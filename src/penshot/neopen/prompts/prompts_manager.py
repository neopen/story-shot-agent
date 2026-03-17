"""
@FileName: prompts_manager.py
@Description: 提示词模板管理类
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10/23 21:54
"""
from pathlib import Path
from typing import Dict, Any

import yaml

from penshot.neopen import prompts
from penshot.neopen.language_manage import Language, get_language
from penshot.logger import error
from penshot.utils.log_utils import print_log_exception


class PromptManager:
    def __init__(self, version: str = "v1.x", language: Language = Language.ZH):
        # 默认使用当前文件的父目录
        self.prompt_dir = Path(__file__).parent / version / language.value
        # 缓存已加载的提示词模板 - 最大缓存1024个提示词
        self._prompt_cache: Dict[str, Dict[str, Any]] = {}
        self._all_prompts_loaded = False

    def get_version(self, name: str) -> str:
        """获取指定名称提示词的版本

        Args:
            name: 提示词名称或标识符

        Returns:
            提示词版本字符串
        """
        # 检查缓存
        if name in self._prompt_cache:
            return self._prompt_cache[name].get("version", "unknown")

        # 如果不在缓存中，先加载提示词
        try:
            self.get_prompt(name)  # 这会更新缓存
            return self._prompt_cache[name].get("version", "unknown")
        except KeyError:
            return "unknown"

    def get_all_prompts(self) -> Dict[str, Dict[str, Any]]:
        """获取所有可用的提示词模板

        Returns:
            所有提示词模板的字典，键为提示词名称，值为提示词配置
        """
        # 使用标志位避免重复加载所有提示词
        if not self._all_prompts_loaded:
            for yaml_file in self.prompt_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)

                        # 处理嵌套结构
                        if isinstance(data, dict):
                            for prompt_key, prompt_data in data.items():
                                if isinstance(prompt_data, dict):
                                    # 使用name字段或键名作为缓存键
                                    # cache_key = prompt_data.get("name", prompt_key)
                                    self._prompt_cache[prompt_key] = prompt_data
                        # 处理旧格式
                        elif isinstance(data, dict) and "name" in data:
                            self._prompt_cache[data["name"]] = data
                except Exception as e:
                    error(f"加载提示词文件 {yaml_file} 时出错: {str(e)}")
                    print_log_exception()
                    continue

            # 标记所有提示词已加载
            self._all_prompts_loaded = True

            # 限制缓存大小为1024个提示词
            if len(self._prompt_cache) > 1024:
                # 只保留最新的1024个提示词
                self._prompt_cache = dict(list(self._prompt_cache.items())[-1024:])

        return self._prompt_cache.copy()

    def get_prompt(self, name: str, file_name: str = None) -> str:
        """获取指定名称的提示词模板
        
        Args:
            name: 提示词名称或标识符
            
        Returns:
            提示词模板字符串
        
        匹配策略（按优先级）：
        1. 首先检查缓存
        2. 对于嵌套格式，优先通过键名(prompt_key)匹配
        3. 对于嵌套格式，其次通过name字段匹配
        4. 对于简单格式，通过name字段匹配
        5. 尝试移除_prompt后缀进行匹配（兼容重命名后的文件）
        """
        # 检查缓存
        if name in self._prompt_cache:
            return self._prompt_cache[name].get("template", "")

        # 尝试多种匹配方式
        match_methods = [
            # 原始名称匹配
            name,
            # 尝试移除_prompt后缀匹配（兼容文件重命名）
            name.replace("_prompt", "") if name.endswith("_prompt") else None
        ]

        # 移除None值
        match_methods = [m for m in match_methods if m]

        data = self.get_all_prompts()  # 确保所有提示词已加载

        # 查找所有YAML文件
        try:
            for prompt_key, prompt_data in data.items():
                # 对每种匹配方式尝试键名和name字段匹配
                for match_name in match_methods:
                    # 优先通过键名匹配
                    if prompt_key == match_name:
                        return prompt_data.get("template", "")
                    # 其次通过name字段匹配
                    if prompt_data.get("name") == match_name:
                        return prompt_data.get("template", "")
        except Exception as e:
            # 记录错误但继续尝试其他文件
            error(f"加载提示词文件 {match_methods} 时出错: {str(e)}")

        # 如果找不到指定名称的提示词，抛出异常
        raise KeyError(f"提示词模板 '{name}' 不存在")

    def get_name_prompt(self, name) -> str:
        """获取剧本解析提示词模板"""
        return self.get_prompt(name)


prompt_manager = PromptManager(version=prompts.__version__, language=get_language())
