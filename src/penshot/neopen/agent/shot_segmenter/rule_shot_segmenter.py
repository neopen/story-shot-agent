"""
@FileName: rule_shot_generator.py
@Description: 基于规则的镜头生成器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 17:40
"""
from typing import List, Optional, Dict, Any

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, BaseElement, SceneInfo
from penshot.neopen.agent.shot_segmenter.base_shot_segmenter import BaseShotSegmenter
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info


class RuleShotSegmenter(BaseShotSegmenter):
    """基于规则的MVP分镜拆分器"""

    def __init__(self, config: Optional[ShotConfig]):
        super().__init__(config)
        # 规则配置
        self.rules = {
            "merge_consecutive_dialogues": True,  # 合并连续对话
            "merge_consecutive_actions": False,  # 不合并连续动作
            "min_dialogue_duration": 1.5,  # 最短对话时长
            "max_dialogue_duration": 5.0,  # 最长对话时长
        }

    def split(self, parsed_script: ParsedScript, repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> ShotSequence:
        """使用简单规则拆分剧本"""
        info(f"开始分镜拆分，剧本: {parsed_script.title}")

        shots = []
        current_time = 0.0

        # 设置剧本引用
        script_ref = {
            "title": parsed_script.title or "未命名剧本",
            "total_elements": parsed_script.stats.get("total_elements", 0),
            "original_duration": parsed_script.stats.get("total_duration", 0.0)
        }

        # 遍历所有场景
        for scene_idx, scene in enumerate(parsed_script.scenes):
            scene_shots = self.split_scene(scene, current_time, len(shots))
            shots.extend(scene_shots)

            # 更新当前时间
            if scene_shots:
                current_time = scene_shots[-1].start_time + scene_shots[-1].duration

        # 构建序列
        shot_sequence = ShotSequence(
            script_reference=script_ref,
            shots=shots
        )

        # 后处理
        return self._post_process(shot_sequence)

    def split_scene(self, scene: SceneInfo, start_time: float, shot_offset: int) -> List[ShotInfo]:
        """拆分单个场景"""
        shots = []
        current_scene_time = start_time

        # 场景内元素分组（基于简单规则）
        element_groups = self._group_elements(scene.elements)

        # 为每个组创建镜头
        for group_idx, group in enumerate(element_groups):
            shot_id = self._generate_shot_id(shot_offset + len(shots))

            # 确定镜头类型（基于组内主要元素）
            shot_type = self._determine_group_shot_type(group)

            # 生成描述
            description = self._generate_shot_description(group, scene)

            # 计算时长
            duration = sum(elem.duration for elem in group)

            # 确定主要角色
            main_character = self._determine_main_character(group)

            # 收集元素ID
            element_ids = [elem.id for elem in group]

            # 创建镜头
            shot = ShotInfo(
                id=shot_id,
                scene_id=scene.id,
                description=description,
                start_time=current_scene_time,
                duration=round(duration, 2),
                shot_type=shot_type,
                main_character=main_character,
                element_ids=element_ids,
                confidence=self._calculate_group_confidence(group)
            )

            shots.append(shot)
            current_scene_time += duration

        return shots

    def _group_elements(self, elements: List[BaseElement]) -> List[List[BaseElement]]:
        """将场景元素分组为镜头"""
        if not elements:
            return []

        groups = []
        current_group = [elements[0]]

        for i in range(1, len(elements)):
            current_elem = elements[i]
            prev_elem = elements[i - 1]

            # 判断是否合并到当前组
            should_merge = self._should_merge_elements(prev_elem, current_elem)

            if should_merge:
                current_group.append(current_elem)
            else:
                groups.append(current_group)
                current_group = [current_elem]

        # 添加最后一组
        groups.append(current_group)

        return groups

    def _should_merge_elements(self, elem1: BaseElement, elem2: BaseElement) -> bool:
        """判断两个元素是否应该合并到同一个镜头"""
        # 规则1：连续对话且角色相同 -> 合并
        if (elem1.type == ElementType.DIALOGUE and
                elem2.type == ElementType.DIALOGUE and
                elem1.character == elem2.character and
                self.rules["merge_consecutive_dialogues"]):
            return True

        # 规则2：连续动作且角色相同 -> 不合并（默认）
        if (elem1.type == ElementType.ACTION and
                elem2.type == ElementType.ACTION and
                elem1.character == elem2.character and
                self.rules["merge_consecutive_actions"]):
            return True

        # 规则3：对话后紧跟简短动作 -> 合并（如果动作是对话的延续）
        if (elem1.type == ElementType.DIALOGUE and
                elem2.type == ElementType.ACTION and
                elem2.duration < 3.0):
            return True

        # 默认不合并
        return False

    def _determine_group_shot_type(self, group: List[BaseElement]) -> ShotType:
        """确定镜头类型（基于组内元素）"""
        if not group:
            return ShotType.MEDIUM_SHOT

        # 如果组内有对话，优先用特写
        if any(elem.type == ElementType.DIALOGUE for elem in group):
            return ShotType.CLOSE_UP

        # 如果组内有场景描述，用全景
        if any(elem.type == ElementType.SCENE for elem in group):
            return ShotType.WIDE_SHOT

        # 其他情况用中景
        return ShotType.MEDIUM_SHOT

    def _generate_shot_description(self, group: List[BaseElement], scene: SceneInfo) -> str:
        """生成镜头描述"""
        if not group:
            return "空镜头"

        # 取第一个元素的主要内容
        first_elem = group[0]

        # 简化描述（不再强制截断；支持可选配置）
        base_desc = first_elem.content

        # 如果用户在配置中指定了最大长度，则按该长度截断并保留省略号
        max_len = None
        if self.config is not None:
            max_len = getattr(self.config, 'max_description_length', None)

        if max_len and isinstance(max_len, int) and max_len > 10:
            if len(base_desc) > max_len:
                base_desc = base_desc[:max_len - 3] + "..."

        # 如果是对话，添加说话者
        if first_elem.type == ElementType.DIALOGUE and first_elem.character:
            return f"{first_elem.character}: {base_desc}"

        return base_desc

    def _determine_main_character(self, group: List[BaseElement]) -> Optional[str]:
        """确定主要角色"""
        if not group:
            return None

        # 统计角色出现次数
        char_counts = {}
        for elem in group:
            if elem.character:
                char_counts[elem.character] = char_counts.get(elem.character, 0) + 1

        if not char_counts:
            return None

        # 返回出现最频繁的角色
        return max(char_counts.items(), key=lambda x: x[1])[0]

    def _calculate_group_confidence(self, group: List[BaseElement]) -> float:
        """计算分组置信度"""
        if not group:
            return 0.5

        # 基于元素数量和类型计算置信度
        base_confidence = 0.7

        # 单一元素置信度更高
        if len(group) == 1:
            base_confidence += 0.1

        # 对话元素置信度更高
        if any(elem.type == ElementType.DIALOGUE for elem in group):
            base_confidence += 0.1

        return min(1.0, round(base_confidence, 2))
