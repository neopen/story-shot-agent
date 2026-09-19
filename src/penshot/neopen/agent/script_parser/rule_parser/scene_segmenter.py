"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: scene_segmenter.py
@Description: 场景切分与对话关联 - 把分类后的行序列组织成场景与元素草稿
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
    RuleVocabulary,
)
from penshot.neopen.agent.script_parser.rule_parser.line_classifiers import (
    compile_config_pattern,
)
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    ElementDraft,
    LineKind,
    LineToken,
    RuleDiagnostics,
    SceneDraft,
    SegmentResult,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import (
    char_count,
    clean_text,
    find_nearest_subject,
)
from penshot.neopen.agent.script_parser.script_parser_models import ElementType

# 首个场景标题之前的内容成为开场场景的最低动作文本长度
_PREAMBLE_MIN_CHARS = 20
# 无标题剧本按段落切分：实质段落的最低字数与最少段数
_PROSE_MIN_CHARS = 30
_PROSE_MIN_PARAGRAPHS = 3

# 章节目录（``## 三、技术参数建议``）：属于剧本之外的附录，其内容不参与场景识别
_NOTE_DOCUMENT = "document"
# 字段区域（``**关键道具：**``）：属于所在场景的场记，其值参与地点与氛围识别
_NOTE_FIELD = "field"

# 值即画面描述的字段：分镜脚本把镜头内容写在「画面：」里，这些值应当成为动作元素
_CONTENT_FIELD_LABELS = frozenset({"画面", "画面内容", "内容", "镜头内容"})


def _note_regions(tokens: Sequence[LineToken]) -> Dict[int, str]:
    """行号 -> 所属场记区域类型

    章节标题开启文档区域，标签行开启字段区域；两者都被下一个场景标题终止，
    因此剧本正文里的场景标题是唯一能结束场记段落的结构。文档区域一旦开启就
    不会被其内部的标签行降级——附录里的「**光线运用：**」仍属于附录。
    """
    regions: Dict[int, str] = {}
    region: Optional[str] = None
    for token in tokens:
        if token.kind is LineKind.SCENE_HEADING:
            region = None
            continue

        role = token.payload.get("role")
        if role == "section":
            region = _NOTE_DOCUMENT
        elif region is not _NOTE_DOCUMENT and role in ("metadata", "metadata_section"):
            region = _NOTE_FIELD
        elif role == "title":
            regions[token.index] = _NOTE_DOCUMENT
            continue

        if region is not None:
            regions[token.index] = region
    return regions


def metadata_spans(tokens: Sequence[LineToken]) -> Set[int]:
    """标记场记信息的行号，这些行不产生剧本元素"""
    return set(_note_regions(tokens))


def _iter_speech(text: str, vocabulary: RuleVocabulary) -> Iterator[Tuple[int, str]]:
    """产出文本中每处引号对话的起始下标与台词内容"""
    for pattern in vocabulary.dialogue_patterns:
        compiled = compile_config_pattern(pattern)
        if compiled is None:
            continue
        for match in compiled.finditer(text):
            content = (
                match.group(1).strip() if match.groups() else match.group(0).strip()
            )
            if content:
                yield match.start(), content


def _strip_speech(text: str, spans: Sequence[Tuple[int, str]]) -> str:
    """去掉引号台词后剩余的叙述文本"""
    if not spans:
        return text
    head = text[: spans[0][0]]
    tail = text[spans[-1][0] + len(spans[-1][1]) + 2 :]
    return clean_text(f"{head} {tail}")


