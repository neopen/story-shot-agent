"""
@FileName: action_estimator.py
@Description: 基于规则的动作时长估算器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19
"""
from typing import Dict, Any

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, CharacterType, EmotionType
from penshot.neopen.agent.shot_segmenter.estimator.base_estimator import BaseDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.estimator_models import IntensityLevel
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotType
from penshot.neopen.tools.action_duration_tool import ActionDurationEstimatorTool
from penshot.logger import debug


class ActionDurationEstimator(BaseDurationEstimator):
    """动作时长估算器"""

    def __init__(self):
        super().__init__()
        self.action_tool = ActionDurationEstimatorTool()
        self._load_rules()

    def _load_rules(self):
        """加载规则"""
        # 动作镜头类型基准
        self.shot_type_baselines = {
            ShotType.CLOSE_UP: {
                "min": 1.5,
                "max": 4.0,
                "base": 2.2,
                "fast_action": 1.8,
                "slow_action": 2.8
            },
            ShotType.MEDIUM_SHOT: {
                "min": 2.0,
                "max": 5.0,
                "base": 2.8,
                "fast_action": 2.2,
                "slow_action": 3.5
            },
            ShotType.WIDE_SHOT: {
                "min": 2.5,
                "max": 6.0,
                "base": 3.5,
                "fast_action": 2.8,
                "slow_action": 4.5
            }
        }

        # 动作复杂度因子
        self.complexity_factors = {
            "simple": 0.8,
            "normal": 1.0,
            "complex": 1.3,
            "very_complex": 1.6
        }

        # 速度关键词
        self.speed_keywords = {
            "fast": ["快速", "迅速", "猛地", "突然", "飞快", "急速"],
            "slow": ["缓缓", "慢慢", "轻轻", "轻柔", "小心"]
        }

    def estimate_shot(self, shot: ShotInfo, script: ParsedScript) -> float:
        """估算动作镜头时长"""
        debug(f"估算动作镜头: {shot.id}")

        # 获取镜头类型基准
        baseline = self.shot_type_baselines.get(shot.shot_type, self.shot_type_baselines[ShotType.MEDIUM_SHOT])
        base_duration = baseline["base"]

        # 1. 分析动作描述
        description = shot.description
        action_analysis = self._analyze_action_description(description)

        # 2. 应用复杂度调整
        complexity_factor = self.complexity_factors.get(action_analysis["complexity"], 1.0)
        base_duration *= complexity_factor

        # 3. 速度调整
        if action_analysis["is_fast"]:
            base_duration *= 0.8  # 快速动作
        elif action_analysis["is_slow"]:
            base_duration *= 1.3  # 慢速动作

        # 4. 场景情绪调整
        scene_mood = shot.emotion
        if scene_mood in [EmotionType.TENSE.value, EmotionType.ANXIOUS.value]:
            base_duration *= 0.9  # 紧张场景节奏快
        elif scene_mood in [EmotionType.SAD.value, EmotionType.CHOKING.value]:
            base_duration *= 1.2  # 悲伤场景节奏慢

        # 5. 角色特征调整
        character_type = CharacterType.DEFAULT
        if shot.main_character:
            character_type, traits = self._get_character_traits(shot.main_character, script)
            if character_type == CharacterType.ELDER:
                base_duration *= 1.2
            elif character_type == CharacterType.CHILD:
                base_duration *= 0.9

        # 6. 使用动作工具验证
        tool_duration = self.action_tool.estimate_action(
            description,
            emotion=scene_mood,
            character_type=character_type,
            intensity=action_analysis["intensity"]
        )

        # 综合两种方法（加权平均）
        final_duration = (base_duration * 0.4 + tool_duration * 0.6)

        return self._clamp_duration(final_duration, baseline["min"], baseline["max"])

    def _analyze_action_description(self, description: str) -> Dict[str, Any]:
        """分析动作描述"""
        result = {
            "complexity": "normal",
            "is_fast": False,
            "is_slow": False,
            "intensity": IntensityLevel.NORMAL,
            "word_count": len(description)
        }

        # 判断复杂度
        if len(description) > 20:
            result["complexity"] = "complex"
        elif len(description) > 10:
            result["complexity"] = "normal"
        else:
            result["complexity"] = "simple"

        # 判断速度
        for keyword in self.speed_keywords["fast"]:
            if keyword in description:
                result["is_fast"] = True
                result["intensity"] = IntensityLevel.HIGH
                break

        for keyword in self.speed_keywords["slow"]:
            if keyword in description:
                result["is_slow"] = True
                result["intensity"] = IntensityLevel.LOW
                break

        return result
