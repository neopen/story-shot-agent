"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character_sheet_generator.py
@Description: 角色三视图资产提示词生成（正/侧/背）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from penshot.neopen.agent.asset_generator.asset_models import (
    AssetConsistency,
    AssetPlanDocument,
    AssetSpec,
    AssetType,
    AssetUsage,
)
from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    APPEARANCE_FIELDS,
    contains_keyword,
    extract_appearance_anchors,
    truncate_at_clause_boundary,
)
from penshot.neopen.constants.appearance import (
    COLOR_KEYWORDS,
    GARMENT_NOUNS,
    MATERIAL_KEYWORDS,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)

# 角色三视图统一视角：正/侧/背
CHARACTER_SHEET_VIEWS: List[str] = ["front", "side", "back"]

# 三视图只做身份参考：中性棚拍光与中性背景，禁止拼接剧情氛围打光（FR-053）
CHARACTER_SHEET_BASE_PARTS: Sequence[str] = (
    "front view, side view and back view",
    "full body",
    "neutral grey background",
    "soft even studio lighting",
    "consistent facial identity and outfit",
)

CHARACTER_SHEET_TAIL = "highly detailed character design"

CHARACTER_SHEET_MAX_PROMPT_LENGTH = 400

CHARACTER_NEGATIVE_PROMPT = (
    "multiple characters, duplicate faces, extra limbs, deformed hands, "
    "inconsistent outfit, different identity, text, watermark, low quality"
)

# 服装歧义标记：A 或 B / 可能 A（0.4.5 服装完整性）
_ALTERNATIVE_SPLIT_RE = re.compile(r"(?:或者|或是|或|\beither\b|\bor\b)", re.IGNORECASE)
_UNCERTAINTY_RE = re.compile(
    r"(?:可能(?:是)?|也许(?:是)?|待定|之类(?:的)?|\bmaybe\b|\bpossibly\b|"
    r"\bperhaps\b|\bunclear\b)",
    re.IGNORECASE,
)
_CLAUSE_TOKEN_RE = re.compile(r"([，,；;。])")


def _choose_alternative(segments: Sequence[str], style: str) -> Tuple[str, str]:
    """按 style > 服装名词唯一命中 > 阅读顺序选择备选"""
    style_text = str(style or "").strip().lower()
    if style_text:
        style_hits = [
            segment
            for segment in segments
            if style_text in segment.lower() or segment.lower() in style_text
        ]
        if len(style_hits) == 1:
            return style_hits[0], "style_match"

    garment_hits = [
        segment for segment in segments if contains_keyword(segment, GARMENT_NOUNS)
    ]
    if len(garment_hits) == 1:
        return garment_hits[0], "garment_match"
    return segments[0], "first_alternative"


def _has_garment(text: str) -> bool:
    """服装文本是否包含明确服装名词"""
    return contains_keyword(str(text or ""), GARMENT_NOUNS)


def _missing_outfit_fields(text: str) -> List[str]:
    """服装描述缺失的要素（类型 / 颜色 / 材质），按固定顺序返回

    0.4.5 把“信息不足”纳入人工复核：只有服装名词但没有颜色或材质时，
    三视图会退化成“高中校服”这类无法约束外观的短标签。
    """
    value = str(text or "")
    missing: List[str] = []
    if not contains_keyword(value, GARMENT_NOUNS):
        missing.append("类型")
    if not contains_keyword(value, COLOR_KEYWORDS):
        missing.append("颜色")
    if not contains_keyword(value, MATERIAL_KEYWORDS):
        missing.append("材质")
    return missing


def _missing_reason(fields: Sequence[str]) -> str:
    """把缺失要素拼成可读原因；三种全缺时用顿号分隔"""
    if fields == ["类型"]:
        return "缺少明确服装类型"
    if len(fields) == 1:
        return f"服装描述缺少{fields[0]}"
    if len(fields) == 2:
        return f"服装描述缺少{fields[0]}和{fields[1]}"
    return f"服装描述缺少{'、'.join(fields[:-1])}和{fields[-1]}"


# 从片段提示词截取服装短语时，去掉后续动作/状态子句（避免把“额头有汗”拼进服装）
_TRAILING_ACTION_RE = re.compile(
    r"\s+(?:with|holding|smiling|looking|turning|standing|sitting|running|"
    r"walking|grabbing|waving|leaning|reaching|glancing|wearing)\b.*$",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;！!？?\n]+")
