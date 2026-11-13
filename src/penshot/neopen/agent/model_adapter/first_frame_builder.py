"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: first_frame_builder.py
@Description: 片段专属首帧提示词与资产引用语义（M3：T-301/T-302）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from penshot.neopen.agent.character_names import normalize_character_name
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    APPEARANCE_FIELDS,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import build_style_text
from penshot.neopen.agent.model_adapter.model_models import PromptReference
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
)
from penshot.neopen.agent.prop_usage import should_reference_prop

# 景别短语：键与 CameraControl.shot_type / ShotType.value 归一值一致
SHOT_PHRASES: Dict[str, str] = {
    "close_up": "close-up shot",
    "extreme_close_up": "extreme close-up shot",
    "wide_shot": "wide shot",
    "long_shot": "long shot",
    "medium_shot": "medium shot",
    "over_shoulder": "over-the-shoulder shot",
    "pov": "POV shot",
    "two_shot": "two-shot",
}

_STYLE_PREFIX_PATTERN = re.compile(r"^\[Style:[^\]]*\]\s*")
_ACTION_LABEL_RE = re.compile(r"action\s*[:：]\s*", re.IGNORECASE)

# 中文镜头前缀：兼容“过肩镜头（或中景）：”“全景/环境音镜头：”“中景转全景：”等变体
_SHOT_PREFIX_RE = re.compile(
    r"^(?:大?全景|远景|中近景|中景|近景|极?特写|过肩|主观|双人)"
    r"[^，,。！？!?；;：:\n]{0,10}[：:，,]\s*"
)

# 子句边界：中文逗号/句号与英文逗号/句号统一切分，便于按视觉内容取舍
_CLAUSE_SEPARATORS = "，,。！？!?；;\n"
# 只裁掉分隔标点，保留引号/问号，避免把“上不上？”的收尾引号一起裁掉
_CLAUSE_TRIM_CHARS = " \t\r\n，,。；;：:"
_QUOTE_PAIRS = {"“": "”", "‘": "’", "「": "」", "『": "』", '"': '"'}

# 音频/画外事件关键词：命中即整句剔除，避免首帧只剩音效文本（FR-081）
_AUDIO_ONLY_KEYWORDS = (
    "广播",
    "画外音",
    "音效",
    "环境音",
    "播报",
    "回荡",
    "announcer",
    "voice-over",
    "voiceover",
    "announcement",
)

# 视觉名词提示：清洗后整段不含角色、场景地点或这些词时视为“无视觉内容”
_VISUAL_NOUNS = (
    "人",
    "身影",
    "背影",
    "侧脸",
    "脸",
    "眼",
    "手",
    "肩",
    "头发",
    "站台",
    "隧道",
    "列车",
    "车",
    "门",
    "窗",
    "墙",
    "地面",
    "灯",
    "街",
    "路",
    "建筑",
    "天空",
    "雨",
    "雪",
    "树",
    "草",
    "花",
    "桌",
    "椅",
    "床",
    "沙发",
    "书",
    "纸",
    "围巾",
    "大衣",
    "衣服",
    "杯",
    # 英文提示词回退路径同样需要视觉锚点
    "person",
    "man",
    "woman",
    "platform",
    "tunnel",
    "train",
    "door",
    "window",
    "wall",
    "floor",
    "light",
    "street",
    "road",
    "building",
    "sky",
    "rain",
    "snow",
    "tree",
    "book",
    "paper",
    "scarf",
    "coat",
    "cup",
)

EMPTY_SCENE_PROMPT = "empty scene, no people"

# 天气为晴时不再重复声明，避免首帧提示词堆叠无信息短语
_NEUTRAL_WEATHER = ("", "clear", "clear weather", "sunny")

