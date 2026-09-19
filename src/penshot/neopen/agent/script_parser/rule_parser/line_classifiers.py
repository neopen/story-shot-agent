"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: line_classifiers.py
@Description: 行分类器责任链 - 把剧本原文的每一行判定为标题/角色/转场/说明/动作
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

import re
from typing import Any, Dict, List, Optional

from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
    RuleVocabulary,
)
from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import LineClassifier
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    LineKind,
    LineMatch,
    LineToken,
    RuleDiagnostics,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import (
    NON_CHARACTER_WORDS,
    is_metadata_label,
    normalize_yaml_pattern,
)

# 行长度上限，超过则不可能视为标题
_MAX_HEADING_LENGTH = 50

_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?")
_HEADING_PREFIX_RE = re.compile(r"^(#{1,6})\s*")
_EMPHASIS_RE = re.compile(r"^([*_`~]{1,3})(.+?)\1$")
_BULLET_RE = re.compile(r"^([-*+]|\d+[.)])\s+")
_BRACKET_RE = re.compile(r"^[【\[](.+?)[】\]]$")
# 残留的强调标记：``**场景：** 值`` 这类只包住标签的写法不会被对称剥离
_RESIDUAL_EMPHASIS_RE = re.compile(r"\*{1,3}|_{2,}|`")
_HORIZONTAL_RULE_RE = re.compile(r"^(?:-{3,}|={3,}|\*{3,})$")

_TRANSITION_EN_RE = re.compile(
    r"^(CUT TO:|DISSOLVE TO:|FADE OUT:|FADE IN:|SMASH CUT TO:)", re.I
)
_TRANSITION_CN_RE = re.compile(r"^(切换|淡入|淡出|叠化|黑场|白场)")
_PARENTHETICAL_RE = re.compile(r"^[（(]([^）)]{1,40})[）)]$")
_LEADING_PARENTHETICAL_RE = re.compile(r"^[（(]([^）)]{1,40})[）)]\s*")
_CUE_PAREN_RE = re.compile(
    r"^([\u4e00-\u9fa5]{2,4}|[A-Z][A-Za-z]{1,20})\s*[（(]([^）)]{1,40})[）)]$"
)
_CUE_CJK_RE = re.compile(r"^[\u4e00-\u9fa5]{2,4}$")
_CUE_EN_RE = re.compile(r"^[A-Z][A-Z0-9\s\-]{1,20}$")
_INLINE_COLON_RE = re.compile(
    r"^(?P<name>[\u4e00-\u9fa5]{2,4}|[A-Z][A-Za-z]{1,20})\s*"
    r"(?:[（(](?P<desc>[^）)]{1,40})[）)])?\s*[:：]\s*(?P<content>.+)$"
)
_LABEL_RE = re.compile(r"^(?P<label>[^：:]{1,12})\s*[:：]\s*(?P<value>.*)$")
_TITLE_RE = re.compile(r"^《(?P<title>.{1,40})》$")
_SECTION_RE = re.compile(r"^(?P<num>[一二三四五六七八九十]+)\s*[、.．]\s*(?P<name>.+)$")

# 剧本结束标记，命中后不再产生内容
END_MARKER_TOKENS = frozenset(
    {"剧终", "全剧终", "完", "结束", "分镜剧本结束", "分镜脚本结束"}
)

_pattern_cache: Dict[str, Optional[re.Pattern]] = {}


def compile_config_pattern(pattern: str) -> Optional[re.Pattern]:
    """编译来自配置的正则，并缓存结果；非法模式返回 None"""
    if pattern in _pattern_cache:
        return _pattern_cache[pattern]
    compiled: Optional[re.Pattern]
    try:
        compiled = re.compile(normalize_yaml_pattern(pattern))
    except re.error:
        compiled = None
    _pattern_cache[pattern] = compiled
    return compiled


class ScriptTokenizer:
    """把剧本文本切分为 LineToken，并记录 Markdown 结构"""

    def tokenize(self, raw_text: str) -> List[LineToken]:
        """逐行切分并剥离 Markdown 前缀"""
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        tokens: List[LineToken] = []
        for index, line in enumerate(normalized.split("\n")):
            payload: Dict[str, Any] = {}
            text = self._normalize(line, payload)
            tokens.append(
                LineToken(
                    index=index,
                    raw=line.rstrip(),
                    text=text,
                    kind=LineKind.ACTION if text else LineKind.EMPTY,
                    payload=payload,
                )
            )
        return tokens

    @staticmethod
    def _normalize(raw: str, payload: Dict[str, Any]) -> str:
        """剥离引用、标题层级、项目符号与对称强调标记"""
        text = raw.strip()
        if not text:
            return ""

        match = _BLOCKQUOTE_RE.match(text)
        if match:
            payload["blockquote"] = True
            text = text[match.end() :].strip()

        match = _HEADING_PREFIX_RE.match(text)
        if match:
            payload["hash_level"] = len(match.group(1))
            text = text[match.end() :].strip()

        # 强调标记必须先于项目符号剥离，否则「**1. 教室 内 日**」的前导 * 会被当成列表符号
        match = _EMPHASIS_RE.match(text)
        if match:
            payload["emphasis"] = match.group(1)
            text = match.group(2).strip()

        if "*" in text or "`" in text or "__" in text:
            text = _RESIDUAL_EMPHASIS_RE.sub("", text).strip()
            if not text:
                return ""

        match = _BULLET_RE.match(text)
        if match:
            payload["bullet"] = True
            # 「1. 教室 内 日」这类编号分场与编号列表同形，保留前缀供标题规则再判断
            payload["bullet_prefix"] = match.group(1)
            text = text[match.end() :].strip()

        match = _BRACKET_RE.match(text)
        if match:
            payload["bracket"] = True
            text = match.group(1).strip()

        return text