_PERSON_OUTFIT_PREFIX_RE = re.compile(
    r"^(?:[A-Z][A-Za-z'’-]*(?:\s+[A-Z][A-Za-z'’-]*){0,2}\s+)?"
    r"(?:wearing|dressed\s+in|clad\s+in|in|穿着|身穿|身着|着)\s*",
    re.IGNORECASE,
)


def _strip_person_prefix(clause: str, character_name: str = "") -> str:
    """去掉“张晨穿着 / Zhang Chen wearing”等主语前缀，只保留服装短语"""
    text = str(clause or "").strip()
    name = str(character_name or "").strip()
    if name and text.startswith(name):
        text = text[len(name) :].lstrip(" ，,的着")
    return _PERSON_OUTFIT_PREFIX_RE.sub("", text).strip()


def _outfit_clauses(text: str, character_name: str = "") -> List[Tuple[str, str]]:
    """从片段文本提取服装子句，返回 (子句, 服装短语) 列表"""
    results: List[Tuple[str, str]] = []
    for raw in _CLAUSE_SPLIT_RE.split(str(text or "")):
        clause = _strip_person_prefix(raw, character_name)
        if not clause or not _has_garment(clause):
            continue
        phrase = _TRAILING_ACTION_RE.sub("", clause).strip(" ，,；;。")
        if phrase and _has_garment(phrase):
            results.append((raw.strip(), phrase))
    return results


def _outfit_from_prompt(image_prompt: str) -> str:
    """兼容 0.4.4 产物：metadata 未记录 outfit_text 时从三视图提示词反查服装段"""
    for clause in str(image_prompt or "").split(", "):
        if _has_garment(clause):
            return clause.strip()
    return ""


def _best_outfit_candidate(
    current: str, character_name: str, texts: Sequence[Tuple[str, str]]
) -> Optional[Tuple[str, str]]:
    """在片段提示词中挑选信息量最大的服装短语

    只在比当前描述更完整时返回，避免用同等信息量的片段文本覆盖原始锚点。
    """
    current_missing = len(_missing_outfit_fields(current))
    if current_missing == 0:
        return None

    best: Optional[Tuple[str, str]] = None
    best_key: Optional[Tuple[int, int]] = None
    for fragment_id, text in texts:
        for _, phrase in _outfit_clauses(text, character_name):
            missing = len(_missing_outfit_fields(phrase))
            if missing >= current_missing:
                continue
            key = (-missing, len(phrase))
            if best_key is None or key > best_key:
                best_key = key
                best = (fragment_id, phrase)
    return best


def _resolve_clothing_ambiguity(
    clothing: str, style: str = ""
) -> Tuple[str, str, List[str], bool]:
    """消解服装描述中的“A 或 B / 可能 A”，返回最终文本与消解依据

    歧义来自剧本解析结果时无法凭空判定，按确定性顺序选择并交给 metadata
    标记人工复核；不修改结构化服装的来源字段本身。
    """
    text = str(clothing or "").strip()
    if not text:
        return "", "none", [], False

    resolution = "none"
    alternatives: List[str] = []
    uncertain = False
    parts: List[str] = []

    for token in _CLAUSE_TOKEN_RE.split(text):
        if not token:
            continue
        if _CLAUSE_TOKEN_RE.fullmatch(token):
            parts.append(token)
            continue

        clause = _UNCERTAINTY_RE.sub("", token).strip()
        if clause != token.strip():
            uncertain = True

        segments = [
            segment.strip(" ，,；;。")
            for segment in _ALTERNATIVE_SPLIT_RE.split(clause)
        ]
        segments = [segment for segment in segments if segment]
        if len(segments) >= 2:
            chosen, label = _choose_alternative(segments, style)
            alternatives.extend(segments)
            if resolution in ("none", "uncertainty_stripped"):
                resolution = label
            parts.append(chosen)
            continue
        parts.append(clause)

    resolved = re.sub(r"[，,；;]\s*(?=[，,；;。]|$)", "", "".join(parts)).strip(
        " ，,；;。"
    )
    if not alternatives and uncertain and resolution == "none":
        resolution = "uncertainty_stripped"
    return resolved, resolution, alternatives, uncertain


