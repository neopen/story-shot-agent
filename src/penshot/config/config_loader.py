"""
@FileName: config_loader.py
@Description: 
@Author: HiPeng
@Time: 2026/3/31 12:35
"""
import os
from typing import Any, Dict, Tuple

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from penshot.logger import debug, error, warning
from penshot.utils.file_utils import get_logging_path, get_env_path


class ConfigLoader(PydanticBaseSettingsSource):
    """
    配置加载器：统一管理配置优先级。合并YAML和环境变量

    优先级（从高到低）:
        1. 运行时显式参数 (API/Function Call)
        2. 环境变量 (.env)
        3. 代码默认值 (Field default)
    """

    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        self.yaml_config = self._load_yaml_config()
        self.env_config = self._load_env_config()

    def get_field_value(self, field: FieldInfo, field_name: str) -> Tuple[Any, str, bool]:
        """
        返回 (值, 来源, 是否已解析)
        让 pydantic 知道这个 source 能提供值
        """
        # 从合并后的配置中查找字段值（支持嵌套）
        value = self._get_nested_value(self.yaml_config, field_name)
        if value is not None:
            return value, "yaml", True

        value = self._get_nested_value(self.env_config, field_name)
        if value is not None:
            return value, "env", True

        return None, "", False

    def _get_nested_value(self, config: Dict[str, Any], field_name: str) -> Any:
        """
        从嵌套字典中获取字段值
        支持: field_name="llm.default.base_url" → config['llm']['default']['base_url']
        """
        keys = field_name.split('.')
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def __call__(self) -> Dict[str, Any]:
        """合并YAML和环境变量配置"""
        # 深拷贝YAML配置作为基础
        config = self._deep_copy(self.yaml_config)

        # 用环境变量覆盖（环境变量优先级更高）
        config = self._merge_env_into_config(config, self.env_config)

        debug(f"配置合并: YAML配置项={len(self._flatten_dict(self.yaml_config))}, "
              f"环境变量配置项={len(self._flatten_dict(self.env_config))}")

        return config

    def _load_yaml_config(self) -> Dict[str, Any]:
        """加载YAML配置"""
        config = {}

        # 从环境变量获取环境
        env = os.getenv("ENVIRONMENT", "development").lower()

        # 1. 加载基础配置
        settings_file = get_logging_path()
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                    debug(f"加载 settings.yaml: {len(self._flatten_dict(config))} 个配置项")
            except Exception as e:
                error(f"加载 settings.yaml 失败: {e}")
        else:
            warning(" settings.yaml 不存在")

        # 2. 加载环境特定配置
        env_file = get_env_path(f"{env}.yaml")
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    env_config = yaml.safe_load(f) or {}
                    config = self._deep_merge(config, env_config)
                    debug(f"加载 {env_file.name}: {len(self._flatten_dict(env_config))} 个配置项")
            except Exception as e:
                error(f"加载 {env_file} 失败: {e}")

        return config

    def _load_env_config(self) -> Dict[str, Any]:
        """从环境变量加载配置（支持 env_prefix）"""
        env_config = {}

        # 关键：从 model_config 读取配置项
        model_config = self.settings_cls.model_config
        env_prefix = model_config.get('env_prefix', 'PENSHOT_').upper()
        nested_delimiter = model_config.get('env_nested_delimiter', '__')
        case_sensitive = model_config.get('case_sensitive', False)

        debug(f"加载环境变量: prefix='{env_prefix}', delimiter='{nested_delimiter}'")

        for env_key, env_value in os.environ.items():
            if not env_value:
                continue

            # 步骤1: 过滤前缀（必须先用大写比较）
            if env_prefix and not env_key.startswith(env_prefix):
                continue  # 跳过不带项目前缀的变量

            # 步骤2: 去掉前缀后再处理
            key_without_prefix = env_key[len(env_prefix):]

            # 步骤3: 大小写处理
            if not case_sensitive:
                key_without_prefix = key_without_prefix.lower()

            # 步骤4: 按嵌套分隔符分割
            key_parts = [p for p in key_without_prefix.split(nested_delimiter) if p]  # 过滤空片段
            if not key_parts:
                continue

            # 步骤5: 构建嵌套字典
            current = env_config
            for part in key_parts[:-1]:
                current = current.setdefault(part, {})
                if not isinstance(current, dict):
                    current = {}  # 类型冲突时重置

            # 步骤6: 设置叶子节点 + 类型转换
            last_part = key_parts[-1]
            if env_value.lower() in ('true', 'false'):
                current[last_part] = env_value.lower() == 'true'
            elif env_value.isdigit():
                current[last_part] = int(env_value)
            else:
                try:
                    current[last_part] = float(env_value)
                except ValueError:
                    current[last_part] = env_value

        return env_config

    def _deep_copy(self, data: Any) -> Any:
        """深拷贝"""
        if isinstance(data, dict):
            return {k: self._deep_copy(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._deep_copy(item) for item in data]
        else:
            return data

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并配置"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _merge_env_into_config(self, config: Dict[str, Any], env_config: Dict[str, Any]) -> Dict[str, Any]:
        """将环境变量配置合并到主配置中"""
        result = config.copy()

        for key, value in env_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_env_into_config(result[key], value)
            else:
                result[key] = value

        return result

    def _flatten_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """展平字典用于统计"""
        items = {}
        for k, v in d.items():
            if isinstance(v, dict):
                items.update({f"{k}.{subk}": subv for subk, subv in self._flatten_dict(v).items()})
            else:
                items[k] = v
        return items
