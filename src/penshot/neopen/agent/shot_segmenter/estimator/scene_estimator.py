"""
@FileName: scene_estimator.py
@Description: 场景时长估算器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19
"""

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, EmotionType
from penshot.neopen.agent.shot_segmenter.estimator.base_estimator import BaseDurationEstimator
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotType
from penshot.logger import debug


class SceneDurationEstimator(BaseDurationEstimator):
    """场景时长估算器"""

    def __init__(self):
        super().__init__()
        self._load_rules()

    def _load_rules(self):
        """加载规则"""
        # 场景镜头类型基准
        self.shot_type_baselines = {
            ShotType.WIDE_SHOT: {
                "min": 3.0,
                "max": 8.0,
                "establishing": 4.5,
                "atmosphere": 4.0,
                "ending": 4.5
            },
            ShotType.MEDIUM_SHOT: {
                "min": 2.0,
                "max": 6.0,
                "base": 3.0,
                "transition": 2.5
            },
            ShotType.CLOSE_UP: {
                "min": 1.5,
                "max": 4.0,
                "detail": 2.0
            }
        }

        # 场景类型调整
        self.scene_type_factors = {
            "室内": 1.0,
            "室外": 1.2,
            "内景": 1.0,
            "外景": 1.2
        }

        # 时间调整
        self.time_factors = {
            "白天": 1.0,
            "夜晚": 1.2,
            "黎明": 1.1,
            "黄昏": 1.1
        }

    def estimate_shot(self, shot: ShotInfo, script: ParsedScript) -> float:
        """估算场景镜头时长"""
        debug(f"估算场景镜头: {shot.id}")

        # 获取镜头类型基准
        baseline = self.shot_type_baselines.get(shot.shot_type, self.shot_type_baselines[ShotType.MEDIUM_SHOT])

        # 1. 根据镜头目的确定基础时长
        base_duration = baseline.get("base", 3.0)

        if "建立" in shot.description or "establish" in shot.description.lower():
            base_duration = baseline["establishing"]
        elif "氛围" in shot.description or "atmosphere" in shot.description.lower():
            base_duration = baseline.get("atmosphere", 4.0)
        elif "结束" in shot.description or "ending" in shot.description.lower():
            base_duration = baseline.get("ending", 4.0)

        # 2. 场景类型调整
        location = self._get_scene_location(shot, script)
        for key, factor in self.scene_type_factors.items():
            if key in location:
                base_duration *= factor
                break

        # 3. 时间调整
        time_key = self._detect_time(shot.description)
        if time_key in self.time_factors:
            base_duration *= self.time_factors[time_key]

        # 4. 情绪调整
        scene_mood = self._get_scene_mood(shot, script)
        if scene_mood in ["magnificent", "imposing", "majestic", "grandiose", "palatial", "majestical"]:
            base_duration *= 1.3
        elif scene_mood in [EmotionType.REPRESSION.value, EmotionType.HEAVY.value]:
            base_duration *= 1.2
        elif scene_mood in [EmotionType.TENSE.value]:
            base_duration *= 0.9

        # 5. 视觉复杂度调整
        visual_complexity = self._estimate_visual_complexity(shot.description)
        base_duration *= visual_complexity

        return self._clamp_duration(base_duration, baseline["min"], baseline["max"])


    def _get_scene_mood(self, shot: ShotInfo, script: ParsedScript) -> str:
        """获取场景情绪"""
        for scene in script.scenes:
            if scene.id == shot.scene_id:
                if scene.audio_context:
                    return scene.audio_context.atmosphere
        return "neutral"


    def _detect_time(self, description: str) -> str:
        """检测时间"""
        time_keywords = {
            "白天": ["白天", "上午", "下午", "中午"],
            "夜晚": ["夜晚", "晚上", "深夜", "night"],
            "黎明": ["黎明", "清晨", "dawn"],
            "黄昏": ["黄昏", "傍晚", "dusk"]
        }

        for time_key, keywords in time_keywords.items():
            for keyword in keywords:
                if keyword in description:
                    return time_key
        return "白天"

    def _estimate_visual_complexity(self, description: str) -> float:
        """估算视觉复杂度"""
        # 基于描述长度和关键词估算复杂度
        complexity = 1.0

        # 长描述通常意味着更复杂的场景
        if len(description) > 50:
            complexity *= 1.3
        elif len(description) > 30:
            complexity *= 1.1

        # 视觉元素关键词
        visual_keywords = ["光影", "色彩", "细节", "纹理", "层次"]
        for keyword in visual_keywords:
            if keyword in description:
                complexity *= 1.1

        return min(complexity, 2.0)