def _appearance_metadata(
    clothing: str, resolution: str, alternatives: Sequence[str], uncertain: bool
) -> Dict[str, Any]:
    """生成服装完整性的审阅标记"""
    metadata: Dict[str, Any] = {}
    if alternatives or uncertain:
        metadata["outfit_resolution"] = resolution
    if alternatives:
        metadata["outfit_alternatives"] = list(dict.fromkeys(alternatives))

    missing = _missing_outfit_fields(clothing)
    if missing:
        metadata["outfit_missing_fields"] = missing
    if clothing:
        metadata["outfit_text"] = clothing

    reasons: List[str] = []
    if alternatives:
        reasons.append("服装描述存在多个备选")
    if uncertain:
        reasons.append("服装描述含不确定词")
    if missing:
        reasons.append(_missing_reason(missing))
    if reasons:
        metadata["requires_special_attention"] = True
        metadata["attention_reason"] = "；".join(reasons)
    return metadata


def _joined_length(parts: Sequence[str]) -> int:
    """计算以 ", " 拼接后的长度"""
    return len(", ".join(parts))


def _outfit_record(parsed_script: Any, character_name: str) -> Dict[str, str]:
    """提取某个角色的结构化服装记录（供契约缺失时兜底）"""
    metadata = getattr(parsed_script, "global_metadata", None)
    for outfit in getattr(metadata, "character_outfits", None) or []:
        if getattr(outfit, "character", "") != character_name:
            continue
        return {
            field_name: value
            for field_name in ("description", "color", "style", "material")
            if (value := str(getattr(outfit, field_name, "") or "").strip())
        }
    return {}


def _appearance_anchors(parsed_script: Any, contract: Any, name: str) -> Dict[str, Any]:
    """读取角色外观锚点；契约为空时用同一规则从解析结果兜底"""
    anchors: Dict[str, Any] = {}
    char_contract = (
        getattr(contract, "characters", {}).get(name) if contract is not None else None
    )
    if char_contract is not None:
        anchors = getattr(char_contract, "appearance_anchors", {}) or {}

    if not any(
        str(anchors.get(field_name) or "").strip() for field_name in APPEARANCE_FIELDS
    ):
        description = ""
        for char in getattr(parsed_script, "characters", None) or []:
            if getattr(char, "name", "") == name:
                description = str(getattr(char, "description", None) or "")
                break
        anchors = extract_appearance_anchors(
            description, _outfit_record(parsed_script, name)
        )
    return dict(anchors)


def _appearance_values(anchors: Dict[str, Any]) -> List[str]:
    """按白名单固定顺序输出外观值"""
    return [
        value
        for field_name in APPEARANCE_FIELDS
        if (value := str(anchors.get(field_name) or "").strip())
    ]


def _dedupe_values(values: Sequence[str]) -> List[str]:
    """按出现顺序去重，包含关系视为同一段描述（避免服装被重复拼接）"""
    result: List[str] = []
    for value in values:
        folded = value.strip()
        if not folded:
            continue
        if any(folded in existing or existing in folded for existing in result):
            continue
        result.append(folded)
    return result


def _compose_prompt(name: str, appearance_values: Sequence[str]) -> str:
    """按固定顺序拼装提示词；超限时只在子句/字段边界裁剪，不切半截词"""
    parts: List[str] = [
        f"character reference sheet of {name}",
        *CHARACTER_SHEET_BASE_PARTS,
    ]

    for value in appearance_values:
        if (
            _joined_length(parts + [value, CHARACTER_SHEET_TAIL])
            <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
        ):
            parts.append(value)
            continue

        room = (
            CHARACTER_SHEET_MAX_PROMPT_LENGTH
            - _joined_length(parts)
            - len(", ")
            - len(", ")
            - len(CHARACTER_SHEET_TAIL)
        )
        truncated = truncate_at_clause_boundary(value, room) if room > 0 else ""
        if (
            truncated
            and len(truncated) < len(value)
            and _joined_length(parts + [truncated, CHARACTER_SHEET_TAIL])
            <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
        ):
            parts.append(truncated)
        break

    if (
        _joined_length(parts + [CHARACTER_SHEET_TAIL])
        <= CHARACTER_SHEET_MAX_PROMPT_LENGTH
    ):
        parts.append(CHARACTER_SHEET_TAIL)
    return ", ".join(parts)


