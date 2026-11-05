"""一致性契约校验器（Validator）回退链路测试。

覆盖切镜 / 切片两个决策点：契约违规时触发回退（NEEDS_RETRY / NEEDS_REPAIR），
并确认违规项被写入 DomainState.contract_violations 供审计。
"""

import pytest

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _state(contract=None) -> WorkflowState:
    """构造最小工作流状态"""
    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = contract
    return state


def _contract(character_names) -> GlobalConsistencyContract:
    """构造只登记角色的最小契约"""
    contract = GlobalConsistencyContract(script_id="script_1", task_id="task_1")
    for name in character_names:
        contract.register_character(name, 1)
    return contract


def _shot(shot_id: str, main_character=None) -> ShotInfo:
    """构造镜头"""
    return ShotInfo(
        id=shot_id,
        scene_id="scene_001",
        description="测试镜头",
        duration=3.0,
        main_character=main_character,
    )


def _fragment(fragment_id: str, shot_id: str) -> VideoFragment:
    """构造片段"""
    return VideoFragment(id=fragment_id, shot_id=shot_id, duration=3.0)


class TestContractValidatorRollback:
    """契约校验回退链路"""

    @pytest.fixture
    def decision(self):
        return PipelineDecision()

    def test_split_unknown_character_retries(self, decision):
        """切镜出现契约外角色：可重试时回退到 SEGMENT_SHOT"""
        contract = _contract(["小明"])
        state = _state(contract)
        state.domain.shot_sequence = ShotSequence(
            shots=[_shot("shot_001", "小明"), _shot("shot_002", "路人甲")]
        )

        result = decision.decide_after_splitting(state)

        assert result == PipelineState.NEEDS_RETRY
        assert len(state.domain.contract_violations) == 1
        assert state.domain.contract_violations[0]["type"] == "unknown_character"
        assert state.execution.stage_current_retries[PipelineNode.SEGMENT_SHOT] == 1

        # 契约违规项同时生成 Repairer 修复参数（供下次切镜消费）
        params = state.domain.repair_params[PipelineNode.SEGMENT_SHOT]
        assert params.issue_types == ["unknown_character"]
        suggestion = params.suggestions["shot_002"][0]
        assert "未登记到一致性契约" in suggestion
        assert "小明" in suggestion

    def test_split_unknown_character_repair_when_retry_exhausted(self, decision):
        """切镜出现契约外角色：重试耗尽时转 NEEDS_REPAIR"""
        contract = _contract(["小明"])
        state = _state(contract)
        state.domain.shot_sequence = ShotSequence(shots=[_shot("shot_001", "路人甲")])
        state.execution.stage_current_retries[PipelineNode.SEGMENT_SHOT] = 3

        result = decision.decide_after_splitting(state)

        assert result == PipelineState.NEEDS_REPAIR

    def test_split_without_contract_passes(self, decision):
        """无契约时不阻塞：正常返回 SUCCESS"""
        state = _state(None)
        state.domain.shot_sequence = ShotSequence(shots=[_shot("shot_001", "路人甲")])

        result = decision.decide_after_splitting(state)

        assert result == PipelineState.SUCCESS
        assert state.domain.contract_violations == []

    def test_fragment_orphan_and_unknown_repairs(self, decision):
        """切片出现孤立片段 / 契约外角色：回退到 SPLIT_VIDEO"""
        contract = _contract(["小明"])
        state = _state(contract)
        state.domain.shot_sequence = ShotSequence(shots=[_shot("shot_001", "路人甲")])
        state.domain.fragment_sequence = FragmentSequence(
            fragments=[
                _fragment("frag_001", "shot_001"),
                _fragment("frag_002", "shot_999"),
            ]
        )

        result = decision.decide_after_fragmenting(state)

        assert result == PipelineState.NEEDS_REPAIR
        issue_types = {issue["type"] for issue in state.domain.contract_violations}
        assert {"unknown_character", "orphan_fragment"} == issue_types

        # 切片阶段的 Repairer 参数应包含孤立片段的重新关联建议
        params = state.domain.repair_params[PipelineNode.SPLIT_VIDEO]
        assert "orphan_fragment" in params.issue_types
        assert "shot_001" in params.suggestions["frag_002"][0]

    def test_repeated_violation_deduplicates(self, decision):
        """同一违规项重复触发时审计列表不重复膨胀"""
        contract = _contract(["小明"])
        state = _state(contract)
        state.domain.shot_sequence = ShotSequence(shots=[_shot("shot_001", "路人甲")])

        decision.decide_after_splitting(state)
        decision.decide_after_splitting(state)

        assert len(state.domain.contract_violations) == 1

    def test_fragment_all_valid_passes(self, decision):
        """片段全部合规时返回 SUCCESS"""
        contract = _contract(["小明"])
        state = _state(contract)
        state.domain.shot_sequence = ShotSequence(shots=[_shot("shot_001", "小明")])
        state.domain.fragment_sequence = FragmentSequence(
            fragments=[_fragment("frag_001", "shot_001")]
        )

        result = decision.decide_after_fragmenting(state)

        assert result == PipelineState.SUCCESS
        assert state.domain.contract_violations == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