class DialogueAssociator:
    """把场景内的行序列转换成元素草稿，负责对话与说话人的关联

    元素草稿只带内容、说话人与表演提示；时长、情绪、强度由 ElementBuilder 统一推断。
    """

    def __init__(self, vocabulary: RuleVocabulary) -> None:
        self._vocabulary = vocabulary

    def associate(
        self,
        tokens: Sequence[LineToken],
        spans: Set[int],
        diagnostics: RuleDiagnostics,
    ) -> List[ElementDraft]:
        """逐行产出元素草稿，返回顺序即剧本顺序"""
        drafts: List[ElementDraft] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.is_blank:
                index += 1
                continue
            if token.index in spans:
                # 「画面：空教室全景」这类字段的值本身就是镜头内容，仍要产出元素
                draft = self._content_field(token)
                if draft is not None:
                    drafts.append(draft)
                index += 1
                continue

            if token.kind is LineKind.PARENTHETICAL:
                drafts.append(self._parenthetical_draft(token))
                index += 1
                continue

            if token.kind is LineKind.TRANSITION:
                draft = self._transition_draft(token)
                if draft is not None:
                    drafts.append(draft)
                index += 1
                continue

            if token.kind is LineKind.CHARACTER:
                if token.payload.get("inline"):
                    drafts.append(self._inline_dialogue(token))
                    index += 1
                else:
                    block, index = self._absorb_cue_block(tokens, index, spans)
                    drafts.extend(block)
                continue

            drafts.extend(self._action_drafts(token))
            index += 1

        if not drafts:
            diagnostics.note("场景内没有产出任何元素")
        return drafts

    # ---------------------------- 单元元素 ----------------------------
    @staticmethod
    def _content_field(token: LineToken) -> Optional[ElementDraft]:
        """取「画面：」「内容：」这类字段的值作为动作元素，其余场记行返回 None"""
        if token.payload.get("role") != "metadata":
            return None
        if token.payload.get("label") not in _CONTENT_FIELD_LABELS:
            return None
        content = clean_text(token.payload.get("value") or "")
        if not content:
            return None
        return ElementDraft(
            type=ElementType.ACTION,
            content=content,
            source_line=token.index,
            confidence=0.65,
        )

    @staticmethod
    def _parenthetical_draft(token: LineToken) -> ElementDraft:
        """独立成行的括号说明折叠为动作元素"""
        inner = token.payload.get("text") or token.text
        return ElementDraft(
            type=ElementType.ACTION,
            content=inner,
            source_line=token.index,
            description=f"（{inner}）",
            confidence=0.6,
        )

    @staticmethod
    def _transition_draft(token: LineToken) -> Optional[ElementDraft]:
        """转场描述保留为动作元素；分隔线与结束标记不产生元素"""
        if token.payload.get("kind") in ("rule", "end"):
            return None
        return ElementDraft(
            type=ElementType.ACTION, content=token.text, source_line=token.index
        )

    @staticmethod
    def _inline_dialogue(token: LineToken) -> ElementDraft:
        """``名字（提示）：内容`` 直接产出一条对话"""
        description = token.payload.get("cue_description") or None
        return ElementDraft(
            type=ElementType.DIALOGUE,
            content=token.payload.get("inline_dialogue", ""),
            source_line=token.index,
            character=token.payload.get("name"),
            description=description,
            confidence=0.85,
        )

    def _action_drafts(self, token: LineToken) -> List[ElementDraft]:
        """动作行：整行是动作；行内引号对话且说话人可解析时拆出对话元素"""
        text = token.text
        speeches = list(_iter_speech(text, self._vocabulary))
        if not speeches:
            return [self._plain_action(token)]

        speaker = None
        for start, _ in speeches:
            speaker = find_nearest_subject(
                text, start, self._vocabulary.subject_verbs, strict=True
            )
            if speaker:
                break
        if not speaker:
            # 没有可解析的说话人，说明引号内容多半是标语、字条而非台词
            return [self._plain_action(token)]

        drafts: List[ElementDraft] = []
        outside = _strip_speech(text, speeches)
        if outside:
            drafts.append(
                ElementDraft(
                    type=ElementType.ACTION, content=outside, source_line=token.index
                )
            )
        for _, content in speeches:
            drafts.append(
                ElementDraft(
                    type=ElementType.DIALOGUE,
                    content=content,
                    source_line=token.index,
                    character=speaker,
                    confidence=0.7,
                )
            )
        return drafts

    @staticmethod
    def _plain_action(token: LineToken) -> ElementDraft:
        """整行作为动作元素，前导括号说明进入 description"""
        description = None
        if token.payload.get("description"):
            description = token.payload["description"]
        return ElementDraft(
            type=ElementType.ACTION,
            content=token.payload.get("content") or token.text,
            source_line=token.index,
            description=description,
            confidence=0.5,
        )

    def _absorb_cue_block(
        self,
        tokens: Sequence[LineToken],
        start: int,
        spans: Set[int],
    ) -> Tuple[List[ElementDraft], int]:
        """角色提示行吸收后续的括号说明与台词，直到空行/新提示/标题/转场"""
        cue = tokens[start]
        description: List[str] = []
        content: List[str] = []
        index = start + 1
        while index < len(tokens):
            token = tokens[index]
            if token.is_blank or token.index in spans:
                break
            if token.kind in (
                LineKind.CHARACTER,
                LineKind.SCENE_HEADING,
                LineKind.TRANSITION,
            ):
                break
            if token.kind is LineKind.PARENTHETICAL:
                description.append(f"（{token.payload.get('text') or token.text}）")
            else:
                content.append(clean_text(token.text))
            index += 1

        name = cue.payload.get("name") or cue.text
        if not content:
            # 提示行后面没有正文，降级为动作，避免裸人名凭空消失
            return [
                ElementDraft(
                    type=ElementType.ACTION,
                    content=cue.text,
                    source_line=cue.index,
                    character=name,
                    confidence=0.4,
                )
            ], index

        return [
            ElementDraft(
                type=ElementType.DIALOGUE,
                content=" ".join(content),
                source_line=cue.index,
                character=name,
                description="".join(description) or None,
                confidence=0.7,
            )
        ], index


