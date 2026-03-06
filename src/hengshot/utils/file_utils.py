"""
@FileName: file_utils.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/18 12:24
"""
import json
from typing import Any
from pathlib import Path
import importlib.resources as resources

from hengshot.utils.obj_utils import dict_to_obj


def load_from_json(json_path: str) -> str:
    """从JSON文件加载数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data


def load_from_obj(json_path: str, cls) -> Any:
    """从JSON文件加载数据"""
    return dict_to_obj(load_from_json(json_path), cls)


def save_to_json(cls: Any, file_name):
    # 保存为JSON
    with open(f"{file_name}.json", "w", encoding="utf-8") as f:
        json.dump(cls.to_dict(), f, ensure_ascii=False, indent=2)


# =============== 资源文件路径获取 ===============
def get_file_path(package, file_name) -> Path:
    """获取配置文件路径"""
    with resources.path(f"hengshot.{package}", file_name) as path:
        return Path(path)

def get_subdir_path(subdir: str, filename: str) -> Path:
    """
    获取包内文件路径（安全版本）

    参数:
        subdir: 子目录名（如 "data", "config"），可以是空字符串
        filename: 文件名

    返回:
        Path: 文件的绝对路径
    """
    # Python 3.9+
    if subdir:
        resource_path = f"{subdir}/{filename}"
    else:
        resource_path = filename

    with resources.path("hengshot", resource_path) as path:
        return Path(path)


def get_env_path(file_name) -> Path:
    """获取配置文件路径"""
    return get_file_path("config.env", file_name)

def get_config_path(file_name) -> Path:
    """获取配置文件路径"""
    return get_file_path("config", file_name)


def get_logging_path() -> Path:
    """获取配置文件路径"""
    return get_config_path("logging.yaml")


def get_settings_path() -> Path:
    """获取配置文件路径"""
    return get_config_path("settings.yaml")