def build_character_sheet_specs(
    parsed_script: Any, contract: GlobalConsistencyContract
) -> List[AssetSpec]:
    """为契约中的每个角色构建三视图资产规格"""
    if contract is None:
        return []

    names: List[str] = []
    for char in getattr(parsed_script, "characters", None) or []:
        name = getattr(char, "name", "")
        if name and name not in names:
            names.append(name)
    # 契约里可能有解析结果未列出的角色（来自场景元素）
    for name in getattr(contract, "characters", {}).keys():
        if name not in names:
            names.append(name)

    specs: List[AssetSpec] = []
    for index, name in enumerate(names, start=1):
        anchors = _appearance_anchors(parsed_script, contract, name)
        outfit = _outfit_record(parsed_script, name)
        clothing = str(anchors.get("clothing") or "").strip()
        resolved, resolution, alternatives, uncertain = _resolve_clothing_ambiguity(
            clothing, outfit.get("style", "")
        )
        if resolved:
            anchors["clothing"] = resolved
        appearance = _dedupe_values(_appearance_values(anchors))
        metadata: Dict[str, Any] = {"role": "identity_anchor"}
        metadata.update(
            _appearance_metadata(
                resolved or clothing, resolution, alternatives, uncertain
            )
        )
        specs.append(
            AssetSpec(
                asset_id=f"char_{index:03d}",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name=name,
                image_prompt=_compose_prompt(name, appearance),
                negative_prompt=CHARACTER_NEGATIVE_PROMPT,
                views=list(CHARACTER_SHEET_VIEWS),
                usage=AssetUsage(characters=[name]),
                consistency=AssetConsistency(
                    identity_lock=True,
                    preferred_view=CHARACTER_SHEET_VIEWS[0],
                ),
                metadata=metadata,
            )
        )
    return specs


def backfill_character_outfits(
    plan: Any,
    texts_by_character: Mapping[str, Sequence[Tuple[str, str]]],
) -> List[str]:
    """用片段提示词回填角色服装缺失的颜色/材质（0.4.5 任务 2）

    ASSETS 节点早于提示词生成，此时只能依据剧本锚点标记“信息不足”；路由阶段
    拿到最终提示词后，用同一角色的片段服装短语补全三视图提示词。补全后仍保留
    ``requires_special_attention``：源锚点本身不完整，人工复核仍有必要。

    Args:
        plan: 资产计划文档（``AssetPlanDocument`` 或字典），原地修改
        texts_by_character: 角色名 -> [(片段ID, 片段文本)]，片段文本含描述与提示词

    Returns:
        实际回填的 asset_id 列表
    """
    document = (
        plan
        if isinstance(plan, AssetPlanDocument)
        else AssetPlanDocument.model_validate(plan)
    )
    changed: List[str] = []
    for spec in document.assets:
        if spec.asset_type != AssetType.CHARACTER_SHEET:
            continue
        if spec.asset_ref or spec.metadata.get("human_edited"):
            continue
        current = str(spec.metadata.get("outfit_text") or "").strip() or (
            _outfit_from_prompt(spec.image_prompt)
        )
        if not _missing_outfit_fields(current):
            continue
        candidate = _best_outfit_candidate(
            current, spec.owner_name, texts_by_character.get(spec.owner_name, [])
        )
        if candidate is None:
            continue
        fragment_id, phrase = candidate
        if not current or current not in spec.image_prompt:
            # 提示词已截断或服装未拼入时不做替换，避免破坏提示词结构
            continue

        spec.image_prompt = spec.image_prompt.replace(current, phrase, 1)
        spec.metadata["outfit_text"] = phrase
        spec.metadata["outfit_backfill_source"] = fragment_id
        remaining = _missing_outfit_fields(phrase)
        if remaining:
            spec.metadata["outfit_missing_fields"] = remaining

        reason = str(spec.metadata.get("attention_reason") or "").strip()
        if not reason:
            # 兼容 0.4.4 产物：旧计划未记录缺失原因，按当前锚点补齐
            reason = _missing_reason(_missing_outfit_fields(current))
        extra = f"已从片段提示词 {fragment_id} 回填"
        if remaining:
            extra += f"，仍缺{'、'.join(remaining)}"
        spec.metadata["requires_special_attention"] = True
        spec.metadata["attention_reason"] = f"{reason}；{extra}" if reason else extra
        changed.append(spec.asset_id)
    return changed
