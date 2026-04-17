"""
@FileName: continuity_guardian_config.py
@Description: 连续性守护智能体配置
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/11/3 21:31
"""
import os
from typing import Dict, List, Any, Optional

import yaml

from penshot.logger import debug, warning
from penshot.neopen.shot_language import ShotLanguage


class ContinuityGuardianConfig:
    def __init__(self, language:ShotLanguage = None):
        """初始化连续性守护智能体
        
        Args:
            language: 语言枚举，默认使用系统设置的语言
        """
        # 角色状态记忆
        self.character_states = {}
        
        # 设置当前语言
        self._language = language or ShotLanguage.ZH.value
        
        # 设置配置文件路径
        self._set_config_path()

        # 加载连续性守护智能体配置
        self.config = self._load_config()

        # 从配置中加载默认角色外观
        self.default_appearances = self.config.get('default_appearances', {})

        # 构建情绪映射表
        self._build_emotion_mapping()
    
    def _set_config_path(self):
        """设置配置文件路径"""
        current_dir = os.path.dirname(os.path.dirname(__file__))
        
        # 根据语言选择配置文件路径
        if self._language == ShotLanguage.EN.value:
            config_file = 'en/continuity_guardian_config.yaml'
        else:
            config_file = 'zh/continuity_guardian_config.yaml'
        
        self.config_path = os.path.join(
            current_dir, 'config', config_file
        )

    def _load_config(self) -> Dict[str, Any]:
        """加载连续性守护智能体配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            debug(f"成功加载连续性守护智能体配置: {self.config_path}")
            return config
        except Exception as e:
            warning(f"加载连续性守护智能体配置失败: {e}")
            # 返回默认配置
            return {
                'default_appearances': {
                    "pose": "站立",
                    "position": "画面中央",
                    "emotion": "平静",
                    "gaze_direction": "前方",
                    "holding": "无"
                },
                'emotion_mapping': {},
                'emotion_transition_rules': {}
            }


    def _build_emotion_mapping(self):
        """从配置构建情绪映射表"""
        self.emotion_categories = {}

        # 从配置加载情绪映射
        emotion_mapping = self.config.get('emotion_mapping', {})

        # 构建情绪到类别的映射（配置文件中已直接使用中文类别）
        for category, emotions in emotion_mapping.items():
            for emotion in emotions:
                self.emotion_categories[emotion] = category

        debug(f"构建的情绪映射表: {self.emotion_categories}")

    def load_prev_state(self, prev_continuity_state: Optional[Dict[str, Any]]):
        """加载上一段的连续性状态"""
        # 检查prev_continuity_state类型
        if isinstance(prev_continuity_state, dict):
            # 如果是字典，直接使用
            self.character_states = prev_continuity_state
        elif isinstance(prev_continuity_state, list):
            # 如果是列表，转换为字典
            for state in prev_continuity_state:
                character_name = state.get("character_name")
                if character_name:
                    self.character_states[character_name] = state
        elif prev_continuity_state is None:
            # 如果是None，清空character_states
            self.character_states = {}
        else:
            # 其他类型，给出警告并清空
            warning(f"未知的连续性状态类型: {type(prev_continuity_state).__name__}")
            self.character_states = {}

    def extract_characters(self, segment: Dict[str, Any]) -> List[str]:
        """提取段落中的所有角色"""
        characters = set()
        for action in segment.get("actions", []):
            if "character" in action:
                characters.add(action["character"])
        return list(characters)

    def get_character_state(self, character_name: str) -> Dict[str, Any]:
        """获取角色的当前状态"""
        if character_name in self.character_states:
            return self.character_states[character_name].copy()
        else:
            # 返回默认状态
            return {
                "character_name": character_name,
                **self.default_appearances
            }

    def set_character_appearance(self, character_name: str, appearance: Dict[str, Any]):
        """设置角色的外观信息"""
        if character_name not in self.character_states:
            self.character_states[character_name] = self.get_character_state(character_name)
        
        # 添加外观信息到角色状态
        self.character_states[character_name]["appearance"] = appearance

    def generate_character_constraints(self, character_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成角色连续性约束"""
        constraints = {
            "must_start_with_pose": state.get("pose", "unknown"),
            "must_start_with_position": state.get("position", "unknown"),
            "must_start_with_emotion": state.get("emotion", "unknown"),
            "must_start_with_gaze": state.get("gaze_direction", "unknown"),
            "must_start_with_holding": state.get("holding", "unknown"),
            "character_description": self._generate_character_description(character_name, state)
        }
        
        # 如果有外观信息，添加到约束中
        if "appearance" in state:
            constraints["appearance"] = state["appearance"]
        
        return constraints

    def _generate_character_description(self, character_name: str, state: Dict[str, Any]) -> str:
        """生成角色描述"""
        # 如果有外观信息，使用更详细的描述
        if "appearance" in state:
            appearance = state["appearance"]
            desc_parts = [
                character_name,
                f"{appearance.get('age', 'unknown')}岁",
                appearance.get('gender', 'unknown'),
                f"{appearance.get('clothing', '')}",
                f"{appearance.get('hair', '')}",
                f"{appearance.get('base_features', '')}",
                f"姿势: {state.get('pose', 'unknown')}",
                f"情绪: {state.get('emotion', 'unknown')}"
            ]
            # 过滤掉空字符串
            desc_parts = [part for part in desc_parts if part]
            return ", ".join(desc_parts)
        else:
            # 没有外观信息时使用简单描述
            return f"{character_name}, {state.get('pose')}, {state.get('emotion')}"
    
    def set_language(self, language: ShotLanguage):
        """设置语言并重新加载配置
        
        Args:
            language: 语言枚举
        """
        if language.value != self._language:
            self._language = language.value
            self._set_config_path()
            self.config = self._load_config()
            self.default_appearances = self.config.get('default_appearances', {})
            self._build_emotion_mapping()
            debug(f"连续性守护智能体配置语言已切换为: {self._language}")