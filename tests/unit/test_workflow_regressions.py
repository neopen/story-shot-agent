"""工作流回归测试：历史统计、阶段问题、连续性缓存、审查缓存与音频链。"""

import time
from types import SimpleNamespace

from penshot.neopen.agent.base_repairable_agent import BaseRepairableAgent
from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import (
    ContinuityGuardianChecker,
    _canonical_action,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityIssueType,
)
from penshot.neopen.agent.prompt_converter.llm_prompt_converter import (
    LLMPromptConverter,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoPrompt,
)
from penshot.neopen.agent.quality_auditor.llm_quality_auditor import (
    LLMQualityAuditor,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_enum import AuditStatus
from penshot.neopen.agent.workflow.workflow_memory import (
    WorkflowMemory,
    stage_issues_key,
    unwrap_stage_stats,
)
from penshot.neopen.knowledge.memory.memory_models import MemoryLevel
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.shot_config import ShotConfig


# ===================== 历史统计包装解包 =====================


def test_unwrap_stage_stats_accepts_wrapper_and_plain():
    wrapped = {"summary": "x", "latest_stats": {"completeness_score": 0.3}}
    assert unwrap_stage_stats(wrapped) == {"completeness_score": 0.3}
    assert unwrap_stage_stats({"completeness_score": 0.9}) == {
        "completeness_score": 0.9
    }
    assert unwrap_stage_stats(None) == {}
    assert unwrap_stage_stats("bad") == {}


class _DummyRepairableAgent(BaseRepairableAgent):
    def process(self, *args, **kwargs):
        return None

    def detect_issues(self, result, node_params):
        return []


def test_empty_history_stats_not_marked_poor():
    """无历史统计时不能判定为 poor，否则首轮误开增强验证。"""
    agent = _DummyRepairableAgent()
    agent.apply_historical_context({"historical_stats": {}})

    insights = agent.get_historical_insights()
    assert insights.get("stats") == {}
    assert "quality_level" not in insights


def test_poor_history_stats_still_detected():
    agent = _DummyRepairableAgent()
    agent.apply_historical_context({"historical_stats": {"completeness_score": 0.3}})

    assert agent.get_historical_insights()["quality_level"] == "poor"


# ===================== 阶段问题去重与替换 =====================


class _FakeMemory:
    def __init__(self):
        self.store = {}

    def get(self, key, level=None, default=None):
        return self.store.get(key, default)

    def add(self, input_text, output_text, level=None, metadata=None):
        self.store[input_text] = output_text


def _issue(code, description, fragment_id="frag_001"):
    return {
        "issue_code": code,
        "issue_type": code,
        "description": description,
        "fragment_id": fragment_id,
        "source_node": "convert_prompt",
    }


def test_stage_issues_deduped_and_replaced():
    memory = _FakeMemory()
    workflow_memory = WorkflowMemory("SN", memory, None)
    key = stage_issues_key("convert_prompt")

    workflow_memory.store_stage_issues(
        "convert_prompt", [_issue("a", "重复"), _issue("a", "重复")]
    )
    assert len(workflow_memory.get_memory_list(key, MemoryLevel.SHORT_TERM)) == 1

    workflow_memory.store_stage_issues("convert_prompt", [_issue("b", "新问题")])
    stored = workflow_memory.get_memory_list(key, MemoryLevel.SHORT_TERM)
    assert [item["issue_code"] for item in stored] == ["b"]


def test_stage_issues_cleared_when_round_has_none():
    memory = _FakeMemory()
    workflow_memory = WorkflowMemory("SN", memory, None)
    key = stage_issues_key("segment_shot")

    workflow_memory.store_stage_issues("segment_shot", [_issue("a", "旧问题")])
    workflow_memory.store_stage_issues("segment_shot", [])

    assert workflow_memory.get_memory_list(key, MemoryLevel.SHORT_TERM) == []


# ===================== 动作判定与跨轮缓存 =====================


def test_negated_action_is_ignored():
    assert _canonical_action("他没有回头") is None
    assert _canonical_action("她没回头继续走") is not None  # 走的动作未被否定


def test_non_negated_turn_action_matches_group():
    canonical = _canonical_action("他回头看")
    assert canonical is not None and "回头" in canonical


def _action_break_shots():
    return SimpleNamespace(
        shots=[
            SimpleNamespace(
                id="s1",
                description="小明向前走",
                main_character="小明",
                scene_id="scene_001",
            ),
            SimpleNamespace(
                id="s2",
                description="小明转身跑开",
                main_character="小明",
                scene_id="scene_001",
            ),
        ]
    )


def test_action_break_reported_every_round_and_not_auto_fixable():
    """跨轮复用 checker 时，同一动作断裂每轮都必须重新上报。"""
    checker = ContinuityGuardianChecker()
    context = {"shot_sequence": _action_break_shots()}

    first = checker.check_all_continuity(context)
    second = checker.check_all_continuity(context)

    for result in (first, second):
        issues = result.issues_by_type.get(ContinuityIssueType.ACTION_BREAK.value)
        assert issues
        assert all(issue.auto_fixable is False for issue in issues)


# ===================== LLM 审查内容指纹缓存 =====================


class _CountingAuditor(LLMQualityAuditor):
    def __init__(self):
        self.calls = 0
        super().__init__(llm_client=None, config=ShotConfig(enable_llm=False))

    def _call_llm_audit(self, instructions, historical_context=None):
        self.calls += 1
        return {
            "status": AuditStatus.PASSED.value,
            "summary": "ok",
            "issues": [],
            "fragments_checked": [
                fragment.fragment_id for fragment in instructions.fragments
            ],
            "quality_score": 90,
            "timestamp": time.time(),
        }


def _audit_instructions(prompt="a"):
    return SimpleNamespace(
        fragments=[AIVideoPrompt(fragment_id="frag_001", prompt=prompt, duration=2)],
        project_info={"title": "测试"},
    )


def test_llm_audit_reruns_when_prompt_changes():
    auditor = _CountingAuditor()
    instructions = _audit_instructions("原始提示词")

    auditor.audit(instructions)
    assert auditor.calls == 1

    # 内容未变时走缓存
    auditor.audit(instructions)
    assert auditor.calls == 1

    # 修复轮改写提示词后必须重新审查
    auditor.audit(_audit_instructions("修复后的提示词"))
    assert auditor.calls == 2


# ===================== 音频链跨轮重置 =====================


class _TrackingConverter(LLMPromptConverter):
    def __init__(self):
        self.seen_audio_ids = []
        super().__init__(llm_client=None, config=ShotConfig(enable_llm=False))

    def _build_element_map(self):
        self.element_map = {}

    def _convert_fragment_with_llm(self, fragment, historical_context):
        self.seen_audio_ids.append(self.last_audio_id)
        return AIVideoPrompt(fragment_id=fragment.id, prompt="test", duration=2)


def test_convert_resets_audio_chain_per_round():
    converter = _TrackingConverter()
    converter.last_audio_id = "audio_010"

    fragment_sequence = SimpleNamespace(
        source_info={},
        stats={},
        fragments=[SimpleNamespace(id="frag_001")],
    )

    converter.convert(fragment_sequence, ParsedScript(title="测试"), None, None)

    assert converter.seen_audio_ids == [None]
