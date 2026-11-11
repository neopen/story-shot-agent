"""场景跳转连续性修复回归测试。

覆盖三点：
1. ``scene_jump`` 只在缺乏视觉切换提示时上报，且跨轮不重复触发修复；
2. 分镜阶段可在场景边界插入过渡镜头；
3. 分镜节点循环超限保留 ``NEEDS_HUMAN`` 语义，且循环计数只自增一次。
"""

from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import (
    ContinuityGuardianChecker,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssueType,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityRepairParams,
)
from penshot.neopen.agent.shot_segmenter.llm_shot_segmenter import LLMShotSegmenter
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
    ShotType,
)
from penshot.neopen.agent.shot_segmenter_agent import ShotSegmenterAgent
from penshot.neopen.agent.workflow.workflow_decision import PipelineDecision
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


def _shot(shot_id: str, scene_id: str, shot_type: ShotType, **kwargs) -> ShotInfo:
    """构造镜头"""
    return ShotInfo(
        id=shot_id,
        scene_id=scene_id,
        description=f"{shot_id} 描述",
        shot_type=shot_type,
        duration=3.0,
        **kwargs,
    )


def _scene_jump_issues(shots) -> list:
    """执行一次场景连续性检查并返回 scene_jump 问题"""
    checker = ContinuityGuardianChecker()
    result = ContinuityCheckResult()
    checker.check_scene_continuity({"shot_sequence": ShotSequence(shots=shots)}, result)
    return [i for i in result.issues if i.type == ContinuityIssueType.SCENE_JUMP]


class TestSceneJumpDetection:
    """场景跳转检测"""

    def test_reports_when_adjacent_types_are_identical(self):
        """相邻镜头景别相同且场景变化时上报一次"""
        issues = _scene_jump_issues(
            [
                _shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT),
                _shot("shot_002", "scene_002", ShotType.MEDIUM_SHOT),
                _shot("shot_003", "scene_002", ShotType.CLOSE_UP),
            ]
        )

        assert len(issues) == 1
        assert issues[0].auto_fixable is True
        assert issues[0].metadata["prev_scene"] == "scene_001"
        assert issues[0].metadata["next_scene"] == "scene_002"

    def test_same_boundary_is_not_reported_twice_across_rounds(self):
        """同一场景边界跨轮不再重复上报，避免反复修复"""
        checker = ContinuityGuardianChecker()
        first = ContinuityCheckResult()
        checker.check_scene_continuity(
            {
                "shot_sequence": ShotSequence(
                    shots=[
                        _shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT),
                        _shot("shot_002", "scene_002", ShotType.MEDIUM_SHOT),
                    ]
                )
            },
            first,
        )
        assert (
            len([i for i in first.issues if i.type == ContinuityIssueType.SCENE_JUMP])
            == 1
        )

        second = ContinuityCheckResult()
        checker.check_scene_continuity(
            {
                "shot_sequence": ShotSequence(
                    shots=[
                        _shot("shot_101", "scene_001", ShotType.MEDIUM_SHOT),
                        _shot("shot_102", "scene_002", ShotType.MEDIUM_SHOT),
                    ]
                )
            },
            second,
        )
        assert not [
            i for i in second.issues if i.type == ContinuityIssueType.SCENE_JUMP
        ]

    def test_transition_shot_smooths_boundary(self):
        """边界已有过渡镜头时不再上报"""
        issues = _scene_jump_issues(
            [
                _shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT),
                _shot(
                    "shot_002_trans",
                    "scene_002",
                    ShotType.WIDE_SHOT,
                    is_transition=True,
                ),
                _shot("shot_003", "scene_002", ShotType.MEDIUM_SHOT),
            ]
        )

        assert not issues