def _heading_candidates(token: LineToken) -> List[str]:
    """标题匹配的候选文本：编号被当项目符号剥离时，还原带编号的写法"""
    prefix = token.payload.get("bullet_prefix")
    if prefix and prefix[:1].isdigit():
        return [f"{prefix} {token.text}", token.text]
    return [token.text]


class SceneHeadingClassifier(LineClassifier):
    """场景标题识别：按配置模式顺序匹配，抽取地点、时间与内外景"""

    @property
    def name(self) -> str:
        return "scene_heading"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        for candidate in _heading_candidates(token):
            for pattern in vocabulary.scene_start_patterns:
                payload = self._match_pattern(candidate, pattern)
                if payload is not None:
                    return LineMatch(
                        LineKind.SCENE_HEADING,
                        payload={"heading": candidate, **payload},
                        confidence=0.95,
                    )
        return None

    @staticmethod
    def _match_pattern(text: str, pattern: str) -> Optional[Dict[str, str]]:
        """用单个配置模式匹配整行，返回命名组；无命名组时退化为第一个捕获组为地点"""
        if not text or len(text) > _MAX_HEADING_LENGTH:
            return None
        compiled = compile_config_pattern(pattern)
        if compiled is None:
            return None
        match = compiled.match(text)
        if not match:
            return None

        groups = {key: value for key, value in match.groupdict().items() if value}
        if not groups:
            captured = [value for value in match.groups() if value]
            if captured:
                groups["location"] = captured[0]
        return groups


class TransitionClassifier(LineClassifier):
    """转场识别：分隔线、结束标记与转场词"""

    @property
    def name(self) -> str:
        return "transition"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        text = token.text
        if _HORIZONTAL_RULE_RE.match(text):
            return LineMatch(
                LineKind.TRANSITION, payload={"kind": "rule"}, confidence=1.0
            )

        if text in END_MARKER_TOKENS or (
            token.payload.get("bracket") and text in END_MARKER_TOKENS
        ):
            return LineMatch(
                LineKind.TRANSITION, payload={"kind": "end"}, confidence=1.0
            )

        if any(text == marker for marker in vocabulary.scene_end_patterns):
            return LineMatch(
                LineKind.TRANSITION, payload={"kind": "end"}, confidence=1.0
            )

        if len(text) <= 20:
            for pattern in vocabulary.scene_transition_patterns:
                compiled = compile_config_pattern(pattern)
                if compiled is not None and compiled.search(text):
                    return LineMatch(
                        LineKind.TRANSITION, payload={"kind": "cut"}, confidence=0.9
                    )
            if _TRANSITION_EN_RE.match(text) or _TRANSITION_CN_RE.match(text):
                return LineMatch(
                    LineKind.TRANSITION, payload={"kind": "cut"}, confidence=0.9
                )

        return None


class ParentheticalClassifier(LineClassifier):
    """独立成行的括号说明，如「（温和地）」「（画外音）」"""

    @property
    def name(self) -> str:
        return "parenthetical"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        match = _PARENTHETICAL_RE.match(token.text)
        if not match:
            return None
        inner = match.group(1).strip()
        return LineMatch(
            LineKind.PARENTHETICAL,
            payload={"text": inner, "voiceover": is_voiceover(inner, vocabulary)},
            confidence=0.9,
        )


class CharacterCueClassifier(LineClassifier):
    """角色提示行：``**陈老师**``、``林然（微笑）``、``林然``"""

    @property
    def name(self) -> str:
        return "character_cue"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        text = token.text
        if text in vocabulary.metadata_labels or text in NON_CHARACTER_WORDS:
            return None

        match = _CUE_PAREN_RE.match(text)
        if match:
            return LineMatch(
                LineKind.CHARACTER,
                payload={
                    "name": match.group(1),
                    "cue_description": match.group(2).strip(),
                    "provisional": True,
                },
                confidence=0.75,
            )

        if _CUE_CJK_RE.match(text):
            # 光秃秃的中文短行风险很高（「夕阳斜照」也是 4 个字），
            # 只在有强调标记或独立成段时才认作角色提示
            if not (token.payload.get("emphasis") or token.payload.get("blank_before")):
                return None
            return LineMatch(
                LineKind.CHARACTER,
                payload={"name": text, "cue_description": "", "provisional": True},
                confidence=0.6,
            )

        if _CUE_EN_RE.match(text):
            return LineMatch(
                LineKind.CHARACTER,
                payload={"name": text, "cue_description": "", "provisional": True},
                confidence=0.6,
            )

        return None


