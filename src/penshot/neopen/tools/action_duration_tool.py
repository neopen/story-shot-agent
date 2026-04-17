"""
@FileName: action_uration_tool.py
@Description: 动作时长估算算法
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10/24 14:01
"""
import re
from functools import lru_cache
from typing import Dict, Any, List

import jieba

from penshot.neopen.agent.script_parser.script_parser_models import CharacterType, EmotionType
from penshot.neopen.agent.shot_segmenter.estimator.estimator_models import IntensityLevel
from penshot.neopen.config.action_duration_config import action_config
from penshot.logger import debug, warning


class ActionDurationEstimatorTool:
    """
    生产级动作时长估算器（优化修复版）

    特点：
    - 支持精确的缓存机制
    - 完整的类型提示
    - 强度参数映射为数值
    - 更好的错误处理
    - 日志记录
    """

    def __init__(self):
        """初始化估算器"""
        self.duration_config = action_config().get_config()
        self._validate_config()

        # 强度级别到数值的映射
        self.intensity_map = {
            IntensityLevel.VERY_LOW: 0.3,
            IntensityLevel.LOW: 0.5,
            IntensityLevel.NORMAL: 1.0,
            IntensityLevel.HIGH: 1.5,
            IntensityLevel.VERY_HIGH: 2.0
        }

    def _validate_config(self):
        """验证配置完整性"""
        required_sections = ["base_actions", "modifiers", "dialogue",
                             "character_speed_factors", "segmentation"]

        for section in required_sections:
            if section not in self.duration_config:
                warning(f"配置缺少必要部分: {section}，使用默认值")
                self.duration_config[section] = self._get_default_config(section)

    def _get_default_config(self, section: str) -> Dict:
        """获取默认配置"""
        defaults = {
            "base_actions": {"走": 2.0, "跑": 1.2, "坐": 1.3},
            "modifiers": {"快速": 0.7, "慢慢": 1.7},
            "dialogue": {
                "base_per_char": 0.35,
                "min_duration": 1.5,
                "max_duration": 6.0,
                "emotion_multipliers": {"默认": 1.0}
            },
            "character_speed_factors": {"default": 1.0},
            "segmentation": {"min_action_duration": 0.4}
        }
        return defaults.get(section, {})

    @lru_cache(maxsize=2048)
    def estimate_action(
            self,
            action_text: str,
            emotion: str = EmotionType.NEUTRAL.value,
            character_type: CharacterType = CharacterType.DEFAULT,
            intensity: IntensityLevel = IntensityLevel.NORMAL
    ) -> float:
        """
        估算动作时长（秒）

        Args:
            action_text: 动作描述文本
            emotion: 情绪类型
            character_type: 角色类型
            intensity: 强度级别

        Returns:
            估算时长（秒）
        """
        debug(f"估算动作: {action_text[:30]}...")

        try:
            if not action_text or not action_text.strip():
                debug("空动作描述，返回0")
                return 0.0

            config = self.duration_config

            # 1. 检查是否为对话
            is_dialogue = self._is_dialogue(action_text)

            if is_dialogue:
                # 对话估算
                duration = self._estimate_dialogue(action_text, emotion, config)
                char_factor = 1.0  # 对话不受角色速度影响
            else:
                # 动作估算
                duration = self._estimate_action_core(action_text, emotion, config)
                # 应用角色因子
                char_factor = config["character_speed_factors"].get(
                    character_type,
                    config["character_speed_factors"]["default"]
                )

            # 2. 应用角色因子
            duration *= char_factor

            # 3. 应用强度因子
            intensity_factor = self.intensity_map.get(intensity, 1.0)
            duration *= intensity_factor

            # 4. 全局约束
            if is_dialogue:
                min_dur = config["dialogue"]["min_duration"]
                max_dur = config["dialogue"]["max_duration"]
            else:
                min_dur = config["segmentation"]["min_action_duration"]
                max_dur = float('inf')

            duration = max(min_dur, min(duration, max_dur))

            debug(f"估算结果: {round(duration, 2)}秒")
            return round(duration, 2)

        except Exception as e:
            warning(f"动作估算失败: {e}，使用默认值")
            return self._get_fallback_duration(action_text)

    def _get_fallback_duration(self, text: str) -> float:
        """获取降级默认时长"""
        if self._is_dialogue(text):
            return self.duration_config["dialogue"]["min_duration"]
        return self.duration_config["segmentation"]["min_action_duration"]

    def _is_dialogue(self, text: str) -> bool:
        """强化对话检测"""
        if not text or "说" not in text:
            return False

        # 检查引号对
        if re.search(r'[“”"\'`].*?[“”"\'`]', text):
            return True

        # 检查冒号后的内容
        if re.search(r'说\s*[：:]\s*\S+', text):
            return True

        # 检查常见对话模式
        dialogue_patterns = [
            r'[“”"\'`].*?[“”"\'`]',  # 引号内容
            r'：.*',  # 中文冒号后
            r':.*',  # 英文冒号后
        ]

        for pattern in dialogue_patterns:
            if re.search(pattern, text):
                return True

        return False

    def _extract_dialogue_content(self, text: str) -> str:
        """提取对话内容"""
        # 尝试匹配引号内容
        quote_match = re.search(r'[“”"\'`](.*?)[“”"\'`]', text)
        if quote_match:
            return quote_match.group(1).strip()

        # 尝试匹配冒号后内容
        colon_match = re.search(r'[：:]\s*(.*?)$', text)
        if colon_match:
            return colon_match.group(1).strip()

        # 移除"说"字后返回
        return text.replace("说", "").strip()

    def _estimate_dialogue(self, text: str, emotion: str, config: dict) -> float:
        """估算对话时长"""
        # 检查时间标注
        explicit_time = self._check_explicit_time(text)
        if explicit_time > 0:
            return explicit_time

        # 提取对话内容
        dialogue = self._extract_dialogue_content(text)

        # 统计中文字符
        chinese_chars = [
            c for c in dialogue
            if '\u4e00' <= c <= '\u9fff' or c in "，。！？；：“”‘’、"
        ]
        char_count = len(chinese_chars)

        if char_count == 0:
            return config["dialogue"]["min_duration"]

        # 获取情绪因子
        emotion = emotion or "默认"
        emo_multipliers = config["dialogue"]["emotion_multipliers"]
        emo_factor = emo_multipliers.get(emotion, emo_multipliers["默认"])

        # 计算原始时长
        raw_duration = char_count * config["dialogue"]["base_per_char"] * emo_factor

        return raw_duration

    def _estimate_action_core(self, text: str, emotion: str, config: dict) -> float:
        """估算动作核心时长"""
        # 检查时间标注
        explicit_time = self._check_explicit_time(text)
        if explicit_time > 0:
            return explicit_time

        # 分词
        words = list(jieba.cut(text, cut_all=False))
        base_actions = config["base_actions"]

        # 匹配基础动作（优先匹配长词）
        base_duration = 1.5
        sorted_verbs = sorted(base_actions.keys(), key=len, reverse=True)

        for verb in sorted_verbs:
            if verb and verb in text:
                base_duration = base_actions[verb]
                debug(f"匹配到动作: {verb} -> {base_duration}s")
                break

        # 修饰词修正
        modifier_factor = 1.0
        modifiers = config["modifiers"]

        for word in words:
            if word in modifiers:
                modifier_factor = modifiers[word]
                debug(f"匹配到修饰词: {word} -> {modifier_factor}")
                break

        # 情绪修正
        emotion_factor = self._get_emotion_factor(emotion)

        return base_duration * modifier_factor * emotion_factor

    def _check_explicit_time(self, text: str) -> float:
        """检查显式时间标注"""
        # 数字时间（如"3秒"）
        time_match = re.search(r'(\d+)秒|(\d+)分钟|(\d+)小时', text)
        if time_match:
            if time_match.group(1):  # 秒
                return float(time_match.group(1))
            elif time_match.group(2):  # 分钟
                return float(time_match.group(2)) * 60
            elif time_match.group(3):  # 小时
                return float(time_match.group(3)) * 3600

        # 中文数字时间（如"三秒"）
        chinese_nums = {
            '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '几': 3, '数': 2
        }

        for cn, num in chinese_nums.items():
            if f"{cn}秒" in text:
                return float(num)

        return 0.0

    def _get_emotion_factor(self, emotion: str) -> float:
        """获取情绪因子"""
        emotion_factors = {
            EmotionType.TENSE.value: 1.1,
            EmotionType.EXCITED.value: 1.1,
            EmotionType.HESITANT.value: 1.2,
            EmotionType.CALM.value: 0.95,
            EmotionType.SAD.value: 0.9,
            EmotionType.ANGRY.value: 1.1,
            EmotionType.HAPPY.value: 1.05,
            EmotionType.NEUTRAL.value: 1.0,
            EmotionType.CRYING.value: 0.85,
            EmotionType.WHISPER.value: 0.9,
        }

        return emotion_factors.get(emotion, 1.0)

    def batch_estimate(self, actions: List[Dict[str, Any]]) -> List[float]:
        """
        批量估算多个动作

        Args:
            actions: 动作字典列表，每个字典包含text、emotion等字段

        Returns:
            时长列表
        """
        results = []
        for action in actions:
            try:
                duration = self.estimate_action(
                    action_text=action.get("text", ""),
                    emotion=action.get("emotion", EmotionType.NEUTRAL.value),
                    character_type=action.get("character_type", CharacterType.DEFAULT),
                    intensity=action.get("intensity", IntensityLevel.NORMAL)
                )
                results.append(duration)
            except Exception as e:
                warning(f"批量估算失败: {e}")
                results.append(self._get_fallback_duration(action.get("text", "")))

        return results

    def clear_cache(self):
        """清空缓存"""
        self.estimate_action.cache_clear()
        debug("动作估算缓存已清空")

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        return {
            "hits": self.estimate_action.cache_info().hits,
            "misses": self.estimate_action.cache_info().misses,
            "maxsize": self.estimate_action.cache_info().maxsize,
            "currsize": self.estimate_action.cache_info().currsize
        }
