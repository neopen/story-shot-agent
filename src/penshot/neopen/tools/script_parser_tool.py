"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: script_parser_tool.py
@Description: 剧本解析工具 - 规则解析引擎的适配层，负责解析与文档转换
@Author: NeoPen
"""

import re
from typing import Dict, List, Optional, Tuple

from llama_index.core.schema import Document

from penshot.logger import debug, info, error
from penshot.neopen.agent.script_parser.rule_parser import RuleParserEngine
from penshot.neopen.agent.script_parser.script_parser_models import (
    ParsedScript,
    SceneInfo,
    CharacterInfo,
)
from penshot.utils.log_utils import print_log_exception


class ScriptParserTool:
    """
    剧本解析工具

    解析本身委托给 ``rule_parser.RuleParserEngine``，本类只保留解析入口与
    面向知识库的文档转换，维持 ``parse`` / ``create_documents`` 的原有契约。
    """

    def __init__(
        self,
        custom_patterns: Optional[Dict[str, re.Pattern]] = None,
        support_chinese: bool = True,
    ):
        """
        初始化解析器

        Args:
            custom_patterns: 保留参数，规则已由 YAML 词表驱动
            support_chinese: 保留参数，中文规则默认启用
        """
        self.custom_patterns = custom_patterns or {}
        self.support_chinese = support_chinese
        self._engine = RuleParserEngine()

    def parse(self, script_text: str) -> ParsedScript:
        """
        解析剧本文本，返回 ParsedScript 对象

        文本为空或未识别到场景时返回带 ``failed`` 标记的兜底结果；真正的
        解析异常向上抛出，由调用方决定降级策略。
        """
        try:
            debug("开始解析剧本文本")
            parsed_script = self._engine.parse(script_text)
            info(
                f"剧本解析完成: {len(parsed_script.scenes)}个场景, {len(parsed_script.characters)}个角色"
            )
            return parsed_script
        except Exception as e:
            print_log_exception()
            error(f"剧本解析失败: {str(e)}")
            raise

    def parse_file(self, file_path: str) -> ParsedScript:
        """从文件解析剧本"""
        try:
            debug(f"开始解析剧本文件: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                script_text = f.read()
            return self.parse(script_text)
        except FileNotFoundError:
            error(f"文件不存在: {file_path}")
            raise
        except Exception as e:
            error(f"解析文件失败: {file_path}, {str(e)}")
            raise

    def create_documents(self, parsed_script: ParsedScript) -> List[Document]:
        """从 ParsedScript 创建 Document 对象列表"""
        documents = []

        for scene in parsed_script.scenes:
            scene_content = self._scene_to_text(scene)
            scene_metadata = {
                "type": "scene",
                "scene_id": scene.id,
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "element_count": len(scene.elements),
            }
            documents.append(Document(text=scene_content, metadata=scene_metadata))

        for character in parsed_script.characters:
            character_content = self._character_to_text(character)
            character_metadata = {
                "type": "character",
                "character_name": character.name,
                "gender": character.gender,
                "role": character.role,
            }
            documents.append(
                Document(text=character_content, metadata=character_metadata)
            )

        info(f"从解析结果创建了 {len(documents)} 个文档")
        return documents

    def _scene_to_text(self, scene: SceneInfo) -> str:
        """将场景转换为文本"""
        from penshot.neopen.agent.base_models import ElementType

        content = f"场景 ID: {scene.id}\n地点: {scene.location}\n"
        if scene.time_of_day:
            content += f"时间: {scene.time_of_day}\n"
        if scene.description:
            content += f"描述: {scene.description}\n"
        content += "\n"

        for elem in scene.elements:
            if elem.type == ElementType.DIALOGUE:
                content += f"{elem.character}: {elem.content}\n\n"
            elif elem.type == ElementType.ACTION:
                content += f"{elem.content}\n\n"
            else:
                content += f"{elem.content}\n\n"

        return content

    def _character_to_text(self, character: CharacterInfo) -> str:
        """将角色转换为文本"""
        content = f"角色名称: {character.name}\n性别: {character.gender}\n类型: {character.role}\n"
        if character.description:
            content += f"描述: {character.description}\n"
        if character.key_traits:
            content += f"关键特征: {', '.join(character.key_traits)}\n"
        return content


# ========== 便捷函数 ==========


def parse_script_to_documents(script_text: str) -> Tuple[ParsedScript, List[Document]]:
    """解析剧本文本并创建文档对象"""
    parser = ScriptParserTool()
    parsed_script = parser.parse(script_text)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents


def parse_script_file_to_documents(
    file_path: str,
) -> Tuple[ParsedScript, List[Document]]:
    """解析剧本文件并创建文档对象"""
    parser = ScriptParserTool()
    parsed_script = parser.parse_file(file_path)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents
