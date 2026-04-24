"""
@FileName: script_parser_tool.py
@Description: 剧本语法解析器模块
            提供自定义剧本格式的解析功能，支持场景、角色、对话、动作等元素的提取
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10 - 2025/11
"""
import re
from typing import Dict, List, Optional, Tuple

from llama_index.core.schema import Document

from penshot.logger import debug, info, error
from penshot.neopen.agent.script_parser.script_parser_models import (
    ParsedScript,
    SceneInfo,
    CharacterInfo,
    BaseElement,
    EmotionType,
    GlobalMetadata,
    CharacterType,
)
from penshot.utils.log_utils import print_log_exception


class ScriptParserTool:
    """
    自定义剧本语法解析器
    支持标准剧本格式和自定义扩展格式的解析
    """

    # 剧本元素的正则表达式模式
    SCENE_HEADING_PATTERN = re.compile(r'^(INT|EXT|INT\.|EXT\.|I/E)\.?\s+(.+)$', re.IGNORECASE)
    CHARACTER_PATTERN = re.compile(r'^[A-Z0-9\s\-]+(?::\s*[A-Z0-9\s\-]+)?$')
    TRANSITION_PATTERN = re.compile(r'^(CUT TO:|DISSOLVE TO:|FADE OUT:|FADE IN:|SMASH CUT TO:)$', re.IGNORECASE)
    PARENTHETICAL_PATTERN = re.compile(r'^\([^)]+\)$')

    def __init__(self, custom_patterns: Optional[Dict[str, re.Pattern]] = None):
        """
        初始化解析器

        Args:
            custom_patterns: 自定义正则表达式模式字典
        """
        self.custom_patterns = custom_patterns or {}

        # 解析状态
        self.scenes: List[SceneInfo] = []
        self.characters: Dict[str, CharacterInfo] = {}
        self.global_metadata = GlobalMetadata()

        # 临时存储用于构建
        self._current_scene: Optional[SceneInfo] = None
        self._current_element: Optional[Dict] = None
        self._element_sequence: int = 0

    def parse(self, script_text: str) -> ParsedScript:
        """
        解析剧本文本，返回 ParsedScript 对象

        Args:
            script_text: 剧本文本内容

        Returns:
            ParsedScript 对象
        """
        try:
            debug("开始解析剧本文本")

            # 重置解析状态
            self.scenes = []
            self.characters = {}
            self._current_scene = None
            self._current_element = None
            self._element_sequence = 0
            self.global_metadata = GlobalMetadata()

            lines = script_text.strip().split('\n')
            scene_number = 0

            # 逐行解析
            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                # 跳过空行
                if not line:
                    self._finalize_current_element(line_num)
                    continue

                # 检查是否是场景标题
                scene_heading_match = self.SCENE_HEADING_PATTERN.match(line)
                if scene_heading_match:
                    # 结束前一个场景
                    self._finalize_current_scene()

                    # 开始新场景
                    scene_number += 1
                    self._start_new_scene(line, scene_heading_match, scene_number, line_num)
                    continue

                # 检查是否是角色对话
                if self._is_character_line(line):
                    self._handle_character_line(line, lines, line_num)
                    continue

                # 检查是否是转场
                if self.TRANSITION_PATTERN.match(line):
                    self._handle_transition(line, line_num)
                    continue

                # 检查是否是括号说明
                if self.PARENTHETICAL_PATTERN.match(line):
                    self._handle_parenthetical(line, line_num)
                    continue

                # 否则视为动作描述
                self._handle_action(line, line_num)

            # 处理最后一个场景和元素
            self._finalize_current_element(len(lines))
            self._finalize_current_scene()

            # 构建 ParsedScript 对象
            parsed_script = self._build_parsed_script()

            info(f"剧本解析完成: {len(parsed_script.scenes)}个场景, {len(parsed_script.characters)}个角色")
            return parsed_script

        except Exception as e:
            print_log_exception()
            error(f"剧本解析失败: {str(e)}")
            raise

    def _start_new_scene(self, line: str, match: re.Match, scene_number: int, line_num: int):
        """开始新场景"""
        heading_text = line
        location_type = match.group(1)
        location_info = match.group(2)

        # 尝试提取时间信息
        time_of_day = None
        time_match = re.search(r'(?:\s|\()(DAY|NIGHT|DUSK|DAWN|MORNING|AFTERNOON|EVENING)(?:\)|\s|$)',
                               location_info, re.IGNORECASE)
        if time_match:
            time_of_day = time_match.group(1).upper()

        # 创建场景
        scene_id = f"scene_{scene_number:03d}"
        self._current_scene = SceneInfo(
            id=scene_id,
            location=f"{location_type}. {location_info}",
            description=heading_text,
            time_of_day=time_of_day,
            elements=[]
        )

        debug(f"识别到场景 {scene_number}: {heading_text} (行号: {line_num})")

    def _start_new_element(self, element_type: str, content: str, line_num: int, metadata: Optional[Dict] = None):
        """开始新元素"""
        self._element_sequence += 1
        self._current_element = {
            "type": element_type,
            "content": content,
            "start_line": line_num,
            "end_line": line_num,
            "metadata": metadata or {},
            "sequence": self._element_sequence
        }

    def _finalize_current_element(self, line_num: int):
        """结束当前元素"""
        if self._current_element:
            self._current_element["end_line"] = line_num - 1

            # 转换为 BaseElement 对象
            element = self._create_element_from_dict(self._current_element)

            if element and self._current_scene:
                self._current_scene.elements.append(element)

            self._current_element = None

    def _finalize_current_scene(self):
        """结束当前场景"""
        if self._current_scene and self._current_scene.elements:
            self.scenes.append(self._current_scene)
            self._current_scene = None

    def _create_element_from_dict(self, element_dict: Dict) -> Optional[BaseElement]:
        """从字典创建 BaseElement 对象"""
        from penshot.neopen.agent.base_models import ElementType

        element_type = element_dict["type"]
        content = element_dict["content"]
        metadata = element_dict.get("metadata", {})

        # 确定元素类型
        if element_type == "dialogue":
            elem_type = ElementType.DIALOGUE
        elif element_type == "action":
            elem_type = ElementType.ACTION
        else:
            elem_type = ElementType.SCENE

        # 估算持续时间（基于内容长度）
        duration = max(1.0, len(content) / 15.0)  # 粗略估算：每15个字符1秒

        # 创建 BaseElement
        element_id = f"elem_{self._element_sequence:04d}"

        return BaseElement(
            id=element_id,
            type=elem_type,
            sequence=self._element_sequence,
            duration=min(duration, 10.0),  # 最大10秒
            confidence=0.8,
            content=content,
            character=metadata.get("character"),
            target_character=metadata.get("target_character"),
            description=content[:100] if len(content) > 100 else content,
            intensity=metadata.get("intensity", 0.5),
            emotion=metadata.get("emotion", EmotionType.NEUTRAL.value),
            audio_context=metadata.get("audio_context")
        )

    def _handle_character_line(self, line: str, lines: List[str], line_num: int):
        """处理角色对话行"""
        character_name = line.strip()

        # 添加角色
        self._add_character(character_name, line_num)

        # 如果当前场景存在，添加角色
        if self._current_scene and character_name not in self._get_scene_characters():
            # 角色会在场景的元素中体现，不需要单独存储
            pass

        # 检查下一行是否是对话
        dialogue_lines = []
        dialogue_start = line_num + 1
        dialogue_end = dialogue_start

        while dialogue_end <= len(lines):
            next_line = lines[dialogue_end - 1].strip()
            # 如果下一行是空行、场景标题、角色名称或转场，结束对话
            if not next_line or \
                    self.SCENE_HEADING_PATTERN.match(next_line) or \
                    self._is_character_line(next_line) or \
                    self.TRANSITION_PATTERN.match(next_line) or \
                    self.PARENTHETICAL_PATTERN.match(next_line):
                break
            dialogue_lines.append(next_line)
            dialogue_end += 1

        if dialogue_lines:
            dialogue_content = '\n'.join(dialogue_lines)

            # 更新角色对话计数
            if character_name in self.characters:
                # 可以在 CharacterInfo 中添加 dialogue_count 字段
                pass

            # 开始新对话元素
            self._finalize_current_element(line_num)
            self._start_new_element(
                "dialogue",
                dialogue_content,
                line_num,
                {"character": character_name}
            )

            # 跳过已处理的对话行
            for _ in range(dialogue_end - line_num - 1):
                pass

    def _handle_transition(self, line: str, line_num: int):
        """处理转场"""
        self._finalize_current_element(line_num)
        self._start_new_element("transition", line, line_num)

    def _handle_parenthetical(self, line: str, line_num: int):
        """处理括号说明"""
        self._finalize_current_element(line_num)
        self._start_new_element("parenthetical", line, line_num)

    def _handle_action(self, line: str, line_num: int):
        """处理动作描述"""
        if not self._current_element or self._current_element["type"] != "action":
            self._finalize_current_element(line_num)
            self._start_new_element("action", line, line_num)
        else:
            # 继续上一个动作描述
            self._current_element["content"] += '\n' + line
            self._current_element["end_line"] = line_num

    def _is_character_line(self, line: str) -> bool:
        """
        判断是否是角色名称行

        Args:
            line: 文本行

        Returns:
            是否是角色名称行
        """
        # 角色名称通常全大写，可能包含空格、连字符和数字
        if not line.isupper():
            return False

        # 排除括号说明
        if self.PARENTHETICAL_PATTERN.match(line):
            return False

        # 应用角色名称模式
        if self.CHARACTER_PATTERN.match(line):
            # 排除太短的行，避免误判
            words = line.split()
            if len(words) == 1 and len(line) < 2:
                return False
            return True

        return False

    def _add_character(self, character_name: str, line_num: int):
        """
        添加角色信息

        Args:
            character_name: 角色名称
            line_num: 行号
        """
        if character_name not in self.characters:
            # 尝试推断角色性别（基于名称中的常见字）
            gender = "unknown"
            if any(keyword in character_name for keyword in ["小姐", "女士", "女", "妹", "姐"]):
                gender = "female"
            elif any(keyword in character_name for keyword in ["先生", "男士", "男", "哥", "弟", "叔"]):
                gender = "male"

            self.characters[character_name] = CharacterInfo(
                name=character_name,
                gender=gender,
                role="supporting",  # 默认为配角，后续可优化
                type=CharacterType.DEFAULT,
                description=None,
                key_traits=[]
            )

    def _get_scene_characters(self) -> List[str]:
        """获取当前场景的角色列表"""
        if not self._current_scene:
            return []
        # 从场景元素中提取角色
        characters = set()
        for elem in self._current_scene.elements:
            if hasattr(elem, 'character') and elem.character:
                characters.add(elem.character)
        return list(characters)

    def _build_parsed_script(self) -> ParsedScript:
        """构建 ParsedScript 对象"""
        from penshot.neopen.agent.base_models import ElementType

        # 计算统计数据
        total_elements = 0
        total_duration = 0.0
        dialogue_count = 0
        action_count = 0

        for scene in self.scenes:
            for elem in scene.elements:
                total_elements += 1
                total_duration += elem.duration
                if elem.type == ElementType.DIALOGUE:
                    dialogue_count += 1
                elif elem.type == ElementType.ACTION:
                    action_count += 1

        # 计算完整性评分
        completeness_score = min(100.0, (len(self.scenes) / 10) * 100) if self.scenes else 0

        return ParsedScript(
            title=None,  # 可从剧本中提取
            characters=list(self.characters.values()),
            scenes=self.scenes,
            global_metadata=self.global_metadata,
            stats={
                "total_elements": total_elements,
                "total_duration": total_duration,
                "dialogue_count": dialogue_count,
                "action_count": action_count,
                "completeness_score": completeness_score,
                "scene_count": len(self.scenes),
                "character_count": len(self.characters)
            },
            metadata={
                "parsed_at": None,  # 将在模型中自动填充
                "version": "1.0",
                "parser_type": "ScriptParserTool"
            }
        )

    def parse_file(self, file_path: str) -> ParsedScript:
        """
        从文件解析剧本

        Args:
            file_path: 文件路径

        Returns:
            ParsedScript 对象
        """
        try:
            debug(f"开始解析剧本文件: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                script_text = f.read()

            return self.parse(script_text)

        except FileNotFoundError:
            error(f"文件不存在: {file_path}")
            raise
        except Exception as e:
            error(f"解析文件失败: {file_path}, {str(e)}")
            raise

    def create_documents(self, parsed_script: ParsedScript) -> List[Document]:
        """
        从 ParsedScript 对象创建 Document 对象列表（用于 LlamaIndex）

        Args:
            parsed_script: ParsedScript 对象

        Returns:
            Document 对象列表
        """
        documents = []

        try:
            # 为每个场景创建文档
            for scene in parsed_script.scenes:
                scene_content = self._scene_to_text(scene)

                scene_metadata = {
                    "type": "scene",
                    "scene_id": scene.id,
                    "location": scene.location,
                    "time_of_day": scene.time_of_day,
                    "element_count": len(scene.elements)
                }

                scene_doc = Document(
                    text=scene_content,
                    metadata=scene_metadata
                )
                documents.append(scene_doc)

            # 为每个角色创建文档
            for character in parsed_script.characters:
                character_content = self._character_to_text(character)

                character_metadata = {
                    "type": "character",
                    "character_name": character.name,
                    "gender": character.gender,
                    "role": character.role
                }

                character_doc = Document(
                    text=character_content,
                    metadata=character_metadata
                )
                documents.append(character_doc)

            info(f"从解析结果创建了 {len(documents)} 个文档")
            return documents

        except Exception as e:
            error(f"创建文档失败: {str(e)}")
            raise

    def _scene_to_text(self, scene: SceneInfo) -> str:
        """将场景转换为文本"""
        from penshot.neopen.agent.base_models import ElementType

        content = f"场景 ID: {scene.id}\n"
        content += f"地点: {scene.location}\n"
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
        content = f"角色名称: {character.name}\n"
        content += f"性别: {character.gender}\n"
        content += f"类型: {character.role}\n"
        if character.description:
            content += f"描述: {character.description}\n"
        if character.key_traits:
            content += f"关键特征: {', '.join(character.key_traits)}\n"
        return content


# ========== 便捷函数 ==========

def parse_script_to_documents(script_text: str) -> Tuple[ParsedScript, List[Document]]:
    """
    解析剧本文本并创建文档对象

    Args:
        script_text: 剧本文本

    Returns:
        (ParsedScript 对象, 文档列表) 元组
    """
    parser = ScriptParserTool()
    parsed_script = parser.parse(script_text)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents


def parse_script_file_to_documents(file_path: str) -> Tuple[ParsedScript, List[Document]]:
    """
    解析剧本文件并创建文档对象

    Args:
        file_path: 文件路径

    Returns:
        (ParsedScript 对象, 文档列表) 元组
    """
    parser = ScriptParserTool()
    parsed_script = parser.parse_file(file_path)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents
