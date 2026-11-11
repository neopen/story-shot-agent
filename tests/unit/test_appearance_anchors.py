"""M1 角色外观锚点共享模块的回归测试。

覆盖 0.4.4 Spec AC-001/AC-002/AC-003，以及 FR-004（白名单字段）
与 FR-005（同字段首值优先、跨片段一致）的确定性约束。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.appearance_anchors import (
    APPEARANCE_FIELDS,
    contains_keyword,
    extract_appearance_anchors,
    extract_appearance_from_text,
    is_appearance_clause,
    merge_appearance_anchors,
    normalize_clothing_value,
    truncate_at_clause_boundary,
)
from penshot.neopen.constants.appearance import GARMENT_NOUNS
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    CharacterContract,
    GlobalConsistencyContract,
)
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed

# 取自 data 下真实剧本解析结果，防止测试数据与线上漂移
LIN_DESCRIPTION = (
    "20岁女学生，神情焦急后转为惊喜，穿着素色外套（肩头微湿），手持手帕和湿漉漉的诗集。"
)
LIN_OUTFIT = {
    "description": "素色外套，肩头因雨水微湿，搭配学生气质的简约装扮。",
    "color": "素色/浅灰",
    "style": "休闲学生风",
    "material": "棉质/混纺",
}
CHEN_DESCRIPTION = (
    "22岁兼职外卖员，穿着黄色雨衣，骑着电动车，动作匆忙但细心，从雨衣里掏出干毛巾。"
)
CHEN_OUTFIT = {
    "description": "亮黄色连帽雨衣，内搭深色T恤，下身深色长裤，脚穿防滑鞋。",
    "color": "黄色",
    "style": "功能性工装",
    "material": "PVC/防水尼龙",
}

EN_DESCRIPTION = (
    "25-year-old male, short black hair, wearing a yellow raincoat, "
    "holding a wet notebook, smiling nervously."
)
EN_OUTFIT = {
    "description": (
        "A yellow hooded raincoat with dark trousers, wearing glasses, "
        "a kind expression."
    ),
    "color": "yellow",
    "style": "functional workwear",
    "material": "PVC",
}


def test_ac001_lin_clothing_exact():
    """AC-001：结构化服装覆盖自由文本，产出去情绪/动作/道具的精确锚点"""
    anchors = extract_appearance_anchors(LIN_DESCRIPTION, LIN_OUTFIT)

    assert anchors["clothing"] == "素色浅灰棉质外套，肩头微湿"
    clothing = anchors["clothing"]
    for banned in ("神情", "焦急", "惊喜", "手持", "湿漉"):
        assert banned not in clothing


def test_ac002_chen_clothing_contains_garment_and_excludes_actions():
    """AC-002：保留雨衣类服装，剔除骑行/动作/道具子句"""
    anchors = extract_appearance_anchors(CHEN_DESCRIPTION, CHEN_OUTFIT)

    clothing = anchors["clothing"]
    assert "亮黄色连帽雨衣" in clothing
    for banned in ("骑着电动车", "动作匆忙", "掏出干毛巾"):
        assert banned not in clothing


def test_ac003_suffix_identical_across_ten_fragments():
    """AC-003：同一角色在所有片段中的锚点后缀完全一致且只用白名单字段"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    character = CharacterContract(name="林小雨")
    character._extract_appearance_features(LIN_DESCRIPTION, LIN_OUTFIT)

    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.characters["林小雨"] = character

    suffixes = {
        PromptConverterAgent._build_character_anchor_suffix("林小雨", contract)
        for _ in range(10)
    }

    assert len(suffixes) == 1
    suffix = suffixes.pop()
    assert suffix == (
        "[Character consistency: 林小雨, clothing: 素色浅灰棉质外套，肩头微湿]"
    )
    assert set(character.appearance_anchors) <= set(APPEARANCE_FIELDS)


def test_structured_outfit_does_not_mix_free_text_noise():
    """FR-001/FR-002：结构化服装存在时不再混入自由文本的年龄/情绪噪声"""
    anchors = extract_appearance_anchors(LIN_DESCRIPTION, LIN_OUTFIT)

    assert anchors == {"clothing": "素色浅灰棉质外套，肩头微湿"}


def test_outfit_accessories_kept_as_separate_anchor():
    """char_002 缺陷回归：结构化服装中的“佩戴眼镜”应落入 accessories"""
    outfit = {
        "description": "得体的浅色连衣裙或套装，佩戴眼镜，气质温婉。",
        "color": "浅色",
        "style": "知性教师风",
        "material": "棉质",
    }

    anchors = extract_appearance_anchors("", outfit)

    assert anchors["accessories"] == "佩戴眼镜"
    assert anchors["clothing"] == "得体的浅色连衣裙或套装"
    assert "气质温婉" not in anchors["clothing"]


def test_english_outfit_extracts_clothing_and_accessories():
    """英文结构化服装：引导词/冠词剥离，配饰单列，情绪子句排除"""
    anchors = extract_appearance_anchors("", EN_OUTFIT)

    assert anchors["clothing"] == "yellow hooded raincoat with dark trousers"
    assert anchors["accessories"] == "glasses"
    assert "kind" not in anchors["clothing"]
    assert "，" not in anchors["clothing"]


def test_english_free_text_extracts_whitelist_fields():
    """英文自由文本：年龄/性别/发型/服装按白名单提取，动作情绪子句排除"""
    anchors = extract_appearance_from_text(EN_DESCRIPTION)

    assert anchors["age"] == "25-year-old"
    assert anchors["gender"] == "male"
    assert anchors["hair"] == "short black hair"
    assert anchors["clothing"] == "yellow raincoat"
    for banned in ("holding", "wet notebook", "smiling", "nervously"):
        assert banned not in anchors["clothing"]


