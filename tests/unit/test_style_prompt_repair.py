"""0.4.7 T-115：风格不一致的确定性收敛。

覆盖：
- 以多数片段风格为目标，统一 ``[Style: ...]`` 前缀并移除冲突风格短语；
- 无任何风格来源时不伪造修复，问题保持未收敛（转人工）；
- 仅修复被标记的片段，未标记片段保持原样；
- 修复参数只带问题码时也能触发全局风格收敛；
- 修复结论接入 ``record_repair_outcome``：收敛后 repaired，未收敛转人工。
"""

from types import SimpleNamespace

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prompt_converter.style_prompt_repair import (
    is_style_issue,
    repair_prompt_styles,
    repair_style_from_codes,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    BasicViolation,
    IssueType,
)

_ROMANCE_STYLE = "romance, soft warm lighting, warm palette"


def _violation(issue_code: str, fragment_id: str = "") -> BasicViolation:
    return BasicViolation.create(
        issue_code=issue_code,
        issue_type=IssueType.STYLE,
        issue_desc="片段风格与其他片段不一致",
        fragment_id=fragment_id or None,
    )


def _instructions(*prompts: AIVideoPrompt) -> AIVideoInstructions:
    return AIVideoInstructions(fragments=list(prompts))


def _prompt(fragment_id: str, text: str, style=None) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id=fragment_id, prompt=text, duration=3.0, style=style
    )