class TestTransitionShotInsertion:
    """分镜阶段插入过渡镜头"""

    def test_inserts_transition_with_different_type(self):
        """在景别相同的场景边界插入不同景别的过渡镜头"""
        segmenter = LLMShotSegmenter.__new__(LLMShotSegmenter)
        sequence = ShotSequence(
            shots=[
                _shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT),
                _shot("shot_002", "scene_002", ShotType.MEDIUM_SHOT),
                _shot("shot_003", "scene_002", ShotType.CLOSE_UP),
            ]
        )

        result = segmenter._insert_transition_shots(sequence)

        assert len(result.shots) == 4
        transition = result.shots[1]
        assert transition.is_transition is True
        assert transition.shot_type == ShotType.WIDE_SHOT
        assert transition.scene_id == "scene_002"
        # 时间轴应连续重排
        assert result.shots[0].start_time == 0.0
        assert result.shots[1].start_time == 3.0
        assert result.shots[2].start_time == 4.2

    def test_does_not_insert_when_type_differs(self):
        """相邻景别不同说明已有切换提示，不插入过渡镜头"""
        segmenter = LLMShotSegmenter.__new__(LLMShotSegmenter)
        sequence = ShotSequence(
            shots=[
                _shot("shot_001", "scene_001", ShotType.CLOSE_UP),
                _shot("shot_002", "scene_002", ShotType.WIDE_SHOT),
            ]
        )

        result = segmenter._insert_transition_shots(sequence)

        assert len(result.shots) == 2


class TestLocalSceneJumpRepair:
    """场景跳转变更分镜后由本地确定性修复，不重跑 LLM"""

    class _NoLLMSegmenter:
        def split(self, *args, **kwargs):
            raise AssertionError("场景跳转修复不应重跑 LLM 分镜生成")

    def _agent(self, sequence: ShotSequence) -> ShotSegmenterAgent:
        agent = ShotSegmenterAgent.__new__(ShotSegmenterAgent)
        agent.current_repair_params = None
        agent.current_historical_context = None
        agent.last_shot_sequence = sequence
        agent.segment_history = []
        agent.segmenter = self._NoLLMSegmenter()
        agent.enhancer = None
        agent.llm_confidence = 0.7
        agent.always_enhance = True
        agent._increase_shot_count = False
        agent._prefer_shorter_shots = False
        return agent

    def _sequence(self) -> ShotSequence:
        return ShotSequence(
            shots=[
                _shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT),
                _shot("shot_002", "scene_002", ShotType.MEDIUM_SHOT),
                _shot("shot_003", "scene_002", ShotType.CLOSE_UP),
            ]
        )

    def test_process_reuses_existing_shots_without_llm(self):
        """仅场景跳转时插入过渡镜头并记录修复历史"""
        agent = self._agent(self._sequence())
        agent.current_repair_params = QualityRepairParams(
            fix_needed=True, issue_types=["scene_jump"]
        )

        result = agent.process(None)

        assert len(result.shots) == 4
        assert result.shots[1].is_transition is True
        assert result.metadata["repair_history"][0]["repair_params"]["issue_types"] == [
            "scene_jump"
        ]
        # 修复后同一个边界不再被上报，保证单轮收敛
        assert not _scene_jump_issues(result.shots)

    def test_mixed_issues_still_regenerate(self):
        """混合问题仍走 LLM 重新生成，本地修复只处理纯结构性问题"""
        agent = self._agent(self._sequence())
        agent.current_repair_params = QualityRepairParams(
            fix_needed=True, issue_types=["scene_jump", "shot_insufficient"]
        )

        assert agent._repair_scene_jumps_locally() is None
        assert len(agent.last_shot_sequence.shots) == 3


class TestSegmentLoopBudget:
    """分镜节点循环预算"""

    def _state(self) -> WorkflowState:
        state = WorkflowState.from_raw_script("测试剧本内容")
        state.domain.shot_sequence = ShotSequence(
            shots=[_shot("shot_001", "scene_001", ShotType.MEDIUM_SHOT)]
        )
        return state

    def test_counter_increments_once_per_execution(self):
        """一次分镜执行只消耗一次节点循环配额"""
        decision = PipelineDecision()
        state = self._state()

        decision.decide_after_splitting(state)

        assert state.execution.node_current_loops[PipelineNode.SEGMENT_SHOT] == 1

    def test_exceeded_keeps_needs_human_instead_of_failed(self):
        """循环超限时保留 NEEDS_HUMAN，不再改写为 FAILED"""
        decision = PipelineDecision()
        state = self._state()
        state.execution.node_current_loops[PipelineNode.SEGMENT_SHOT] = 4

        result = decision.decide_after_splitting(state)

        assert result == PipelineState.NEEDS_HUMAN