# 时间序列/动作线索：命中即视为动作开始，之后的内容不进入静态首帧（P0-2）
_MOTION_CUES = (
    "亮起",
    "熄灭",
    "驶入",
    "驶离",
    "进站",
    "出站",
    "打开",
    "关上",
    "关闭",
    "合拢",
    "启动",
    "迈步",
    "走上",
    "走下",
    "走出",
    "走进",
    "转身",
    "回头",
    "抬头",
    "揉成",
    "吹起",
    "飘起",
    "逐渐",
    "缓缓",
    "渐渐",
    "随后",
    "然后",
    "接着",
    "最终",
    "与此同时",
    "突然",
    "渐黑",
    "消失",
    "开口",
    "说道",
    "问道",
    "喊道",
    "说话",
    "轻声说",
    "低声说",
    "叹气",
    "叹了",
    "点头",
    "摇头",
    "伸手",
    "接过",
    "递给",
    "握紧",
    "松开",
    "落下",
    "升起",
    "走过",
    "走来",
    "走向",
    "走近",
    "靠近",
    "推开",
    "拉上",
    "拉开",
    "闪烁",
    "enters",
    "entering",
    "entered",
    "opens",
    "opening",
    "opened",
    "closes",
    "closing",
    "closed",
    "stepping",
    "steps",
    "walks",
    "walking",
    "turns",
    "turning",
    "looks back",
    "look back",
    "looks down",
    "looking down",
    "looks up",
    "looking up",
    "raises",
    "raising",
    "glances",
    "glancing",
    "nods",
    "nodding",
    "slowly",
    "sighs",
    "sighing",
    "departs",
    "departing",
    "fade",
    "fades",
    "fading",
    "flutters",
    "fluttering",
    "gradually",
    "starts",
    "moving",
    "approaching",
    "arriving",
)
_NEGATION_PREFIXES = ("没有", "并未", "未", "不", "没")

CHARACTER_SHEET_TYPE = "character_sheet"
SCENE_ASSET_TYPE = "scene"
PROP_ASSET_TYPE = "prop"

# 场景地点双语词表：剧本地点是中文、最终提示词常为英文，直接子串匹配会漏检
_SCENE_LOCATION_GLOSSARY: Dict[str, tuple[str, ...]] = {
    "教室": ("classroom", "class room"),
    "走廊": ("corridor", "hallway", "hall"),
    "记忆墙": ("memory wall",),
    "班级记忆墙": ("memory wall",),
    "操场": ("playground", "sports field"),
    "篮球场": ("basketball court",),
    "图书馆": ("library",),
    "食堂": ("cafeteria", "canteen"),
    "宿舍": ("dormitory", "dorm room"),
    "天台": ("rooftop",),
    "校门": ("school gate",),
    "街道": ("street",),
    "公交站": ("bus stop",),
    "公园": ("park",),
    "河边": ("riverside", "riverbank"),
    "客厅": ("living room",),
    "卧室": ("bedroom",),
    "厨房": ("kitchen",),
    "办公室": ("office",),
    "医院": ("hospital",),
    "咖啡馆": ("cafe", "coffee shop"),
    "餐厅": ("restaurant",),
    "商店": ("store", "shop"),
    "家": ("home",),
}


def _scene_location_terms(location: str) -> List[str]:
    """把场景地点展开为可直接在文本中检索的词（中文原词 + 英文别名）"""
    terms: List[str] = []
    for token in re.split(r"[/、·,，]", str(location or "")):
        token = token.strip()
        if not token:
            continue
        terms.append(token)
        for key, aliases in _SCENE_LOCATION_GLOSSARY.items():
            if key == token or (len(key) > 1 and key in token):
                terms.extend(aliases)
    return list(dict.fromkeys(terms))


def _term_in_text(text: str, term: str) -> bool:
    """英文词按整词匹配，中文按子串匹配（与外观词表口径一致）"""
    if not term:
        return False
    if term.isascii():
        pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
        return re.search(pattern, text) is not None
    return term in text


# 英文单引号对白里常有 don't 之类的撇号：首尾引号必须不贴字母，
# 中间的撇号只有夹在两个字母之间才视为词内撇号而非配对边界
_QUOTED_RE = re.compile(
    r"\"[^\"]*\""
    r"|(?<![A-Za-z])'(?:[^']|(?<=[A-Za-z])'(?=[A-Za-z]))*'(?![A-Za-z])"
    r"|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』"
)


def _strip_quoted_content(text: str) -> str:
    """剔除对白/引号内容：台词里提到“走廊”不代表画面场景在走廊"""
    return _QUOTED_RE.sub(" ", str(text or ""))


