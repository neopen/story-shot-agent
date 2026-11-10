"""契约驱动修复（Repairer）单元测试。

覆盖 Validator 违规项 -> 修复参数转换、契约锚点描述、违规项去重与
RePairer（ContinuityRepairGenerator）按契约注入修复建议。
"""

from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    AssetContract,
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityIssue,
    ContinuityIssueType,
    ContinuitySeverity,
)
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import (
    ContinuityRepairGenerator,
)
from penshot.neopen.agent.continuity_guardian.contract_repair import (
    build_contract_repair_params,
    describe_character_anchors,
    describe_prop_anchors,
    describe_scene_anchors,
    describe_style_anchors,
    group_violations_by_stage,
    merge_repair_params,
    merge_violations,
)
from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    QualityRepairParams,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo
from penshot.neopen.agent.workflow.workflow_models import PipelineNode


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


def _full_contract() -> GlobalConsistencyContract:
    """构造带角色/场景/风格/道具锚点的完整契约"""
    contract = _contract(["小明"])
    contract.characters["小明"].appearance_anchors["clothing"] = "蓝色风衣"

    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="教室",
            time_of_day="day",
            characters_in_scene=["小明"],
        )
    )
    contract.set_style_anchor("genre", "thriller")
    contract.register_asset(
        AssetContract(
            asset_id="prop_001",
            asset_type="prop",
            owner_name="旧怀表",
            asset_ref="data/assets/prop_001.png",
        )
    )
    contract.register_asset(
        AssetContract(
            asset_id="sheet_001",
            asset_type="character_sheet",
            owner_name="小明",
            asset_ref="data/assets/character_001.png",
        )
    )
    return contract


def _issue(issue_type: ContinuityIssueType, **kwargs) -> ContinuityIssue:
    """构造连续性问题"""
    return ContinuityIssue(
        id=kwargs.pop("id", "issue_001"),
        type=issue_type,
        description=kwargs.pop("description", "测试连续性问题"),
        **kwargs,
    )


class TestContractAnchorDescriptions:
    """契约锚点 -> 修复约束文本"""

    def test_character_anchor_includes_appearance_and_asset(self):
        """角色锚点包含外观与参考资产"""
        text = describe_character_anchors(_full_contract(), "小明")
        assert "角色「小明」" in text
        assert "蓝色风衣" in text
        assert "data/assets/character_001.png" in text

    def test_character_anchor_unknown_returns_empty(self):
        """未登记角色不产生锚点"""
        assert describe_character_anchors(_full_contract(), "路人甲") == ""
        assert describe_character_anchors(_full_contract(), "") == ""

    def test_style_anchor_uses_english_prefix(self):
        """风格锚点复用英文六维前缀"""
        text = describe_style_anchors(_full_contract())
        assert "[Style:" in text
        assert "high contrast lighting" in text

    def test_scene_anchor_includes_location_and_time(self):
        """场景锚点包含地点与时间"""
        text = describe_scene_anchors(_full_contract(), "scene_001")
        assert "教室" in text
        assert "day" in text

    def test_prop_anchor_matches_asset_owner(self):
        """道具锚点仅在描述命中道具名时返回"""
        text = describe_prop_anchors(_full_contract(), "角色检查手里的旧怀表")
        assert "旧怀表" in text
        assert "data/assets/prop_001.png" in text
        assert describe_prop_anchors(_full_contract(), "无关描述") == ""


class TestContractRepairParams:
    """Validator 违规项 -> 修复参数"""

    def test_unknown_character_builds_constraint(self):
        """未知角色违规转换为契约约束建议"""
        violation = {
            "type": "unknown_character",
            "stage": "segment_shot",
            "shot_id": "shot_002",
            "character": "路人甲",
            "message": "镜头 shot_002 的角色 路人甲 不在一致性契约中",
        }
        params = build_contract_repair_params(
            [violation], PipelineNode.SEGMENT_SHOT, _full_contract()
        )

        assert params is not None
        assert params.fix_needed is True
        assert params.issue_types == ["unknown_character"]
        assert params.issue_count == 1
        suggestion = params.suggestions["shot_002"][0]
        assert "路人甲" in suggestion
        assert "小明" in suggestion

    def test_orphan_fragment_lists_valid_shots(self):
        """孤立片段违规建议重新关联到有效镜头"""
        violation = {
            "type": "orphan_fragment",
            "stage": "split_video",
            "fragment_id": "frag_002",
            "shot_id": "shot_999",
            "message": "片段 frag_002 关联的镜头 shot_999 不存在",
        }
        shot_sequence = type(
            "ShotSequenceStub", (), {"shots": [_shot("shot_001", "小明")]}
        )()

        params = build_contract_repair_params(
            [violation], PipelineNode.SPLIT_VIDEO, None, shot_sequence
        )

        assert params.fragments == ["frag_002"]
        suggestion = params.suggestions["frag_002"][0]
        assert "shot_999" in suggestion
        assert "shot_001" in suggestion

    def test_empty_violations_returns_none(self):
        """无违规项时不生成修复参数"""
        assert build_contract_repair_params([], PipelineNode.SEGMENT_SHOT) is None
        assert build_contract_repair_params(None, PipelineNode.SEGMENT_SHOT) is None


