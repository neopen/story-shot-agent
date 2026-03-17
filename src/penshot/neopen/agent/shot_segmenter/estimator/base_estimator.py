"""
@FileName: base_estimator.py
@Description: 时长估算基类
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/19
"""
import re
from abc import abstractmethod
from typing import Dict, List, Optional

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, CharacterType
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotSequence, ShotType


class EstimationContext:
    """估算上下文"""

    def __init__(self):
        self.scene_id: str = ""
        self.scene_description: str = ""
        self.scene_mood: str = "neutral"
        self.scene_location: str = ""
        self.characters: List[str] = []
        self.total_shots: int = 0
        self.script: Optional[ParsedScript] = None

    def update_from_shot(self, shot: ShotInfo, script: ParsedScript):
        """从镜头更新上下文"""
        self.scene_id = shot.scene_id
        self.script = script

        # 查找场景信息
        for scene in script.scenes:
            if scene.id == shot.scene_id:
                self.scene_description = scene.description or ""
                self.scene_location = scene.location
                if scene.audio_context:
                    self.scene_mood = scene.audio_context.atmosphere
                break

        # 获取所有角色
        self.characters = [c.name for c in script.characters]

    def to_dict(self) -> Dict:
        return {
            "scene_id": self.scene_id,
            "scene_mood": self.scene_mood,
            "scene_location": self.scene_location,
            "characters": self.characters,
            "total_shots": self.total_shots
        }


class BaseDurationEstimator:
    """时长估算基类"""

    def __init__(self):
        self.context = EstimationContext()

    def set_context(self, context: EstimationContext):
        """设置上下文"""
        self.context = context

    @abstractmethod
    def estimate_shot(self, shot: ShotInfo, script: ParsedScript) -> float:
        """估算单个镜头时长（子类必须实现）"""
        pass

    def estimate_sequence(self, sequence: ShotSequence, script: ParsedScript) -> ShotSequence:
        """估算整个序列"""
        for shot in sequence.shots:
            shot.duration = self.estimate_shot(shot, script)

        # 更新统计数据
        sequence.stats = self._update_stats(sequence)
        return sequence

    def _update_stats(self, sequence: ShotSequence) -> Dict:
        """更新统计数据"""
        stats = {
            "shot_count": len(sequence.shots),
            "total_duration": sum(s.duration for s in sequence.shots),
            "avg_shot_duration": 0.0,
            "close_up_count": 0,
            "wide_shot_count": 0,
            "medium_shot_count": 0
        }

        if stats["shot_count"] > 0:
            stats["avg_shot_duration"] = stats["total_duration"] / stats["shot_count"]

        for shot in sequence.shots:
            if shot.shot_type == ShotType.CLOSE_UP:
                stats["close_up_count"] += 1
            elif shot.shot_type == ShotType.WIDE_SHOT:
                stats["wide_shot_count"] += 1
            else:
                stats["medium_shot_count"] += 1

        return stats

    def _get_scene_location(self, shot: ShotInfo, script: ParsedScript) -> str:
        """获取场景地点"""
        for scene in script.scenes:
            if scene.id == shot.scene_id:
                return scene.location
        return ""

    def _get_character_traits(self, character_name: str, script: ParsedScript) -> (CharacterType, List[str]):
        """获取角色特征"""
        for char in script.characters:
            if char.name == character_name:
                return char.type, char.key_traits

        return CharacterType.DEFAULT, []

    def _clamp_duration(self, duration: float, min_val: float = 0.5, max_val: float = 10.0) -> float:
        """限制时长范围"""
        return round(max(min_val, min(duration, max_val)), 2)

    def _calculate_pause_time(self, text: str) -> float:
        """计算停顿时间"""
        pause = 0.0

        # 问号
        pause += text.count('？') * 0.3
        pause += text.count('?') * 0.3

        # 感叹号
        pause += text.count('！') * 0.4
        pause += text.count('!') * 0.4

        # 省略号
        pause += text.count('……') * 0.8
        pause += text.count('...') * 0.8

        # 句号
        sentences = re.split(r'[。！？!?]', text)
        pause += (len(sentences) - 1) * 0.2

        return pause
