"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: consistency_contract.py
@Description: 全局一致性契约 - 贯穿剧本解析、分镜、分割、提示词生成
@Author: NeoPen
@Time: 2026/4/28 0:18
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Set


class ContractStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    COMPLETED = "completed"


@dataclass
class CharacterContract:
    """角色一致性契约"""
    name: str
    first_scene: int = 0
    last_scene: int = 0
    appearance_scenes: List[int] = field(default_factory=list)

    # 外观锚点（从剧本解析时提取）
    appearance_anchors: Dict[str, Any] = field(default_factory=dict)
    # 服装状态序列
    outfit_sequence: List[Dict[str, Any]] = field(default_factory=list)
    # 关联的道具
    held_props: Set[str] = field(default_factory=set)

    def add_appearance(self, scene_num: int, description: str):
        """添加角色出现记录"""
        self.appearance_scenes.append(scene_num)
        self.last_scene = scene_num
        if self.first_scene == 0:
            self.first_scene = scene_num

        # 提取外观特征
        self._extract_appearance_features(description)

    def _extract_appearance_features(self, description: str):
        """从描述中提取外观特征"""
        features = {}
        # 服装特征
        clothes_keywords = ['穿', '着', '戴', '衣服', '裙子', '西装', '衬衫']
        for kw in clothes_keywords:
            if kw in description:
                # 提取服装描述
                idx = description.find(kw)
                if idx > 0:
                    start = max(0, idx - 10)
                    end = min(len(description), idx + 20)
                    features['clothing'] = description[start:end]
                    break

        if features:
            self.appearance_anchors.update(features)

    def get_gap_scenes(self) -> int:
        """获取最大缺席场景数"""
        if len(self.appearance_scenes) <= 1:
            return 0
        max_gap = 0
        for i in range(1, len(self.appearance_scenes)):
            gap = self.appearance_scenes[i] - self.appearance_scenes[i - 1] - 1
            max_gap = max(max_gap, gap)
        return max_gap


@dataclass
class SceneContract:
    """场景一致性契约"""
    scene_num: int
    location: str
    time_of_day: str  # day/night/dawn/dusk
    weather: str = "clear"
    characters_in_scene: List[str] = field(default_factory=list)
    main_emotion: str = "neutral"

    # 道具状态
    props_in_scene: Dict[str, str] = field(default_factory=dict)  # name -> state

    def is_consistent_with(self, other: 'SceneContract') -> bool:
        """检查与另一个场景的一致性"""
        # 场景切换时检查合理性
        if self.location != other.location:
            # 不同场景，检查是否有角色重叠
            common_chars = set(self.characters_in_scene) & set(other.characters_in_scene)
            if common_chars and self.time_of_day != other.time_of_day:
                return False  # 同一角色在不同时间同时出现在两个场景？不合理
        return True


@dataclass
class GlobalConsistencyContract:
    """全局一致性契约 - 贯穿整个工作流"""
    script_id: str
    task_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: ContractStatus = ContractStatus.ACTIVE

    # 各阶段契约
    characters: Dict[str, CharacterContract] = field(default_factory=dict)
    scenes: Dict[int, SceneContract] = field(default_factory=dict)

    # 风格锚点
    style_anchor: Dict[str, Any] = field(default_factory=dict)

    # 版本控制
    version: int = 1
    history: List[Dict] = field(default_factory=list)

    def register_character(self, name: str, scene_num: int, description: str = ""):
        """注册角色"""
        if name not in self.characters:
            self.characters[name] = CharacterContract(name=name)
        self.characters[name].add_appearance(scene_num, description)
        self._record_change("character_appearance", {"name": name, "scene": scene_num})

    def register_scene(self, scene_contract: SceneContract):
        """注册场景"""
        self.scenes[scene_contract.scene_num] = scene_contract
        # 注册场景中的角色
        for char in scene_contract.characters_in_scene:
            self.register_character(char, scene_contract.scene_num)
        self._record_change("scene_registered", {"scene": scene_contract.scene_num})

    def set_style_anchor(self, style_type: str, value: Any):
        """设置风格锚点"""
        self.style_anchor[style_type] = value
        self._record_change("style_anchor", {style_type: value})

    def _record_change(self, change_type: str, data: Dict):
        """记录变更历史"""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "type": change_type,
            "data": data,
            "version": self.version
        })

    def get_character_appearance_consistency(self) -> List[Dict]:
        """检查角色出现一致性"""
        issues = []
        for char in self.characters.values():
            gap = char.get_gap_scenes()
            if gap > 5 and len(self.scenes) > 10:
                issues.append({
                    "type": "character_long_absence",
                    "character": char.name,
                    "gap_scenes": gap,
                    "severity": "moderate",
                    "suggestion": f"角色{char.name}已消失{gap}个场景，考虑是否应继续出现"
                })
        return issues

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "script_id": self.script_id,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "status": self.status.value,
            "characters": {
                name: {
                    "name": c.name,
                    "first_scene": c.first_scene,
                    "last_scene": c.last_scene,
                    "appearance_scenes": c.appearance_scenes,
                    "appearance_anchors": c.appearance_anchors
                }
                for name, c in self.characters.items()
            },
            "scenes": {
                str(num): {
                    "location": s.location,
                    "time_of_day": s.time_of_day,
                    "characters": s.characters_in_scene
                }
                for num, s in self.scenes.items()
            },
            "style_anchor": self.style_anchor,
            "version": self.version
        }
