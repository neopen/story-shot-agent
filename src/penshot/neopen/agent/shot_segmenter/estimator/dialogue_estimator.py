"""
@FileName: dialogue_estimator.py
@Description: 对话时长估算器
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/19
"""
import re

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, CharacterType, EmotionType
from penshot.neopen.agent.shot_segmenter.estimator.base_estimator import BaseDurationEstimator
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotType
from penshot.logger import debug


class DialogueDurationEstimator(BaseDurationEstimator):
    """对话时长估算器"""

    def __init__(self):
        super().__init__()
        self._load_rules()

    def _load_rules(self):
        """加载规则"""
        # 对话镜头类型基准
        self.shot_type_baselines = {
            ShotType.CLOSE_UP: {
                "min": 1.5,
                "max": 5.0,
                "base": 2.5,
                "emotional": 3.5,
                "normal": 2.2
            },
            ShotType.MEDIUM_SHOT: {
                "min": 2.0,
                "max": 5.0,
                "base": 3.0,
                "dialogue": 2.8,
                "reaction": 2.2
            },
            ShotType.WIDE_SHOT: {
                "min": 2.5,
                "max": 6.0,
                "base": 3.5,
                "group": 4.0
            }
        }

        # 语速配置（字/秒）
        self.speech_rates = {
            "fast": 4.0,
            "normal": 3.0,
            "slow": 2.0,
            "very_slow": 1.5
        }

        # 情感语速调整
        self.emotion_speed = {
            "平静": "normal",
            "neutral": "normal",
            "开心": "fast",
            "愤怒": "fast",
            "悲伤": "slow",
            "哽咽": "very_slow",
            "激动": "fast",
            "紧张": "fast",
            "犹豫": "slow"
        }

        # 标点停顿时间（秒）
        self.punctuation_pauses = {
            "？": 0.3,
            "！": 0.4,
            "!": 0.4,
            "……": 0.8,
            "...": 0.8,
            "，": 0.1,
            ",": 0.1
        }

    def estimate_shot(self, shot: ShotInfo, script: ParsedScript) -> float:
        """估算对话镜头时长"""
        debug(f"估算对话镜头: {shot.id}")

        # 获取镜头类型基准
        baseline = self.shot_type_baselines.get(shot.shot_type, self.shot_type_baselines[ShotType.CLOSE_UP])

        # 1. 从描述中提取对话内容
        dialogue_text = self._extract_dialogue(shot.description)

        # 2. 计算对话基础时长
        word_count = len(dialogue_text)
        if word_count == 0:
            return baseline["min"]

        # 3. 确定语速
        speed_key = self.emotion_speed.get(shot.emotion, "normal")
        speech_rate = self.speech_rates[speed_key]

        # 4. 基础时长 = 字数 / 语速
        base_duration = word_count / speech_rate

        # 5. 添加停顿时间
        pause_time = self._calculate_pause_time(dialogue_text)
        base_duration += pause_time

        # 6. 情感镜头调整("悲伤", "激动")
        if shot.emotion in [EmotionType.SAD, EmotionType.EMOTIONAL] and shot.shot_type == ShotType.CLOSE_UP:
            base_duration *= 1.3

        # 7. 角色特征调整
        if shot.main_character:
            character_type, traits = self._get_character_traits(shot.main_character, script)
            # if "老人" in traits or "老年" in traits:
            #     base_duration *= 1.2
            # elif "小孩" in traits or "儿童" in traits:
            #     base_duration *= 0.8
            if character_type == CharacterType.ELDER:
                base_duration *= 1.2
            elif character_type == CharacterType.CHILD:
                base_duration *= 0.8

        # 8. 确保在合理范围内
        final_duration = self._clamp_duration(base_duration, baseline["min"], baseline["max"])

        return final_duration

    def _extract_dialogue(self, description: str) -> str:
        """从描述中提取对话内容"""
        # 匹配引号内的内容
        quote_pattern = r'["“](.*?)["”]'
        quotes = re.findall(quote_pattern, description)
        if quotes:
            return quotes[0]

        # 匹配冒号后的内容
        colon_pattern = r'[:：](.*?)$'
        colon_match = re.search(colon_pattern, description)
        if colon_match:
            return colon_match.group(1).strip()

        return description