def test_repair_unifies_prefix_and_removes_conflicting_phrases():
    """多数风格为目标：补齐前缀并移除冲突的风格维度短语"""
    instructions = _instructions(
        _prompt("frag_001", "a woman waits by the window", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
        _prompt(
            "frag_003",
            "a car chase under neon rain, high contrast lighting, desaturated palette",
            "thriller, high contrast lighting, desaturated palette",
        ),
    )
    issue = _violation("style_inconsistent", "frag_003")

    result = repair_prompt_styles(instructions, [issue])

    assert result.target_style == _ROMANCE_STYLE
    assert result.resolved == [issue]
    assert result.unresolved == []
    assert {fragment.style for fragment in instructions.fragments} == {_ROMANCE_STYLE}
    repaired_prompt = instructions.fragments[2].prompt
    assert repaired_prompt.startswith(f"[Style: {_ROMANCE_STYLE}] ")
    assert "high contrast lighting" not in repaired_prompt
    assert "desaturated palette" not in repaired_prompt
    assert "a car chase under neon rain" in repaired_prompt
    assert any("frag_003" in action for action in result.actions)


def test_missing_style_source_keeps_issues_unresolved():
    """无任何风格来源时不做无效改写，问题保持未收敛"""
    instructions = _instructions(
        _prompt("frag_001", "a woman waits"),
        _prompt("frag_002", "a man reads a letter"),
    )
    issue = _violation("style_inconsistent", "frag_002")

    result = repair_prompt_styles(instructions, [issue])

    assert result.target_style == ""
    assert result.resolved == []
    assert result.unresolved == [issue]
    assert result.actions == []
    assert instructions.fragments[0].prompt == "a woman waits"
    assert instructions.fragments[1].prompt == "a man reads a letter"


def test_repair_only_touches_flagged_fragments():
    """带片段定位的问题只改该片段，不连带改写其余片段"""
    instructions = _instructions(
        _prompt("frag_001", "a woman waits", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
        _prompt("frag_003", "a train departs", "comedy, bright colors"),
    )

    result = repair_prompt_styles(
        instructions, [_violation("style_missing", "frag_003")]
    )

    assert instructions.fragments[0].prompt == "a woman waits"
    assert instructions.fragments[1].prompt == "a man reads a letter"
    assert instructions.fragments[2].style == _ROMANCE_STYLE
    assert len(result.actions) == 1


def test_fragment_not_in_instructions_routes_to_manual():
    """问题指向不存在的片段时无法确定性收敛，保持未收敛"""
    instructions = _instructions(
        _prompt("frag_001", "a woman waits", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
    )
    issue = _violation("style_inconsistent", "frag_404")

    result = repair_prompt_styles(instructions, [issue])

    assert result.unresolved == [issue]
    assert result.resolved == []
    assert result.actions == []


def test_repair_style_from_codes_triggers_on_style_codes_only():
    """修复参数只带问题码时，风格码触发收敛，其他码不触发"""
    instructions = _instructions(
        _prompt("frag_001", "a woman waits", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
        _prompt("frag_003", "a train departs", "comedy, bright colors"),
    )

    assert repair_style_from_codes(instructions, ["prompt_too_long"]).actions == []

    result = repair_style_from_codes(instructions, ["continuity_style_inconsistent"])

    assert result.target_style == _ROMANCE_STYLE
    assert {fragment.style for fragment in instructions.fragments} == {_ROMANCE_STYLE}
    assert result.actions


def test_is_style_issue_accepts_continuity_prefixed_code():
    """连续性检查产出的 continuity_style_inconsistent 也属于风格问题"""
    issue = BasicViolation.create(
        issue_code="continuity_style_inconsistent",
        issue_type=IssueType.CONTINUITY,
        issue_desc="片段风格突变",
    )
    assert is_style_issue(issue)
    non_style = BasicViolation.create(
        issue_code="prompt_too_long",
        issue_type=IssueType.PROMPT,
        issue_desc="提示词过长",
    )
    assert not is_style_issue(non_style)


def test_repair_prompts_records_repaired_for_converged_style():
    """确定性收敛后修复结论为 repaired，不残留人工项"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    instructions = _instructions(
        _prompt("frag_001", "a woman waits", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
        _prompt(
            "frag_003",
            "a train departs, high contrast lighting",
            "thriller, high contrast lighting",
        ),
    )

    agent.repair_prompts(
        instructions,
        [_violation("style_inconsistent", "frag_003")],
        SimpleNamespace(fragments=[]),
    )

    assert instructions.metadata["repair_status"] == "repaired"
    assert "requires_manual_fix" not in instructions.metadata
    assert {fragment.style for fragment in instructions.fragments} == {_ROMANCE_STYLE}


def test_repair_prompts_routes_style_without_source_to_manual():
    """无风格来源时不重试，直接标记人工处理而非 no_action_taken"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    instructions = _instructions(
        _prompt("frag_001", "a woman waits"),
        _prompt("frag_002", "a man reads a letter"),
    )

    agent.repair_prompts(
        instructions,
        [_violation("style_inconsistent", "frag_002")],
        SimpleNamespace(fragments=[]),
    )

    assert instructions.metadata["repair_status"] == "manual_required"
    manual = instructions.metadata["requires_manual_fix"]
    assert [entry["issue_code"] for entry in manual] == ["style_inconsistent"]
    assert manual[0]["fragment_id"] == "frag_002"
    assert instructions.fragments[0].prompt == "a woman waits"


def test_prompt_process_applies_style_repair_from_issue_codes():
    """生成路径中修复参数含风格码时先做确定性收敛"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    instructions = _instructions(
        _prompt("frag_001", "a woman waits", _ROMANCE_STYLE),
        _prompt("frag_002", "a man reads a letter", _ROMANCE_STYLE),
        _prompt(
            "frag_003",
            "a train departs, high contrast lighting",
            "thriller, high contrast lighting",
        ),
    )
    agent.current_historical_context = None
    agent.current_repair_params = SimpleNamespace(
        fix_needed=True,
        issue_types=["style"],
        issue_codes=["style_inconsistent"],
        suggestions={},
    )
    agent.convert_history = []
    agent.converter = SimpleNamespace(convert=lambda *args, **kwargs: instructions)

    result = agent.prompt_process(SimpleNamespace(fragments=[]), None)

    assert result is instructions
    assert {fragment.style for fragment in instructions.fragments} == {_ROMANCE_STYLE}
    assert "high contrast lighting" not in instructions.fragments[2].prompt
    assert instructions.fragments[2].prompt.startswith(f"[Style: {_ROMANCE_STYLE}] ")
