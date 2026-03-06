"""
@FileName: action_uration_tool.py
@Description: 动作时长估算算法
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10/24 14:01
"""
import re
from functools import lru_cache

import jieba

from hengshot.hengline.config.action_duration_config import action_config


class ActionDurationEstimatorTool:
    """
    生产级动作时长估算器（修复版）
    - 对话时长 = max(字数 × 情绪因子, min_duration)
    - 角色因子仅在顶层应用一次
    - 动作/对话内部逻辑与角色完全解耦合
    """

    def __init__(self):
        self.duration_config = action_config().get_config()

    @lru_cache(maxsize=1024)
    def estimate_action(
            self,
            action_text: str,
            emotion: str = "",
            character_type: str = "default"
    ) -> float:
        """
        估算动作时长（秒）
        角色因子仅在此处应用一次！
        """
        if not action_text.strip():
            return 0.0

        config = self.duration_config

        # 1. 分支：对话 vs 动作
        if self._is_dialogue(action_text):
            # 对话：完全不受角色身体速度影响
            duration = self._estimate_dialogue(action_text, emotion, config)
            char_factor = 1.0
        else:
            # 动作：基础时长计算（不含角色因子）
            duration = self._estimate_action(action_text, emotion, config)
            # 仅在此处应用角色因子
            char_factor = config["character_speed_factors"].get(
                character_type,
                config["character_speed_factors"]["default"]
            )

        # 2. 应用角色因子（唯一位置！）
        duration *= char_factor

        # 3. 全局约束   区分对话和动作的最小值
        if self._is_dialogue(action_text):
            min_dur = config["dialogue"]["min_duration"]  # 1.5
            max_dur = config["dialogue"]["max_duration"]  # 6.0
        else:
            min_dur = config["segmentation"]["min_action_duration"]  # 0.4
            max_dur = float('inf')  # 动作无硬上限

        duration = max(min_dur, min(duration, max_dur))
        return round(duration, 2)

    def _is_dialogue(self, text: str) -> bool:
        """强化对话检测（支持中英文标点）"""
        if "说" not in text:
            return False
        # 检查引号对或冒号后有内容
        if re.search(r'[“”"\'`：:].*?[“”"\'`]', text):
            return True
        if re.search(r'说\s*[：:].', text):
            return True
        return False

    def _estimate_dialogue(self, text: str, emotion: str, config: dict) -> float:
        """估算对话时长（与角色完全无关）"""
        # 1. 首先检查是否有明确的时间标注
        time_match = re.search(r'(\d+)秒|(\d+)分钟|(\d+)小时', text)
        if time_match:
            if time_match.group(1):  # 秒
                return float(time_match.group(1))
            elif time_match.group(2):  # 分钟
                return float(time_match.group(2)) * 60
            elif time_match.group(3):  # 小时
                return float(time_match.group(3)) * 3600

        # 2. 检查是否有"三秒"、"两秒"这样的中文数字时间标注
        chinese_time_match = re.search(r'(一|二|三|四|五|六|七|八|九|十|两|几)秒', text)
        if chinese_time_match:
            chinese_numbers = {
                '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                '几': 3  # 不确定的"几秒"默认按3秒计算
            }
            return float(chinese_numbers.get(chinese_time_match.group(1), 1))

        # 3. 没有时间标注时，使用常规对话时长估算
        # 提取对话内容
        dialogue = ""
        quote_match = re.search(r'[“”"\'`：:].*?[“”"\'`]', text)
        if quote_match:
            dialogue = quote_match.group(0).lstrip('“”"\'`：:').rstrip('“”"\'`')
        else:
            parts = re.split(r'[：:]', text, maxsplit=1)
            if len(parts) > 1:
                dialogue = re.sub(r'^说\s*', '', parts[1]).strip()
            else:
                dialogue = text.replace("说", "").strip()

        # 统计中文字符
        chinese_chars = [c for c in dialogue if '\u4e00' <= c <= '\u9fff' or c in "，。！？；：“”‘’、"]
        char_count = len(chinese_chars)

        if char_count == 0:
            return config["dialogue"]["min_duration"]

        # 获取情绪因子
        emotion = emotion or "默认"
        emo_multipliers = config["dialogue"]["emotion_multipliers"]
        emo_factor = emo_multipliers.get(emotion, emo_multipliers["默认"])

        # 计算原始时长（含情绪修正）
        raw_duration = char_count * config["dialogue"]["base_per_char"] * emo_factor

        # 注意：min/max 限制在 estimate() 中统一应用
        return raw_duration

    def _estimate_action(self, text: str, emotion: str, config: dict) -> float:
        """估算动作基础时长（不含角色因子！）"""

        # 1. 首先检查是否有明确的时间标注
        time_match = re.search(r'(\d+)秒|(\d+)分钟|(\d+)小时', text)
        if time_match:
            if time_match.group(1):  # 秒
                return float(time_match.group(1))
            elif time_match.group(2):  # 分钟
                return float(time_match.group(2)) * 60
            elif time_match.group(3):  # 小时
                return float(time_match.group(3)) * 3600

        # 2. 检查是否有"三秒"、"两秒"这样的中文数字时间标注
        chinese_time_match = re.search(r'(一|二|三|四|五|六|七|八|九|十|两|几)秒', text)
        if chinese_time_match:
            chinese_numbers = {
                '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                '几': 3  # 不确定的"几秒"默认按3秒计算
            }
            return float(chinese_numbers.get(chinese_time_match.group(1), 1))

        # 3. 常规动作时长估算
        words = list(jieba.cut(text, cut_all=False))
        base_actions = config["base_actions"]

        # 匹配最长动词
        base_duration = 1.5
        sorted_verbs = sorted(base_actions.keys(), key=len, reverse=True)
        for verb in sorted_verbs:
            if verb and verb in text:
                base_duration = base_actions[verb]
                break

        # 修饰词修正
        modifier_factor = 1.0
        modifiers = config["modifiers"]
        for word in words:
            if word in modifiers:
                modifier_factor = modifiers[word]
                break

        # 情绪修正（简单映射）
        emotion_factor = 1.0
        if emotion:
            if emotion in ["紧张", "激动", "犹豫"]:
                emotion_factor = 1.1
            elif emotion in ["平静", "冷静"]:
                emotion_factor = 0.95

        return base_duration * modifier_factor * emotion_factor

    def clear_cache(self):
        """清空缓存"""
        self.estimate.cache_clear()
