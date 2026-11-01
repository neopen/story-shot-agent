"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_paths_config.py
@Description: 嵌套路径配置与 get_data_paths() 兼容性回归测试
@Author: NeoPen
"""
import os

from penshot.config.config import settings
from penshot.config.config_models import PathsConfig


def test_paths_config_defaults_are_nested():
    """PathsConfig 默认值应与 settings.yaml 的嵌套结构一致"""
    paths = PathsConfig()

    assert paths.data.input == "./data/input"
    assert paths.data.output == "./data/output"
    assert paths.logs.base == "./logs"
    assert paths.logs.errors == "./logs/errors"
    assert paths.temp.uploads == "./tmp/uploads"
    assert paths.temp.processed == "./tmp/processed"


def test_settings_loads_nested_yaml_paths():
    """settings.yaml 中 paths 的嵌套配置应能正确加载"""
    assert settings.paths.data.input == "./data/input"
    assert settings.paths.data.output == "./data/output"
    assert settings.paths.data.embedding == "./data/embedding"
    assert settings.paths.data.cache == "./data/cache"
    assert settings.paths.logs.errors == "./logs/errors"
    assert settings.paths.temp.processed == "./tmp/processed"


def test_nested_paths_partial_override():
    """只覆盖部分嵌套字段时，其余字段应保持默认值"""
    overridden = PathsConfig(data={"output": "custom/output"})

    assert overridden.data.output == "custom/output"
    assert overridden.data.input == "./data/input"


def test_get_data_paths_keeps_flat_keys_and_absolute_paths():
    """get_data_paths() 应继续返回 data_* 扁平键，并解析为绝对路径"""
    data_paths = settings.get_data_paths()

    assert set(data_paths) == {
        "data_input",
        "data_output",
        "data_memory",
        "data_embedding",
        "data_template",
        "data_model",
        "data_checkpoint",
        "data_cache",
    }
    assert os.path.isabs(data_paths["data_output"])
    assert data_paths["data_output"].endswith(os.path.join("data", "output"))


def test_get_log_paths_keeps_flat_keys_and_absolute_paths():
    """get_log_paths() 应返回 log_* 扁平键，并解析为绝对路径"""
    log_paths = settings.get_log_paths()

    assert set(log_paths) == {"log_base", "log_app", "log_api", "log_errors"}
    assert os.path.isabs(log_paths["log_errors"])
    assert log_paths["log_errors"].endswith(os.path.join("logs", "errors"))


def test_get_temp_paths_keeps_flat_keys_and_absolute_paths():
    """get_temp_paths() 应返回 temp_* 扁平键，并解析为绝对路径"""
    temp_paths = settings.get_temp_paths()

    assert set(temp_paths) == {"temp_base", "temp_uploads", "temp_processed"}
    assert os.path.isabs(temp_paths["temp_processed"])
    assert temp_paths["temp_processed"].endswith(os.path.join("tmp", "processed"))