class TestViolationAndParamMerging:
    """违规项与修复参数合并"""

    def test_merge_violations_deduplicates(self):
        """相同违规项重复出现时只保留一条"""
        violation = {
            "type": "unknown_character",
            "stage": "segment_shot",
            "shot_id": "shot_002",
            "character": "路人甲",
        }
        merged = merge_violations([violation], [dict(violation)])
        assert merged == [violation]

    def test_merge_violations_keeps_latest_limit(self):
        """违规项超过上限时保留最近记录"""
        violations = [
            {"type": "unknown_character", "shot_id": f"shot_{i:03d}"} for i in range(60)
        ]
        merged = merge_violations([], violations, max_items=5)
        assert len(merged) == 5
        assert merged[-1]["shot_id"] == "shot_059"

    def test_group_violations_by_stage(self):
        """违规项按 stage 字段归档到工作流节点"""
        grouped = group_violations_by_stage(
            [
                {"type": "unknown_character", "stage": "segment_shot"},
                {"type": "orphan_fragment", "stage": "split_video"},
                {"type": "unknown_character", "stage": "unknown"},
            ]
        )
        assert len(grouped[PipelineNode.SEGMENT_SHOT]) == 1
        assert len(grouped[PipelineNode.SPLIT_VIDEO]) == 1

    def test_merge_repair_params_deduplicates_suggestions(self):
        """合并修复参数时建议去重、计数累加"""
        base = QualityRepairParams(
            fix_needed=True,
            issue_count=1,
            issue_types=["action_break"],
            suggestions={"global": ["补充动作镜头"]},
            severity_summary={"moderate": 1},
        )
        extra = QualityRepairParams(
            fix_needed=True,
            issue_count=1,
            issue_types=["unknown_character"],
            suggestions={"shot_002": ["角色未登记"], "global": ["补充动作镜头"]},
            severity_summary={"moderate": 1},
        )

        merged = merge_repair_params(base, extra)

        assert merged is not None
        assert merged.issue_count == 2
        assert merged.issue_types == ["action_break", "unknown_character"]
        assert merged.suggestions["global"] == ["补充动作镜头"]
        assert merged.severity_summary["moderate"] == 2

    def test_merge_repair_params_with_none(self):
        """任一侧为空时直接返回另一侧"""
        base = QualityRepairParams(fix_needed=True, suggestions={"global": ["x"]})
        assert merge_repair_params(base, None) is base
        assert merge_repair_params(None, base) is base
        assert merge_repair_params(None, None) is None


class TestRepairerContractDriven:
    """ContinuityRepairGenerator 按契约注入修复建议"""

    def test_appearance_issue_uses_character_anchor(self):
        """角色外观问题注入契约外观锚点"""
        issue = _issue(
            ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
            description="小明的外套颜色前后不一致",
            fragment_id="frag_001",
            metadata={"character": "小明"},
        )

        params = ContinuityRepairGenerator().generate_repair_params(
            [issue], PipelineNode.CONVERT_PROMPT, _full_contract()
        )

        suggestion = params.suggestions["frag_001"][0]
        assert "角色「小明」契约锚点" in suggestion
        assert "蓝色风衣" in suggestion

    def test_style_issue_uses_style_anchor(self):
        """风格问题注入契约风格锚点"""
        issue = _issue(
            ContinuityIssueType.STYLE_INCONSISTENT,
            description="部分片段风格偏亮",
            fragment_id="frag_002",
            severity=ContinuitySeverity.MAJOR,
        )

        params = ContinuityRepairGenerator().generate_repair_params(
            [issue], PipelineNode.CONVERT_PROMPT, _full_contract()
        )

        suggestion = params.suggestions["frag_002"][0]
        assert "[Style:" in suggestion
        assert "high contrast lighting" in suggestion

    def test_scene_issue_uses_scene_anchor(self):
        """场景问题注入契约场景锚点"""
        issue = _issue(
            ContinuityIssueType.SCENE_JUMP,
            description="场景切换缺少过渡",
            fragment_id="frag_003",
            scene_id="scene_001",
        )

        params = ContinuityRepairGenerator().generate_repair_params(
            [issue], PipelineNode.SEGMENT_SHOT, _full_contract()
        )

        suggestion = params.suggestions["frag_003"][0]
        assert "教室" in suggestion

    def test_without_contract_keeps_generic_suggestion(self):
        """无契约时保持通用修复建议，不注入锚点"""
        issue = _issue(
            ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE,
            description="角色外观变化",
            fragment_id="frag_001",
        )

        params = ContinuityRepairGenerator().generate_repair_params(
            [issue], PipelineNode.CONVERT_PROMPT, None
        )

        suggestion = params.suggestions["frag_001"][0]
        assert "契约锚点" not in suggestion

    def test_unmapped_issue_type_still_produces_suggestion(self):
        """未注册策略的问题类型也会生成修复建议"""
        issue = _issue(
            ContinuityIssueType.COMPOSITION_BREAK,
            description="构图断裂",
            fragment_id="frag_004",
        )

        params = ContinuityRepairGenerator().generate_repair_params(
            [issue], PipelineNode.CONVERT_PROMPT, None
        )

        assert params.suggestions["frag_004"][0].startswith("按一致性契约修复该问题")
