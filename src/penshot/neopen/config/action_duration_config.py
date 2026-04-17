"""
@FileName: action_uration_tool.py
@Description: 动作时长估算算法
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10/24 14:01
"""
from typing import Dict, Any

import jieba

from penshot.neopen.config.base_config import BaseConfig
from penshot.neopen.shot_language import ShotLanguage


class ActionDurationConfig(BaseConfig):
    """
    生产级动作时长估算器（修复版）
    - 对话时长 = max(字数 × 情绪因子, min_duration)
    - 角色因子仅在顶层应用一次
    - 动作/对话内部逻辑与角色完全解耦合
    """
    def _initialize_config(self, language: ShotLanguage = ShotLanguage.ZH):
        self._language = language
        self._init_jieba()

    def _config_file_name(self) -> str:
        """配置文件名"""
        return "action_duration_config.yaml"

    def _init_jieba(self):
        """优化中文分词"""
        for verb in self._config_data.get("base_actions", {}):
            jieba.add_word(verb, freq=2000, tag='v')
        for mod in self._config_data.get("modifiers", {}):
            jieba.add_word(mod, freq=2000, tag='d')

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self._config_data

    def reload_config(self):
        """热重载配置"""
        self.load_configuration()


action_config = ActionDurationConfig