def _scene_asset_mentioned(asset: Any, text: str) -> bool:
    """场景资产的地点是否在片段文本中被提及"""
    location = _attr(asset, "owner_name") or _attr(asset, "location")
    return any(_term_in_text(text, term) for term in _scene_location_terms(location))


def check_scene_anchor_consistency(
    prompt: AIVideoPrompt,
    contract: Any,
    scene: Any = None,
    fragment: Any = None,
    first_frame_asset_id: str = "",
) -> str:
    """校验片段描述的场景与首帧场景资产是否一致（0.4.5 任务 7）

    片段文本明确提到另一个场景地点、且未提到当前首帧场景时给出告警；文本没有
    场景描述或同时提到多个场景时跳过，避免误报。

    Returns:
        告警文本；无需告警时返回空串
    """
    asset_id = str(first_frame_asset_id or "").strip()
    if contract is None or not asset_id:
        return ""

    scenes = _contract_assets(contract, SCENE_ASSET_TYPE)
    current = next(
        (item for item in scenes if _attr(item, "asset_id") == asset_id), None
    )
    if current is None:
        return ""

    text = _strip_quoted_content(
        f"{_attr(fragment, 'description')} {_attr(prompt, 'prompt')}"
    )
    if _scene_asset_mentioned(current, text):
        return ""

    mentioned = [
        item
        for item in scenes
        if _attr(item, "asset_id") != asset_id and _scene_asset_mentioned(item, text)
    ]
    if len(mentioned) != 1:
        return ""

    target = mentioned[0]
    fragment_id = _attr(fragment, "id") or _attr(prompt, "fragment_id")
    return (
        f"{fragment_id} 描述「{_attr(target, 'owner_name')}」场景，"
        f"但首帧资产为「{_attr(current, 'owner_name')}」，"
        f"建议改用 {_attr(target, 'asset_id')}（{_attr(target, 'owner_name')}）"
    )


def _attr(source: Any, name: str, default: str = "") -> str:
    """读取 dataclass / 字典字段并归一为字符串"""
    if source is None:
        return default
    value = getattr(source, name, None)
    if value is None and isinstance(source, dict):
        value = source.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _contract_assets(contract: Any, asset_type: str) -> List[Any]:
    """按类型筛选契约中的资产锚点"""
    assets = getattr(contract, "assets", None) or {}
    values = assets.values() if isinstance(assets, dict) else assets
    return [
        asset
        for asset in values
        if _attr(asset, "asset_type") == asset_type and _attr(asset, "asset_id")
    ]


def _contract_scenes(contract: Any) -> List[Any]:
    """读取契约中的场景（按场景号排序，保证结果稳定）"""
    scenes = getattr(contract, "scenes", None) or {}
    if isinstance(scenes, dict):
        return [scenes[key] for key in sorted(scenes, key=str)]
    return list(scenes)


