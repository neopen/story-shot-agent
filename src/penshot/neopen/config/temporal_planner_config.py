"""
@FileName: temporal_planner_config.py
@Description: 时序规划智能体配置管理
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10/27 17:24
"""
from functools import lru_cache
from typing import Dict, Any

from penshot.neopen.config.base_config import BaseConfig
from penshot.neopen.language_manage import Language
from penshot.logger import debug


class TemporalPlannerConfig(BaseConfig):
    """时序规划智能体配置类"""

    def _initialize_config(self, language: Language = Language.ZH):
        """初始化配置管理器
        
        Args:
            language: 语言枚举，默认使用系统设置的语言
        """
        # 设置当前语言
        self._language = language

        self._base_config = {}
        self._scene_estimator = {}
        self._dialogue_estimator = {}
        self._action_estimator = {}

        self._target_segment_duration = 5.0
        self._max_duration_deviation = 0.5
        self._min_action_duration = 0.4
        self._default_duration = 0.8

    def _config_file_name(self) -> str:
        """配置文件名"""
        return "duration_estimator_config.yaml"

    def _load_config(self):
        """从配置文件加载动作时长数据"""
        # 加载基础动作时长
        self._base_config = self._config_data.get('base_config', {})

        # 加载修饰词修正系数
        self._scene_estimator = self._config_data.get('scene_estimator', {})

        # 加载对话参数
        self._dialogue_estimator = self._config_data.get('dialogue_estimator', {})
        # 加载动作参数
        self._action_estimator = self._config_data.get('action_estimator', {})

        # 默认动作时长
        self._default_duration = 0.8

    @lru_cache(maxsize=100)
    def get_base_config(self, name: str, default=None) -> Any:
        """获取基础动作时长"""
        return self._base_config.get(name, default)

    @property
    def scene_estimator(self) -> Any:
        """获取修饰词修正系数"""
        return self._scene_estimator

    @property
    def dialogue_estimator(self) -> Any:
        """获取对话参数"""
        return self._dialogue_estimator

    @property
    def action_estimator(self) -> Any:
        """获取动作参数"""
        return self._action_estimator

    # Getter methods
    @property
    def target_segment_duration(self) -> float:
        """获取目标分段时长"""
        return self._target_segment_duration

    @property
    def max_duration_deviation(self) -> float:
        """获取最大时长偏差"""
        return self._max_duration_deviation

    @property
    def min_action_duration(self) -> float:
        """获取最小动作时长"""
        return self._min_action_duration

    @property
    def default_duration(self) -> float:
        """获取默认动作时长"""
        return self._default_duration

    # Setter methods
    @target_segment_duration.setter
    def target_segment_duration(self, value: float):
        """设置目标分段时长"""
        if value > 0:
            self._target_segment_duration = value
            debug(f"目标分段时长已设置为: {value}秒")

    @max_duration_deviation.setter
    def max_duration_deviation(self, value: float):
        """设置最大时长偏差"""
        if value >= 0:
            self._max_duration_deviation = value
            debug(f"最大时长偏差已设置为: {value}秒")

    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "base_config": len(self._base_config),
            "scene_estimator": len(self._scene_estimator),
            "target_segment_duration": self._target_segment_duration,
            "max_duration_deviation": self._max_duration_deviation,
            "min_action_duration": self._min_action_duration,
            "language": self._language
        }


# 创建全局配置实例
planner_config = TemporalPlannerConfig()


def get_planner_config(language: Language = None) -> TemporalPlannerConfig:
    """
    获取时序规划配置实例
    
    Args:
        language: 语言枚举，默认使用系统设置的语言
        
    Returns:
        TemporalPlannerConfig: 配置实例
    """
    global planner_config

    if language and language.value != planner_config._language:
        planner_config.set_language(language)

    return planner_config


def reload_configuration() -> TemporalPlannerConfig:
    """
    重新加载配置文件
    """
    global planner_config
    planner_config.load_configuration()
    debug("配置已重新加载")
    return planner_config
