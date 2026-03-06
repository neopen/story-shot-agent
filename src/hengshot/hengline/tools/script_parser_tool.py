"""
@FileName: script_parser_agent.py
@Description: 剧本语法解析器模块
            提供自定义剧本格式的解析功能，支持场景、角色、对话、动作等元素的提取
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import re
from dataclasses import asdict
from typing import Dict, List, Optional, Any, Tuple

from llama_index.core.schema import Document

from hengshot.hengline.agent.script_parser2.script_parser_models import Character, Scene, Action
from hengshot.logger import debug, info, error
from hengshot.utils.log_utils import print_log_exception



class ScriptParserTool:
    """
    自定义剧本语法解析器
    支持标准剧本格式和自定义扩展格式的解析
    """

    # 剧本元素的正则表达式模式
    SCENE_HEADING_PATTERN = re.compile(r'^(INT|EXT|INT\.|EXT\.|I/E)\.?\s+(.+)$', re.IGNORECASE)
    CHARACTER_PATTERN = re.compile(r'^[A-Z0-9\s\-]+(?::\s*[A-Z0-9\s\-]+)?$')
    TRANSITION_PATTERN = re.compile(r'^(CUT TO:|DISSOLVE TO:|FADE OUT:|FADE IN:|SMASH CUT TO:)$', re.IGNORECASE)

    def __init__(self, custom_patterns: Optional[Dict[str, re.Pattern]] = None):
        """
        初始化解析器
        
        Args:
            custom_patterns: 自定义正则表达式模式字典
        """
        self.custom_patterns = custom_patterns or {}

    def parse(self, script_text: str) -> Dict[str, Any]:
        """
        解析剧本文本
        
        Args:
            script_text: 剧本文本内容
            
        Returns:
            解析结果字典，包含scenes、characters等信息
        """
        try:
            debug("开始解析剧本文本")

            # 重置解析状态
            self.scenes = []
            self.characters = {}
            self.elements = []

            lines = script_text.strip().split('\n')
            current_scene = None
            current_element = None
            scene_number = 0

            # 逐行解析
            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                # 跳过空行
                if not line:
                    # 如果有正在进行的元素，结束它
                    if current_element:
                        current_element.end_line = line_num - 1
                        if current_scene:
                            current_scene.elements.append(current_element)
                        self.elements.append(current_element)
                        current_element = None
                    continue

                # 检查是否是场景标题
                scene_heading_match = self.SCENE_HEADING_PATTERN.match(line)
                if scene_heading_match:
                    # 结束前一个场景
                    if current_scene:
                        current_scene.end_line = line_num - 1
                        if current_element:
                            current_element.end_line = line_num - 1
                            current_scene.elements.append(current_element)
                            self.elements.append(current_element)
                            current_element = None

                    # 开始新场景
                    scene_number += 1
                    heading_text = line

                    # 解析场景信息
                    location_type = scene_heading_match.group(1)
                    location_info = scene_heading_match.group(2)

                    # 尝试提取时间信息
                    time_of_day = None
                    time_match = re.search(r'(?:\s|\()(DAY|NIGHT|DUSK|DAWN|MORNING|AFTERNOON|EVENING)(?:\)|\s|$)', location_info, re.IGNORECASE)
                    if time_match:
                        time_of_day = time_match.group(1).upper()

                    current_scene = Scene(
                        heading=heading_text,
                        number=scene_number,
                        location=f"{location_type}. {location_info}",
                        time_of_day=time_of_day,
                        start_line=line_num
                    )
                    self.scenes.append(current_scene)

                    debug(f"识别到场景: {heading_text} (行号: {line_num})")
                    continue

                # 检查是否是角色对话
                if self._is_character_line(line) and line_num < len(lines):
                    # 检查下一行是否是对话内容或括号说明
                    next_line = lines[line_num].strip() if line_num < len(lines) else ""

                    # 如果下一行以括号开头，这可能是对话前的说明
                    if next_line.startswith('(') and ')' in next_line:
                        # 这是角色名称和括号说明
                        character_name = line.strip()
                        self._add_character(character_name, line_num)
                        if current_scene and character_name not in current_scene.characters:
                            current_scene.characters.append(character_name)

                        # 创建括号说明元素
                        current_element = SceneElement(
                            type="parenthetical",
                            content=next_line,
                            start_line=line_num + 1,
                            end_line=line_num + 1,
                            metadata={"character": character_name}
                        )
                        continue

                    # 这可能是角色名称，接下来是对话
                    character_name = line.strip()
                    self._add_character(character_name, line_num)
                    if current_scene and character_name not in current_scene.characters:
                        current_scene.characters.append(character_name)

                    # 检查下一行是否是对话
                    dialogue_lines = []
                    dialogue_start = line_num + 1
                    dialogue_end = line_num + 1

                    while dialogue_end <= len(lines):
                        if dialogue_end > len(lines):
                            break
                        next_content_line = lines[dialogue_end - 1].strip()
                        # 如果下一行是空行、场景标题、角色名称或转场，结束对话
                        if not next_content_line or \
                                self.SCENE_HEADING_PATTERN.match(next_content_line) or \
                                self._is_character_line(next_content_line) or \
                                self.TRANSITION_PATTERN.match(next_content_line):
                            break
                        dialogue_lines.append(next_content_line)
                        dialogue_end += 1

                    if dialogue_lines:
                        # 创建对话元素
                        dialogue_content = '\n'.join(dialogue_lines)
                        current_element = SceneElement(
                            type="dialogue",
                            content=dialogue_content,
                            start_line=dialogue_start,
                            end_line=dialogue_end - 1,
                            metadata={"character": character_name}
                        )

                        # 更新角色对话计数
                        if character_name in self.characters:
                            self.characters[character_name].dialogue_count += 1

                        # 跳过已处理的对话行
                        line_num = dialogue_end - 1
                    continue

                # 检查是否是转场
                if self.TRANSITION_PATTERN.match(line):
                    if current_element:
                        current_element.end_line = line_num - 1
                        if current_scene:
                            current_scene.elements.append(current_element)
                        self.elements.append(current_element)

                    current_element = SceneElement(
                        type="transition",
                        content=line,
                        start_line=line_num,
                        end_line=line_num
                    )
                    continue

                # 检查是否是括号说明
                if line.startswith('(') and ')' in line:
                    if current_element:
                        current_element.end_line = line_num - 1
                        if current_scene:
                            current_scene.elements.append(current_element)
                        self.elements.append(current_element)

                    current_element = SceneElement(
                        type="parenthetical",
                        content=line,
                        start_line=line_num,
                        end_line=line_num
                    )
                    continue

                # 否则视为动作描述
                if not current_element or current_element.type != "action":
                    if current_element:
                        current_element.end_line = line_num - 1
                        if current_scene:
                            current_scene.elements.append(current_element)
                        self.elements.append(current_element)

                    current_element = Action(
                        type="action",
                        content=line,
                        start_line=line_num,
                        end_line=line_num
                    )
                else:
                    # 继续上一个动作描述
                    current_element.content += '\n' + line
                    current_element.end_line = line_num

            # 处理最后一个元素
            if current_element:
                current_element.end_line = len(lines)
                if current_scene:
                    current_scene.elements.append(current_element)
                self.elements.append(current_element)

            # 处理最后一个场景
            if current_scene:
                current_scene.end_line = len(lines)

            # 更新角色的场景信息
            for scene in self.scenes:
                for character_name in scene.characters:
                    if character_name in self.characters and scene.heading not in self.characters[character_name].scenes:
                        self.characters[character_name].scenes.append(scene.heading)

            info(f"剧本解析完成: {len(self.scenes)}个场景, {len(self.characters)}个角色, {len(self.elements)}个元素")

            return {
                "scenes": [asdict(scene) for scene in self.scenes],
                "characters": {name: asdict(char) for name, char in self.characters.items()},
                "elements": [asdict(element) for element in self.elements],
                "total_lines": len(lines),
                "stats": {
                    "scene_count": len(self.scenes),
                    "character_count": len(self.characters),
                    "element_count": len(self.elements)
                }
            }

        except Exception as e:
            print_log_exception()
            error(f"剧本解析失败: {str(e)}")
            raise

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
            self.characters[character_name] = Character(
                name=character_name,
                first_appearance=line_num
            )

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        从文件解析剧本
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析结果字典
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

    def create_documents(self, parsed_result: Dict[str, Any]) -> List[Document]:
        """
        从解析结果创建Document对象列表
        
        Args:
            parsed_result: 解析结果字典
            
        Returns:
            Document对象列表
        """
        documents = []

        try:
            # 为每个场景创建文档
            for scene_data in parsed_result.get("scenes", []):
                # 构建场景内容
                scene_content = f"场景标题: {scene_data['heading']}\n"
                scene_content += f"场景编号: {scene_data['number']}\n"
                if scene_data.get('location'):
                    scene_content += f"地点: {scene_data['location']}\n"
                if scene_data.get('time_of_day'):
                    scene_content += f"时间: {scene_data['time_of_day']}\n"
                scene_content += f"出场角色: {', '.join(scene_data.get('characters', []))}\n\n"

                # 添加场景元素内容
                for element in scene_data.get('elements', []):
                    element_type = element['type']
                    content = element['content']

                    if element_type == 'dialogue':
                        character = element.get('metadata', {}).get('character', '未知角色')
                        scene_content += f"{character}:\n{content}\n\n"
                    elif element_type == 'parenthetical':
                        scene_content += f"{content}\n"
                    elif element_type == 'action':
                        scene_content += f"{content}\n\n"
                    elif element_type == 'transition':
                        scene_content += f"{content}\n\n"

                # 创建场景文档
                scene_metadata = {
                    "type": "scene",
                    "scene_number": scene_data['number'],
                    "scene_heading": scene_data['heading'],
                    "location": scene_data.get('location'),
                    "time_of_day": scene_data.get('time_of_day'),
                    "start_line": scene_data['start_line'],
                    "end_line": scene_data['end_line'],
                    "characters": scene_data.get('characters', [])
                }

                scene_doc = Document(
                    text=scene_content,
                    metadata=scene_metadata
                )
                documents.append(scene_doc)

            # 为每个角色创建文档
            for character_name, character_data in parsed_result.get("characters", {}).items():
                character_content = f"角色名称: {character_name}\n"
                character_content += f"对话次数: {character_data['dialogue_count']}\n"
                character_content += f"首次出现: 第{character_data['first_appearance']}行\n"
                character_content += f"出场场景: {len(character_data['scenes'])}个\n\n"

                # 列出角色出场的场景
                character_content += "出场场景列表:\n"
                for scene in character_data['scenes']:
                    character_content += f"- {scene}\n"

                character_metadata = {
                    "type": "character",
                    "character_name": character_name,
                    "dialogue_count": character_data['dialogue_count'],
                    "first_appearance": character_data['first_appearance'],
                    "scene_count": len(character_data['scenes']),
                    "scenes": character_data['scenes']
                }

                character_doc = Document(
                    text=character_content,
                    metadata=character_metadata
                )
                documents.append(character_doc)

            info(f"从解析结果创建了{len(documents)}个文档")
            return documents

        except Exception as e:
            error(f"创建文档失败: {str(e)}")
            raise


def parse_script_to_documents(script_text: str) -> Tuple[Dict[str, Any], List[Document]]:
    """
    解析剧本文本并创建文档对象
    
    Args:
        script_text: 剧本文本
        
    Returns:
        (解析结果, 文档列表)元组
    """
    parser = ScriptParserTool()
    parsed_result = parser.parse(script_text)
    documents = parser.create_documents(parsed_result)
    return parsed_result, documents


def parse_script_file_to_documents(file_path: str) -> Tuple[Dict[str, Any], List[Document]]:
    """
    解析剧本文件并创建文档对象
    
    Args:
        file_path: 文件路径
        
    Returns:
        (解析结果, 文档列表)元组
    """
    parser = ScriptParserTool()
    parsed_result = parser.parse_file(file_path)
    documents = parser.create_documents(parsed_result)
    return parsed_result, documents
