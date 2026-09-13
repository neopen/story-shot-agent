"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: script_parser_tool.py
@Description: 剧本语法解析器模块 - 支持中文剧本
@Author: NeoPen
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
    剧本语法解析器 - 支持中文剧本和标准好莱坞格式
    """

    # ========== 场景标题模式（支持中英文） ==========
    # 英文标准格式: INT. 房间 - 白天
    SCENE_HEADING_EN = re.compile(
        r'^(INT|EXT|INT\.|EXT\.|I/E)\.?\s+(.+?)(?:\s*[-–]\s*)?(DAY|NIGHT|DUSK|DAWN|MORNING|AFTERNOON|EVENING|白天|夜晚|黄昏|黎明|早晨|下午|傍晚)?$',
        re.IGNORECASE
    )

    # 中文格式1: 【场景1】房间 / 白天
    SCENE_HEADING_CN1 = re.compile(
        r'^[【\[]?场景\s*(\d+)[】\]]?\s*[:：]?\s*(.+?)(?:[\/\\]|\s+)(白天|夜晚|黄昏|黎明|早晨|下午|傍晚|室内|室外)?',
        re.IGNORECASE
    )

    # 中文格式2: 第一场 房间 白天
    SCENE_HEADING_CN2 = re.compile(
        r'^第\s*(\d+)\s*场\s*[:：]?\s*(.+?)(?:\s+(白天|夜晚|黄昏|黎明|早晨|下午|傍晚))?',
        re.IGNORECASE
    )

    # 中文格式3: 1. 房间 / 白天
    SCENE_HEADING_CN3 = re.compile(
        r'^(\d+)\.\s*(.+?)(?:\s+[\/\-]\s+)?(白天|夜晚|黄昏|黎明|早晨|下午|傍晚)?',
        re.IGNORECASE
    )

    # 通用场景标题（兜底）
    SCENE_HEADING_FALLBACK = re.compile(
        r'^(?:第\s*(\d+)\s*[场幕回]|(?:【\[?场景\]?】?\s*)?(\d+)[\.:：]?)\s*(.+)$',
        re.IGNORECASE
    )

    # ========== 角色名称模式 ==========
    # 英文角色名（全大写）
    CHARACTER_EN = re.compile(r'^[A-Z][A-Z\s\-]{1,20}$')

    # 中文角色名（2-4个中文字符，可选括号标注）
    CHARACTER_CN = re.compile(r'^[\u4e00-\u9fa5]{2,4}(?:\s*[（(][^）)]+[）)])?$')

    # 角色名+冒号格式（中文剧本常见）
    CHARACTER_WITH_COLON = re.compile(r'^([\u4e00-\u9fa5]{2,4}|[A-Z][a-z]+)\s*[:：]\s*$')

    # ========== 转场模式（中英文） ==========
    TRANSITION_PATTERNS = [
        re.compile(r'^(CUT TO:|DISSOLVE TO:|FADE OUT:|FADE IN:|SMASH CUT TO:)', re.IGNORECASE),
        re.compile(r'^(切换|淡入|淡出|叠化|黑场|白场)'),
        re.compile(r'^={3,}$'),  # 分隔线
        re.compile(r'^-{3,}$'),
    ]

    # ========== 括号说明模式（中英文） ==========
    PARENTHETICAL_EN = re.compile(r'^\([^)]+\)$')
    PARENTHETICAL_CN = re.compile(r'^[（(][^）)]+[）)]$')

    # ========== 动作描述触发词 ==========
    ACTION_TRIGGERS = [
        "镜头", "特写", "远景", "中景", "近景", "摇移", "推拉",
        "镜头", "画面", "背景", "音效", "音乐",
    ]

    def __init__(self, custom_patterns: Optional[Dict[str, re.Pattern]] = None,
                 support_chinese: bool = True):
        """
        初始化解析器

        Args:
            custom_patterns: 自定义正则表达式模式字典
            support_chinese: 是否支持中文格式
        """
        self.custom_patterns = custom_patterns or {}
        self.support_chinese = support_chinese

        # 解析状态
        self.scenes: List[SceneInfo] = []
        self.characters: Dict[str, CharacterInfo] = {}
        self.global_metadata = GlobalMetadata()

        # 临时存储
        self._current_scene: Optional[SceneInfo] = None
        self._current_element: Optional[Dict] = None
        self._element_sequence: int = 0

        # 统计
        self._debug_stats = {"total_lines": 0, "matched_scenes": 0, "matched_characters": 0}

    def parse(self, script_text: str) -> ParsedScript:
        """
        解析剧本文本，返回 ParsedScript 对象
        """
        try:
            debug("开始解析剧本文本")

            # 重置状态
            self._reset_state()

            lines = script_text.strip().split('\n')
            self._debug_stats["total_lines"] = len(lines)

            info(f"开始解析，共 {len(lines)} 行")

            scene_number = 0

            # 第一遍：识别行类型
            line_types = self._classify_lines(lines)

            # 第二遍：构建场景结构
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                line_type = line_types[i] if i < len(line_types) else "unknown"

                if not line:
                    self._finalize_current_element(i + 1)
                    i += 1
                    continue

                # 检查是否是场景标题
                scene_match, scene_num, scene_loc, scene_time = self._match_scene_heading(line)
                if scene_match:
                    # 结束前一个场景
                    self._finalize_current_scene()

                    # 开始新场景
                    scene_number += 1
                    actual_scene_num = scene_num or scene_number
                    self._start_new_scene(
                        heading=line,
                        location=scene_loc or line,
                        time_of_day=scene_time,
                        scene_number=actual_scene_num,
                        line_num=i + 1
                    )
                    self._debug_stats["matched_scenes"] += 1
                    i += 1
                    continue

                # 检查是否是角色对话
                character_name = self._match_character(line)
                if character_name:
                    # 处理角色对话
                    i = self._handle_character_line(
                        character_name, lines, i, line_types
                    )
                    continue

                # 检查是否是转场
                if self._match_transition(line):
                    self._handle_transition(line, i + 1)
                    i += 1
                    continue

                # 检查是否是括号说明
                if self._match_parenthetical(line):
                    self._handle_parenthetical(line, i + 1)
                    i += 1
                    continue

                # 否则视为动作描述
                self._handle_action(line, i + 1)
                i += 1

            # 处理最后一个场景和元素
            self._finalize_current_element(len(lines))
            self._finalize_current_scene()

            # 构建结果
            parsed_script = self._build_parsed_script()

            info(f"剧本解析完成: {len(parsed_script.scenes)}个场景, {len(parsed_script.characters)}个角色")
            debug(f"解析统计: {self._debug_stats}")

            return parsed_script

        except Exception as e:
            print_log_exception()
            error(f"剧本解析失败: {str(e)}")
            raise

    def _reset_state(self):
        """重置解析状态"""
        self.scenes = []
        self.characters = {}
        self._current_scene = None
        self._current_element = None
        self._element_sequence = 0
        self.global_metadata = GlobalMetadata()
        self._debug_stats = {"total_lines": 0, "matched_scenes": 0, "matched_characters": 0}

    def _classify_lines(self, lines: List[str]) -> List[str]:
        """预分类行类型（用于更准确的解析）"""
        line_types = []

        for line in lines:
            line = line.strip()
            if not line:
                line_types.append("empty")
            elif self._match_scene_heading(line)[0]:
                line_types.append("scene")
            elif self._match_character(line):
                line_types.append("character")
            elif self._match_transition(line):
                line_types.append("transition")
            elif self._match_parenthetical(line):
                line_types.append("parenthetical")
            else:
                line_types.append("action")

        return line_types

    def _match_scene_heading(self, line: str) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """
        匹配场景标题

        Returns:
            (是否匹配, 场景编号, 场景地点, 时间段)
        """
        # 英文格式
        match_en = self.SCENE_HEADING_EN.match(line)
        if match_en:
            location = match_en.group(2) or line
            time_of_day = match_en.group(3)
            return True, None, location, time_of_day

        if self.support_chinese:
            # 中文格式1: 【场景1】房间 / 白天
            match_cn1 = self.SCENE_HEADING_CN1.match(line)
            if match_cn1:
                scene_num = int(match_cn1.group(1))
                location = match_cn1.group(2)
                time_of_day = match_cn1.group(3)
                return True, scene_num, location, time_of_day

            # 中文格式2: 第一场 房间 白天
            match_cn2 = self.SCENE_HEADING_CN2.match(line)
            if match_cn2:
                scene_num = int(match_cn2.group(1))
                location = match_cn2.group(2)
                time_of_day = match_cn2.group(3)
                return True, scene_num, location, time_of_day

            # 中文格式3: 1. 房间 / 白天
            match_cn3 = self.SCENE_HEADING_CN3.match(line)
            if match_cn3:
                scene_num = int(match_cn3.group(1))
                location = match_cn3.group(2)
                time_of_day = match_cn3.group(3)
                return True, scene_num, location, time_of_day

            # 兜底格式
            match_fallback = self.SCENE_HEADING_FALLBACK.match(line)
            if match_fallback:
                scene_num = match_fallback.group(1) or match_fallback.group(2)
                location = match_fallback.group(3)
                if scene_num:
                    scene_num = int(scene_num)
                return True, scene_num, location, None

        return False, None, None, None

    def _match_character(self, line: str) -> Optional[str]:
        """
        匹配角色名称

        Returns:
            角色名或 None
        """
        # 英文格式
        if self.CHARACTER_EN.match(line):
            return line.strip()

        if self.support_chinese:
            # 中文格式: 角色名 + 冒号
            match_colon = self.CHARACTER_WITH_COLON.match(line)
            if match_colon:
                return match_colon.group(1)

            # 纯中文角色名
            if self.CHARACTER_CN.match(line):
                return line.strip()

        return None

    def _match_transition(self, line: str) -> bool:
        """匹配转场标记"""
        for pattern in self.TRANSITION_PATTERNS:
            if pattern.match(line):
                return True
        return False

    def _match_parenthetical(self, line: str) -> bool:
        """匹配括号说明"""
        if self.PARENTHETICAL_EN.match(line):
            return True
        if self.support_chinese and self.PARENTHETICAL_CN.match(line):
            return True
        return False

    def _start_new_scene(self, heading: str, location: str, time_of_day: Optional[str],
                         scene_number: int, line_num: int):
        """开始新场景"""
        scene_id = f"scene_{scene_number:03d}"

        # 清理位置描述
        location = re.sub(r'^(INT|EXT|INT\.|EXT\.|I/E)\.?\s*', '', location, flags=re.IGNORECASE)

        self._current_scene = SceneInfo(
            id=scene_id,
            location=location.strip(),
            description=heading,
            time_of_day=time_of_day,
            elements=[]
        )

        debug(f"识别到场景 {scene_number}: {heading[:50]} (行号: {line_num})")

    def _start_new_element(self, element_type: str, content: str, line_num: int,
                           metadata: Optional[Dict] = None):
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

            element = self._create_element_from_dict(self._current_element)

            if element and self._current_scene:
                self._current_scene.elements.append(element)

            self._current_element = None

    def _finalize_current_scene(self):
        """结束当前场景"""
        if self._current_scene:
            # 即使没有元素也保存场景
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

        # 估算持续时间
        duration = max(1.0, min(10.0, len(content) / 15.0))

        element_id = f"elem_{self._element_sequence:04d}"

        return BaseElement(
            id=element_id,
            type=elem_type,
            sequence=self._element_sequence,
            duration=duration,
            confidence=0.8,
            content=content,
            character=metadata.get("character"),
            target_character=metadata.get("target_character"),
            description=content[:100] if len(content) > 100 else content,
            intensity=metadata.get("intensity", 0.5),
            emotion=metadata.get("emotion", EmotionType.NEUTRAL.value),
            audio_context=metadata.get("audio_context")
        )

    def _handle_character_line(self, character_name: str, lines: List[str],
                               idx: int, line_types: List[str]) -> int:
        """处理角色对话行，返回下一个索引"""
        line_num = idx + 1

        # 添加角色
        self._add_character(character_name, line_num)

        # 收集对话内容
        dialogue_lines = []
        next_idx = idx + 1

        while next_idx < len(lines):
            next_line = lines[next_idx].strip()
            next_type = line_types[next_idx] if next_idx < len(line_types) else "unknown"

            # 遇到空行、场景、角色、转场、括号说明时结束对话
            if not next_line or next_type in ["scene", "character", "transition"]:
                break

            # 括号说明单独处理
            if next_type == "parenthetical":
                # 括号说明可以作为对话的一部分或单独元素
                dialogue_lines.append(next_line)
                next_idx += 1
                continue

            dialogue_lines.append(next_line)
            next_idx += 1

        if dialogue_lines:
            dialogue_content = '\n'.join(dialogue_lines)

            # 结束之前的元素
            self._finalize_current_element(line_num)

            # 开始新对话元素
            self._start_new_element(
                "dialogue",
                dialogue_content,
                line_num,
                {"character": character_name}
            )

            self._debug_stats["matched_characters"] += 1

        return next_idx

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
            self._current_element["content"] += '\n' + line
            self._current_element["end_line"] = line_num

    def _add_character(self, character_name: str, line_num: int):
        """添加角色信息"""
        if character_name not in self.characters:
            # 推断性别
            gender = "unknown"
            if any(kw in character_name for kw in ["小姐", "女士", "女", "妹", "姐", "母", "妈"]):
                gender = "female"
            elif any(kw in character_name for kw in ["先生", "男士", "男", "哥", "弟", "叔", "父", "爸"]):
                gender = "male"

            self.characters[character_name] = CharacterInfo(
                name=character_name,
                gender=gender,
                role="supporting",
                type=CharacterType.DEFAULT,
                description=None,
                key_traits=[]
            )
            debug(f"识别到角色: {character_name}")

    def _get_scene_characters(self) -> List[str]:
        """获取当前场景的角色列表"""
        if not self._current_scene:
            return []
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

        completeness_score = min(100.0, (len(self.scenes) / 20) * 100) if self.scenes else 0

        return ParsedScript(
            title=None,
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
                "parsed_at": None,
                "version": "1.0",
                "parser_type": "ScriptParserTool"
            }
        )

    def parse_file(self, file_path: str) -> ParsedScript:
        """从文件解析剧本"""
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
        """从 ParsedScript 创建 Document 对象列表"""
        documents = []

        for scene in parsed_script.scenes:
            scene_content = self._scene_to_text(scene)
            scene_metadata = {
                "type": "scene",
                "scene_id": scene.id,
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "element_count": len(scene.elements)
            }
            documents.append(Document(text=scene_content, metadata=scene_metadata))

        for character in parsed_script.characters:
            character_content = self._character_to_text(character)
            character_metadata = {
                "type": "character",
                "character_name": character.name,
                "gender": character.gender,
                "role": character.role
            }
            documents.append(Document(text=character_content, metadata=character_metadata))

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
    parser = ScriptParserTool(support_chinese=True)
    parsed_script = parser.parse(script_text)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents


def parse_script_file_to_documents(file_path: str) -> Tuple[ParsedScript, List[Document]]:
    """解析剧本文件并创建文档对象"""
    parser = ScriptParserTool(support_chinese=True)
    parsed_script = parser.parse_file(file_path)
    documents = parser.create_documents(parsed_script)
    return parsed_script, documents