def _resolve_scene(
    contract: Any,
    prompt: AIVideoPrompt,
    scene: Any = None,
) -> Optional[Any]:
    """解析片段所属场景

    优先使用调用方显式传入的场景（T-303 由镜头 -> 场景映射提供）；缺失时
    回退契约场景：先按地点词命中片段提示词，再按主角色唯一出现的场景判断。
    无法唯一确定时返回 ``None``，不猜测错误场景而污染首帧提示词。
    """
    if scene is not None:
        return scene

    candidates = _contract_scenes(contract)
    if not candidates:
        return None

    prompt_text = _attr(prompt, "prompt")
    matched = [
        item
        for item in candidates
        if _attr(item, "location") and _attr(item, "location") in prompt_text
    ]
    if len(matched) == 1:
        return matched[0]

    main_character = _attr(prompt, "main_character")
    if main_character:
        pool = matched or candidates
        character_scenes = [
            item
            for item in pool
            if main_character in (getattr(item, "characters_in_scene", None) or [])
        ]
        if len(character_scenes) == 1:
            return character_scenes[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _shot_phrase(prompt: AIVideoPrompt, fragment: Any) -> str:
    """景别短语：结构化相机参数 > 来源片段景别 > 中景兜底"""
    camera = getattr(prompt, "camera", None)
    shot_type = _attr(camera, "shot_type") or _attr(fragment, "shot_type")
    return SHOT_PHRASES.get(shot_type.lower(), "medium shot")


def _appearance_text(contract: Any, character_name: str) -> str:
    """角色白名单外观锚点（顺序固定，与三视图同源）"""
    if contract is None or not character_name:
        return ""
    characters = getattr(contract, "characters", None) or {}
    character = characters.get(character_name) if isinstance(characters, dict) else None
    anchors = getattr(character, "appearance_anchors", None) or {}
    parts = [
        f"{field_name}: {anchors[field_name]}"
        for field_name in APPEARANCE_FIELDS
        if anchors.get(field_name)
    ]
    return ", ".join(parts)


def _has_visual_anchor(text: str, character_name: str, scene: Any) -> bool:
    """判断清洗后的文本是否仍包含可入画的视觉对象（FR-083）"""
    if not text:
        return False
    if character_name and character_name in text:
        return True
    location = _attr(scene, "location")
    if any(term in text for term in _scene_location_terms(location)):
        return True
    lowered = text.lower()
    return any(noun in lowered for noun in _VISUAL_NOUNS)


def _split_clauses(text: str) -> List[str]:
    """按标点切分子句，但不切开引号内的台词（避免引号配对残缺）"""
    clauses: List[str] = []
    buffer: List[str] = []
    closing = ""
    for char in text:
        if closing:
            buffer.append(char)
            if char == closing:
                closing = ""
            continue
        if char in _QUOTE_PAIRS:
            closing = _QUOTE_PAIRS[char]
            buffer.append(char)
            continue
        if char in _CLAUSE_SEPARATORS:
            clauses.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    clauses.append("".join(buffer))
    return clauses


def _clean_visual_clauses(text: str) -> List[str]:
    """清洗片段动作文本并按子句返回，只保留可入画的视觉内容（FR-080/081）

    处理顺序：剔除 ``action:`` 标签 -> 按子句切分 -> 剥离中文镜头前缀 ->
    丢弃音频/画外子句与含“镜头”的运镜描述。
    """
    cleaned = _ACTION_LABEL_RE.sub(" ", _STYLE_PREFIX_PATTERN.sub("", str(text or "")))
    clauses: List[str] = []
    for clause in _split_clauses(cleaned):
        clause = _SHOT_PREFIX_RE.sub("", clause.strip())
        clause = clause.strip(_CLAUSE_TRIM_CHARS)
        if not clause:
            continue
        lowered = clause.lower()
        if any(keyword in lowered for keyword in _AUDIO_ONLY_KEYWORDS):
            continue
        # “固定镜头”“镜头越过肩膀”等属于运镜描述，景别已由 shot_phrase 表达
        if "镜头" in clause:
            continue
        clauses.append(clause)
    return clauses


def _clean_visual_text(text: str) -> str:
    """清洗片段动作文本；返回空串表示没有可用视觉内容（FR-083 兜底）"""
    return ", ".join(_clean_visual_clauses(text))


def _is_motion_clause(clause: str) -> bool:
    """子句是否包含时间序列/动作线索（否定表述如“没有回头”不算）"""
    lowered = clause.lower()
    for cue in _MOTION_CUES:
        start = lowered.find(cue)
        if start < 0:
            continue
        prefix = lowered[max(0, start - 3) : start]
        if any(negation in prefix for negation in _NEGATION_PREFIXES):
            continue
        return True
    return False


def _is_negated_motion_clause(clause: str) -> bool:
    """子句是否只含被否定的动作线索（如“没有回头”）

    这类子句描述的是静止状态，但字面仍带动作词。首帧验收按关键词检查
    ``image_prompt``，因此在静态截面前剔除，避免“回头”等词误判为动作。
    """
    lowered = clause.lower()
    for cue in _MOTION_CUES:
        start = lowered.find(cue)
        if start < 0:
            continue
        prefix = lowered[max(0, start - 3) : start]
        if any(negation in prefix for negation in _NEGATION_PREFIXES):
            return True
    return False


def find_motion_clauses(text: str) -> List[str]:
    """返回文本中命中动作线索的子句，供 Gate 1 首帧静态性检查复用"""
    return [
        clause
        for clause in _split_clauses(str(text or ""))
        if _is_motion_clause(clause)
    ]


def split_static_motion(text: str) -> Tuple[str, str]:
    """把片段文本切分为「动作开始前的静态截面」与「后续动作序列」（P0-2）

    静态截面只保留第一个动作线索之前的子句；若首句即动作，静态部分为空，
    由调用方用景别/角色/场景构成首帧。没有动作线索时整段都视为静态，
    同时作为动作描述回退，避免图生视频缺少可动内容。

    Returns:
        ``(static_text, motion_text)``，均为逗号拼接的清洗后子句
    """
    clauses = _clean_visual_clauses(text)
    if not clauses:
        return "", ""
    index = next(
        (i for i, clause in enumerate(clauses) if _is_motion_clause(clause)),
        len(clauses),
    )
    static_text = ", ".join(
        clause for clause in clauses[:index] if not _is_negated_motion_clause(clause)
    )
    motion_text = ", ".join(clauses[index:]) if index < len(clauses) else static_text
    return static_text, motion_text


def _fragment_visual_text(prompt: AIVideoPrompt, fragment: Any) -> str:
    """片段原始视觉文本：优先来源片段描述，回退提示词正文（剥离风格前缀）"""
    description = _attr(fragment, "description")
    return description or _STYLE_PREFIX_PATTERN.sub("", _attr(prompt, "prompt")).strip()


def build_motion_prompt(
    prompt: Optional[AIVideoPrompt] = None, fragment: Any = None
) -> str:
    """构建图生视频的动作驱动提示词（P0-2）

    与 ``image_prompt`` 互斥：首帧只保留动作开始前的静态截面，动作序列改由
    本字段承载，供下游在首帧之后驱动画面。
    """
    if prompt is None and fragment is None:
        return ""
    raw = (
        _fragment_visual_text(prompt, fragment)
        if prompt is not None
        else _attr(fragment, "description")
    )
    _, motion = split_static_motion(raw)
    return motion


def build_first_frame_prompt(
    prompt: AIVideoPrompt,
    contract: Any = None,
    scene: Any = None,
    fragment: Any = None,
) -> str:
    """构建片段专属首帧静帧提示词（FR-011、AC-011）

    组成顺序：景别短语 -> 角色（白名单外观） -> 场景地点/时间/天气 ->
    动作开始前的静态截面 -> 风格维度。与角色三视图提示词（固定 turnaround
    棚拍表述）结构不同，保证 ``image_prompt`` 不会等于三视图提示词。

    动作文本经 FR-080/081 清洗后，再按 P0-2 只保留动作开始前的静态内容：
    “驶入/打开/回头/关门/渐黑”等时间序列动作由 ``build_motion_prompt``
    承载，首帧不再混入动作序列。清洗后无视觉内容时按 FR-083 追加空镜兜底。

    Args:
        prompt: 片段提示词；读取 ``main_character`` / ``camera`` / ``prompt``
        contract: 全局一致性契约；提供外观锚点、场景与风格锚点
        scene: 可选已解析场景（具备 location/time_of_day/weather 字段）
        fragment: 可选来源片段；提供 ``description`` 与 ``shot_type``

    Returns:
        英文为主的首帧静帧提示词；动作无视觉内容时包含空镜兜底描述
    """
    resolved_scene = _resolve_scene(contract, prompt, scene)
    # 旧产物可能已把“无角色”占位符写进 main_character，首帧拼接时同样视为无角色
    main_character = normalize_character_name(_attr(prompt, "main_character"))
    location = _attr(resolved_scene, "location")

    subject = main_character
    appearance = _appearance_text(contract, main_character)
    if appearance:
        subject = f"{subject} ({appearance})"
    shot_phrase = _shot_phrase(prompt, fragment)
    parts: List[str] = [f"{shot_phrase} of {subject}" if subject else shot_phrase]

    # 场景地点独立声明：FR-011 要求首帧同时锚定角色与所处环境
    if location:
        parts.append(f"at {location}")

    time_of_day = _attr(resolved_scene, "time_of_day")
    if time_of_day:
        parts.append(f"{time_of_day} lighting")

    weather = _attr(resolved_scene, "weather")
    if weather.lower() not in _NEUTRAL_WEATHER:
        parts.append(weather)

    raw_visual = _fragment_visual_text(prompt, fragment)
    cleaned = _clean_visual_text(raw_visual)
    if cleaned and _has_visual_anchor(cleaned, main_character, resolved_scene):
        static_text, _ = split_static_motion(raw_visual)
        if static_text:
            parts.append(static_text)
    else:
        # FR-083：纯音效/纯广播片段用空镜兜底，不能让首帧只剩声音描述
        parts.append(EMPTY_SCENE_PROMPT)

    if contract is not None:
        style_text = build_style_text(
            getattr(contract, "style_anchor", None),
            getattr(contract, "style_anchor_provenance", None),
        )
        if style_text:
            parts.append(style_text)

    return ", ".join(parts)


def _shot_type(prompt: AIVideoPrompt, fragment: Any) -> str:
    """结构化景别：提示词相机参数优先，回退来源片段景别"""
    return _attr(getattr(prompt, "camera", None), "shot_type") or _attr(
        fragment, "shot_type"
    )


def build_package_references(
    prompt: AIVideoPrompt,
    contract: Any = None,
    scene: Any = None,
    fragment: Any = None,
    prop_names: Optional[List[str]] = None,
    prop_states: Optional[Dict[str, str]] = None,
) -> List[PromptReference]:
    """构建片段的声明式资产引用语义（FR-010/016、AC-010）

    - 角色三视图：``role="identity_reference"``、``as_first_frame=False``；
    - 场景锚点：``role="first_frame"``、``as_first_frame=True``；
    - 道具静帧：``role="prop"``、``as_first_frame=False``。

    仅引用契约中已声明的资产；未声明资产不凭空造 ID。道具引用必须**同时**
    满足“文本提及”与“场景约束”，并复用 ``should_reference_prop`` 的着装
    道具聚焦规则（与使用范围回填同一口径）。围巾/饰品只在特写聚焦于它的
    片段挂引用，道具名至多展开出核心名词（“皱巴巴的纸条” → “纸条”）。

    Args:
        prompt: 片段提示词
        contract: 全局一致性契约
        scene: 可选已解析场景
        fragment: 可选来源片段
        prop_names: 场景内允许引用的道具名集合；``None`` 表示只按文本匹配
        prop_states: 道具名 -> 当前片段状态（如 crumpled/balled）

    Returns:
        声明式资产引用列表
    """
    if contract is None:
        return []

    references: List[PromptReference] = []
    main_character = _attr(prompt, "main_character")

    for asset in _contract_assets(contract, CHARACTER_SHEET_TYPE):
        if main_character and _attr(asset, "owner_name") == main_character:
            references.append(
                PromptReference(
                    asset_id=_attr(asset, "asset_id"),
                    role="identity_reference",
                    view="front",
                    as_first_frame=False,
                    required=True,
                )
            )

    resolved_scene = _resolve_scene(contract, prompt, scene)
    location = _attr(resolved_scene, "location")
    if location:
        for asset in _contract_assets(contract, SCENE_ASSET_TYPE):
            if _attr(asset, "owner_name") == location:
                references.append(
                    PromptReference(
                        asset_id=_attr(asset, "asset_id"),
                        role="first_frame",
                        view="front",
                        as_first_frame=True,
                        required=True,
                    )
                )

    text = f"{_attr(fragment, 'description')} {_attr(prompt, 'prompt')}"
    shot_type = _shot_type(prompt, fragment)
    allowed_props = set(prop_names) if prop_names is not None else None
    for asset in _contract_assets(contract, PROP_ASSET_TYPE):
        owner_name = _attr(asset, "owner_name")
        if not owner_name:
            continue
        # 文本提及 + 着装道具聚焦判定，与 usage 回填同口径
        if not should_reference_prop(text, owner_name, shot_type):
            continue
        if allowed_props is not None and owner_name not in allowed_props:
            continue
        references.append(
            PromptReference(
                asset_id=_attr(asset, "asset_id"),
                role="prop",
                view="front",
                as_first_frame=False,
                required=False,
                state=(prop_states or {}).get(owner_name, ""),
            )
        )

    return references