class SceneSegmenter:
    """场景切分器：按场景标题划分场景，无标题时退化为按段落切分"""

    def __init__(self, vocabulary: RuleVocabulary) -> None:
        self._vocabulary = vocabulary
        self._associator = DialogueAssociator(vocabulary)

    def segment(
        self, tokens: List[LineToken], diagnostics: RuleDiagnostics
    ) -> SegmentResult:
        """切分场景并填充元素草稿"""
        title = self._extract_title(tokens)
        spans = metadata_spans(tokens)
        if not any(token.text for token in tokens):
            return SegmentResult(scenes=[], title=title, diagnostics=diagnostics)

        if any(token.kind is LineKind.SCENE_HEADING for token in tokens):
            scenes = self._build_from_headings(tokens, spans, diagnostics)
        else:
            scenes = self._build_from_paragraphs(tokens, spans, diagnostics)
        return SegmentResult(scenes=scenes, title=title, diagnostics=diagnostics)

    # ---------------------------- 标题驱动的切分 ----------------------------
    def _build_from_headings(
        self,
        tokens: Sequence[LineToken],
        spans: Set[int],
        diagnostics: RuleDiagnostics,
    ) -> List[SceneDraft]:
        scenes: List[SceneDraft] = []
        heading: Optional[LineToken] = None
        body: List[LineToken] = []
        for token in tokens:
            if token.kind is LineKind.SCENE_HEADING:
                self._flush(scenes, heading, body, spans, diagnostics)
                heading, body = token, []
            else:
                body.append(token)
        self._flush(scenes, heading, body, spans, diagnostics)
        return scenes

    def _flush(
        self,
        scenes: List[SceneDraft],
        heading: Optional[LineToken],
        body: List[LineToken],
        spans: Set[int],
        diagnostics: RuleDiagnostics,
    ) -> None:
        """把一组标题+正文落成一个场景；无标题组需通过开场场景门槛"""
        if heading is None and not body:
            return
        if heading is None and not self._qualifies_as_opening(body, spans):
            return
        scenes.append(
            self._make_scene(len(scenes) + 1, heading, body, spans, diagnostics)
        )

    def _qualifies_as_opening(self, body: Sequence[LineToken], spans: Set[int]) -> bool:
        """标题之前的正文只有含对话或足够长的动作描述时才成为开场场景"""
        for token in body:
            if token.is_blank or token.index in spans:
                continue
            if token.kind is LineKind.CHARACTER:
                return True
            if any(_iter_speech(token.text, self._vocabulary)):
                return True
        text = self._join_text(body, spans)
        return char_count(text) >= _PREAMBLE_MIN_CHARS

    # ---------------------------- 段落驱动的切分 ----------------------------
    def _build_from_paragraphs(
        self,
        tokens: Sequence[LineToken],
        spans: Set[int],
        diagnostics: RuleDiagnostics,
    ) -> List[SceneDraft]:
        paragraphs = self._paragraphs(tokens)
        substantial = [
            paragraph
            for paragraph in paragraphs
            if char_count(self._join_text(paragraph, spans)) >= _PROSE_MIN_CHARS
        ]
        groups = (
            substantial if len(substantial) >= _PROSE_MIN_PARAGRAPHS else [list(tokens)]
        )
        return [
            self._make_scene(index, None, body, spans, diagnostics)
            for index, body in enumerate(groups, start=1)
        ]

    @staticmethod
    def _paragraphs(tokens: Sequence[LineToken]) -> List[List[LineToken]]:
        """按空行切分出非空段落"""
        paragraphs: List[List[LineToken]] = []
        current: List[LineToken] = []
        for token in tokens:
            if token.is_blank:
                if current:
                    paragraphs.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            paragraphs.append(current)
        return paragraphs

    # ---------------------------- 公共辅助 ----------------------------
    def _make_scene(
        self,
        index: int,
        heading: Optional[LineToken],
        body: Sequence[LineToken],
        spans: Set[int],
        diagnostics: RuleDiagnostics,
    ) -> SceneDraft:
        scene = SceneDraft(
            index=index,
            id=f"scene_{index:03d}",
            heading=""
            if heading is None
            else (heading.payload.get("heading") or heading.text),
            heading_payload=dict(heading.payload) if heading is not None else {},
        )
        scene.body_text = self._join_text(body, spans)
        # 场记行不产生元素，但「画面：空教室全景」「关键道具：- 同学录」这类字段值
        # 仍要参与地点与氛围识别；文档附录里的说明性散文不属于任何场景
        regions = _note_regions(body)
        scene.meta_text = " ".join(
            token.text
            for token in body
            if token.text
            and not token.is_blank
            and regions.get(token.index) == _NOTE_FIELD
        )
        scene.drafts = self._associator.associate(body, spans, diagnostics)
        return scene

    @staticmethod
    def _join_text(
        tokens: Sequence[LineToken], spans: Optional[Set[int]] = None
    ) -> str:
        """拼接行文本，可选择排除场记行"""
        return " ".join(
            token.text
            for token in tokens
            if token.text and (spans is None or token.index not in spans)
        )

    @staticmethod
    def _extract_title(tokens: Sequence[LineToken]) -> Optional[str]:
        """取剧本标题，来源于《…》标题行或「剧本名称：」标签"""
        for token in tokens:
            if token.payload.get("role") == "title":
                return token.payload.get("title")
            if token.payload.get("role") == "metadata" and token.payload.get(
                "label"
            ) in (
                "剧本名称",
                "剧本",
                "片名",
                "题目",
            ):
                return token.payload.get("value") or None
        return None