class ColonDialogueClassifier(LineClassifier):
    """行内对话：``名字：内容`` 与 ``名字（提示）：内容``"""

    @property
    def name(self) -> str:
        return "colon_dialogue"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        text = token.text
        if is_metadata_label(text, vocabulary.metadata_labels):
            return None

        match = _INLINE_COLON_RE.match(text)
        if not match:
            return None

        name = match.group("name")
        content = match.group("content").strip()
        if (
            not content
            or name in vocabulary.metadata_labels
            or name in NON_CHARACTER_WORDS
        ):
            return None

        return LineMatch(
            LineKind.CHARACTER,
            payload={
                "name": name,
                "cue_description": (match.group("desc") or "").strip(),
                "inline_dialogue": content,
                "inline": True,
            },
            confidence=0.85,
        )


class MetadataLabelClassifier(LineClassifier):
    """标题、章节与场记说明行，不产生剧本元素"""

    @property
    def name(self) -> str:
        return "metadata_label"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        text = token.text

        match = _TITLE_RE.match(text)
        if match:
            return LineMatch(
                LineKind.ACTION,
                payload={"role": "title", "title": match.group("title").strip()},
                confidence=0.9,
            )

        match = _SECTION_RE.match(text)
        if match and len(text) <= 30:
            return LineMatch(
                LineKind.ACTION,
                payload={"role": "section", "section": match.group("name").strip()},
                confidence=0.8,
            )

        # 「关键道具：」这类块标题，冒号后无内容
        if len(text) <= 20 and text.endswith(("：", ":")):
            return LineMatch(
                LineKind.ACTION,
                payload={
                    "role": "metadata_section",
                    "label": text.rstrip("：:").strip(),
                    "value": "",
                },
                confidence=0.8,
            )

        if is_metadata_label(text, vocabulary.metadata_labels):
            label_match = _LABEL_RE.match(text)
            if label_match:
                return LineMatch(
                    LineKind.ACTION,
                    payload={
                        "role": "metadata",
                        "label": label_match.group("label").strip(),
                        "value": label_match.group("value").strip(),
                    },
                    confidence=0.85,
                )

        return None


class ActionClassifier(LineClassifier):
    """兜底分类器：所有未被认领的行都是动作描述，永远不会返回 None"""

    @property
    def name(self) -> str:
        return "action"

    def match(
        self, token: LineToken, vocabulary: RuleVocabulary
    ) -> Optional[LineMatch]:
        text = token.text
        payload: Dict[str, Any] = {"content": text}

        match = _LEADING_PARENTHETICAL_RE.match(text)
        if match:
            inner = match.group(1).strip()
            payload["description"] = f"（{inner}）"
            payload["voiceover"] = is_voiceover(inner, vocabulary)
            payload["content"] = text[match.end() :].strip() or text

        return LineMatch(LineKind.ACTION, payload=payload, confidence=0.5)


def is_voiceover(inner: str, vocabulary: RuleVocabulary) -> bool:
    """判断括号内文本是否为画外音/旁白标记"""
    lowered = inner.lower()
    return any(marker in lowered for marker in vocabulary.voiceover_markers)


class LineClassifierChain:
    """责任链：按顺序询问各分类器，首个返回结果的胜出"""

    def __init__(self, classifiers: List[LineClassifier]) -> None:
        self._classifiers = list(classifiers)

    @property
    def names(self) -> List[str]:
        """链上分类器名称，顺序即优先级"""
        return [classifier.name for classifier in self._classifiers]

    def classify_all(
        self,
        tokens: List[LineToken],
        vocabulary: RuleVocabulary,
        diagnostics: RuleDiagnostics,
    ) -> List[LineToken]:
        """就地写入每个 token 的 kind 与 payload"""
        diagnostics.lines_total = len(tokens)
        self._annotate_blank_neighbours(tokens)
        for token in tokens:
            if token.is_blank:
                token.kind = LineKind.EMPTY
                diagnostics.record_hit(LineKind.EMPTY)
                continue
            for classifier in self._classifiers:
                match = classifier.match(token, vocabulary)
                if match is not None:
                    token.kind = match.kind
                    token.payload.update(match.payload)
                    diagnostics.record_hit(match.kind)
                    break
        return tokens

    @staticmethod
    def _annotate_blank_neighbours(tokens: List[LineToken]) -> None:
        """标记每行前后是否为空白行，供角色提示行判断是否独立成段"""
        last = len(tokens) - 1
        for index, token in enumerate(tokens):
            token.payload.setdefault(
                "blank_before", index == 0 or not tokens[index - 1].text
            )
            token.payload.setdefault(
                "blank_after", index == last or not tokens[index + 1].text
            )


def default_line_classifiers() -> List[LineClassifier]:
    """默认责任链，顺序即优先级，替换其中任一环即可扩展"""
    return [
        SceneHeadingClassifier(),
        TransitionClassifier(),
        ParentheticalClassifier(),
        CharacterCueClassifier(),
        ColonDialogueClassifier(),
        MetadataLabelClassifier(),
        ActionClassifier(),
    ]
