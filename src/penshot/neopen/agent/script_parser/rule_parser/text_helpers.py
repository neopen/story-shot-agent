"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: text_helpers.py
@Description: 规则解析器共用的文本处理与推断工具
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

import re
from functools import lru_cache
from typing import Collection, Dict, List, Optional, Sequence

# 小句边界，用于在长句中切出「主语 + 动作」所在的小句
CLAUSE_DELIMITERS = frozenset("。！？；，、,;!?\n \t—…“”\"'（）()【】")

# 并非角色名的常见词：动作句主语识别的停用词
NON_CHARACTER_WORDS = frozenset(
    {
        "这里",
        "那里",
        "此时",
        "此刻",
        "忽然",
        "突然",
        "一下",
        "两人",
        "目光",
        "声音",
        "窗外",
        "旁边",
        "身后",
        "眼前",
        "空气",
        "夕阳",
        "阳光",
        "同学",
        "大家",
        "对方",
        "自己",
        "他们",
        "她们",
        "我们",
        "你们",
        "教室",
        "走廊",
        "门口",
        "手机",
        "篮球",
    }
)

_MALE_KEYWORDS = ["先生", "男士", "哥", "弟", "叔", "伯", "公", "爷", "爸", "爹", "他"]
_FEMALE_KEYWORDS = ["小姐", "女士", "姐", "妹", "姨", "姑", "妈", "娘", "她"]

# 姓名不可能出现的结尾：副词/结构助词/动态助词
_NAME_REJECT_SUFFIXES = ("地", "的", "得", "了", "着", "过", "也", "都", "就")
# 姓名不可能出现的开头：副词
_NAME_REJECT_PREFIXES = (
    "也",
    "又",
    "都",
    "就",
    "还",
    "才",
    "便",
    "却",
    "更",
    "再",
    "刚",
    "正",
    "很",
    "太",
)

_MARKDOWN_WRAP_RE = re.compile(r"^[*_`~]{1,3}(.+?)[*_`~]{1,3}$")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fa5]+")


def normalize_yaml_pattern(pattern: str) -> str:
    """还原 YAML 中被重复转义的正则

    YAML 单引号标量不做转义处理，写成 `'[\\s\\S]'` 会得到两个反斜杠，
    正则里 `\\\\s` 匹配的是「反斜杠 + s」而非空白符，因此统一折叠为单反斜杠。
    """
    return pattern.replace("\\\\", "\\")


def strip_markdown(text: str) -> str:
    """去除对称的 Markdown 强调标记（**粗体**、*斜体*、`代码`）"""
    stripped = text.strip()
    match = _MARKDOWN_WRAP_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def char_count(text: str) -> int:
    """统计有效字符数（忽略空白），用于估算时长"""
    return len(_WHITESPACE_RE.sub("", text))


def split_sentences(text: str) -> List[str]:
    """按中文/英文句末标点切分句子，保留标点"""
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def clean_text(text: str) -> str:
    """去除 Markdown 标记与多余空白，用于生成描述文本"""
    cleaned = re.sub(r"[*_`#>]+", "", text)
    cleaned = re.sub(r"^[\-+]\s*", "", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def is_metadata_label(text: str, labels: Collection[str]) -> bool:
    """判断一行是否为「标签：值」形式的场记/说明行"""
    head = text.split("：", 1)[0].split(":", 1)[0].strip()
    return bool(head) and head in set(labels)


def label_values(text: str, label: str) -> List[str]:
    """取出「标签：」后面到下一个标签之前的内容，可能有多处"""
    values: List[str] = []
    for match in re.finditer(rf"{label}\s*[:：]\s*(.*)", text):
        rest = match.group(1)
        next_label = re.search(r"[\u4e00-\u9fa5]{2,10}\s*[:：]", rest)
        values.append(rest[: next_label.start()] if next_label else rest)
    return values


def infer_gender(name: str, description: str = "") -> str:
    """根据角色名与描述推断性别"""
    haystack = f"{name}{description}"
    for keyword in _MALE_KEYWORDS:
        if keyword in haystack or keyword in name:
            return "male"
    for keyword in _FEMALE_KEYWORDS:
        if keyword in haystack or keyword in name:
            return "female"
    return "unknown"


@lru_cache(maxsize=8)
def _subject_match_re(verbs: Sequence[str]) -> re.Pattern:
    """「句首 2-4 字主语 + 动词」模式，动词按长词优先排列"""
    ordered = sorted({verb for verb in verbs if verb}, key=len, reverse=True)
    alternatives = "|".join(re.escape(verb) for verb in ordered)
    return re.compile(rf"^(?P<name>[\u4e00-\u9fa5]{{2,4}})(?=(?:{alternatives}))")


@lru_cache(maxsize=8)
def _subject_search_re(verbs: Sequence[str]) -> re.Pattern:
    """小句内任意位置的「主语 + 动词」模式"""
    ordered = sorted({verb for verb in verbs if verb}, key=len, reverse=True)
    alternatives = "|".join(re.escape(verb) for verb in ordered)
    return re.compile(rf"(?P<name>[\u4e00-\u9fa5]{{2,4}})(?=(?:{alternatives}))")


def _is_plausible_name(name: str) -> bool:
    """排除停用词与副词性片段，如「阳光照进」「温和地」「他忽然」"""
    if len(name) < 2:
        return False
    if any(word in name for word in NON_CHARACTER_WORDS):
        return False
    if name.endswith(_NAME_REJECT_SUFFIXES) or name.startswith(_NAME_REJECT_PREFIXES):
        return False
    # 四字候选若含「的/地/得」多为短语而非姓名
    return not any(marker in name for marker in ("的", "地", "得"))


def find_subject(text: str, verbs: Sequence[str]) -> Optional[str]:
    """从句首切出「主语 + 动词」结构中的主语"""
    if not text or not verbs:
        return None
    match = _subject_match_re(tuple(verbs)).match(text.strip())
    if not match:
        return None
    name = match.group("name")
    return name if _is_plausible_name(name) else None


def _clause_segments(text: str) -> List[str]:
    """按小句边界切分，返回非空小句"""
    segments: List[str] = []
    current: List[str] = []
    for char in text:
        if char in CLAUSE_DELIMITERS:
            if current:
                segments.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        segments.append("".join(current))
    return segments


def find_nearest_subject(
    text: str,
    position: int,
    verbs: Sequence[str],
    strict: bool = False,
) -> Optional[str]:
    """从 position 处向前逐个小句回溯，找出最近的动作主体

    ``strict`` 只接受「小句开头即主语」的形式，用于说话人归属这类高精度场景，
    避免把「同桌张晨写的」中的修饰成分当成人名。
    """
    if not text or not verbs:
        return None
    head = text[: max(0, min(position, len(text)))]
    for segment in reversed(_clause_segments(head)):
        subject = find_subject(segment, verbs)
        if subject:
            return subject
        if strict:
            continue
        for match in _subject_search_re(tuple(verbs)).finditer(segment):
            name = match.group("name")
            if _is_plausible_name(name):
                return name
    return None


def find_cjk_names(text: str) -> List[str]:
    """取出文本中全部汉字连续串，供角色名候选过滤使用"""
    return _CJK_RUN_RE.findall(text)


def first_match_positions(text: str, words: Collection[str]) -> Dict[str, int]:
    """返回每个词在文本中首次出现的下标，未出现则不在结果中"""
    positions: Dict[str, int] = {}
    for word in words:
        if not word:
            continue
        index = text.find(word)
        if index >= 0:
            positions[word] = index
    return positions