def test_english_clause_boundary_uses_comma_space():
    """英文子句截断按 “, ” 拼接，不产生中文逗号或半截词"""
    text = "yellow hooded raincoat, dark trousers, glasses"

    assert truncate_at_clause_boundary(text, 30) == "yellow hooded raincoat"
    assert (
        truncate_at_clause_boundary("yellow hooded raincoat", 10)
        == "yellow hooded raincoat"
    )


def test_english_keywords_match_on_word_boundary():
    """英文按单词边界匹配：“raincoat”命中，“captain”不因 cap 误命中"""
    assert contains_keyword("a yellow raincoat", GARMENT_NOUNS)
    assert not contains_keyword("captain of the team", GARMENT_NOUNS)


def test_english_clause_classification_excludes_emotion_and_actions():
    """英文外观判定与中文同规则：动作/情绪/道具子句不属于外观"""
    assert is_appearance_clause("wearing a yellow raincoat")
    assert not is_appearance_clause("smiling nervously")
    assert not is_appearance_clause("holding a wet notebook")


def test_whitelist_fields_only():
    """FR-004：任何提取结果都只能落在白名单字段内"""
    for anchors in (
        extract_appearance_anchors(LIN_DESCRIPTION, LIN_OUTFIT),
        extract_appearance_anchors(CHEN_DESCRIPTION, CHEN_OUTFIT),
        extract_appearance_anchors(LIN_DESCRIPTION),
    ):
        assert set(anchors) <= set(APPEARANCE_FIELDS)


def test_free_text_fallback_has_no_sentence_fragments():
    """缺少结构化服装时，自由文本回退仍不得带情绪/动作/半截词"""
    anchors = extract_appearance_from_text(LIN_DESCRIPTION)

    assert anchors["clothing"] == "素色外套，肩头微湿"
    for banned in ("神情", "焦急", "惊喜", "手持", "湿漉"):
        assert banned not in anchors["clothing"]


def test_merge_first_value_wins():
    """FR-005：同字段首值优先，重复提取不会改变既有锚点"""
    character = CharacterContract(name="林小雨")
    character._extract_appearance_features(LIN_DESCRIPTION, LIN_OUTFIT)
    first = dict(character.appearance_anchors)

    character._extract_appearance_features(CHEN_DESCRIPTION, CHEN_OUTFIT)

    assert character.appearance_anchors == first
    assert character.appearance_anchors["clothing"].startswith("素色浅灰棉质外套")


def test_merge_appearance_anchors_ignores_unknown_and_empty():
    """合并只接受白名单字段，空值不覆盖已有值"""
    merged = merge_appearance_anchors(
        {"clothing": "素色外套"},
        {"clothing": "", "hair": "短发", "mood": "紧张"},
    )

    assert merged == {"clothing": "素色外套", "hair": "短发"}


def test_clause_boundary_truncation_never_cuts_words():
    """长度限制只落在子句边界；单子句超限时整句保留"""
    text = "素色浅灰棉质外套，肩头微湿，搭配简约装扮"

    assert truncate_at_clause_boundary(text, 12) == "素色浅灰棉质外套"
    assert truncate_at_clause_boundary("素色浅灰棉质外套", 4) == "素色浅灰棉质外套"
    assert truncate_at_clause_boundary(text, 0) == text


def test_normalize_clothing_value_dedupes_and_strips_cause():
    """规范化去成因、去重、去首尾标点，不产生重复子句"""
    value = "素色外套，素色外套，肩头因雨水微湿。"

    assert normalize_clothing_value(value) == "素色外套，肩头微湿"


def test_is_appearance_clause_excludes_emotion_and_action():
    """白名单判定：情绪、动作、道具子句不属于外观描述"""
    assert is_appearance_clause("穿着素色外套")
    assert not is_appearance_clause("神情焦急后转为惊喜")
    assert not is_appearance_clause("手持手帕和湿漉漉的诗集")
    assert not is_appearance_clause("骑着电动车")


def _outfit_script(include_outfit: bool = True) -> SimpleNamespace:
    """构造解析器接线测试所需的 ParsedScript 结构"""
    outfits = (
        [
            SimpleNamespace(
                character="林小雨",
                description=LIN_OUTFIT["description"],
                color=LIN_OUTFIT["color"],
                style=LIN_OUTFIT["style"],
                material=LIN_OUTFIT["material"],
            )
        ]
        if include_outfit
        else []
    )
    return SimpleNamespace(
        scenes=[
            SimpleNamespace(
                id="scene_001",
                location="咖啡店外",
                time_of_day="day",
                elements=[SimpleNamespace(character="林小雨")],
            )
        ],
        characters=[
            SimpleNamespace(name="林小雨", description=LIN_DESCRIPTION),
        ],
        global_metadata=SimpleNamespace(
            character_outfits=outfits,
            continuity_notes="",
            audio_atmosphere="neutral",
        ),
        title="雨夜来电",
    )


def test_parser_prefers_character_outfits():
    """T-103：解析器读取 character_outfits 写入契约，且压过自由文本"""
    contract = build_contract_from_parsed(_outfit_script(), script_id="s1")

    assert contract.characters["林小雨"].appearance_anchors == {
        "clothing": "素色浅灰棉质外套，肩头微湿"
    }


def test_parser_falls_back_to_free_text_without_outfit():
    """T-103：缺少结构化服装时回退自由文本，仍排除情绪与动作"""
    contract = build_contract_from_parsed(
        _outfit_script(include_outfit=False), script_id="s1"
    )

    clothing = contract.characters["林小雨"].appearance_anchors.get("clothing")
    assert clothing == "素色外套，肩头微湿"
    for banned in ("神情", "焦急", "手持", "湿漉"):
        assert banned not in clothing
