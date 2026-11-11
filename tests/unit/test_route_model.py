"""模型路由与结构化相机控制（M0.4.3）单元测试。

覆盖：路由特征抽取、YAML 规则优先级、兜底与时长能力兜底、结构化相机
透传与降级，以及 ROUTE_MODEL 节点的路由计划重建。
"""

import pytest

from penshot.config.config import settings
from penshot.neopen.agent.model_adapter import (
    adapt_instructions,
    get_adapter,
    get_capability,
)
from penshot.neopen.agent.model_adapter.model_models import (
    AestheticBias,
    ConsistencyNeed,
    MotionComplexity,
    RouteMode,
)
from penshot.neopen.agent.model_adapter.model_router import build_route_plan
from penshot.neopen.agent.model_adapter.route_features import extract_route_features
from penshot.neopen.agent.prompt_converter.camera_builder import build_camera_control
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
    CameraMotion,
)
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.constants.schema import CONTRACT_SCHEMA_VERSION


def _prompt(
    prompt_text: str,
    duration: float = 5.0,
    style: str | None = None,
    main_character: str | None = None,
) -> AIVideoPrompt:
    """构造片段提示词样本"""
    return AIVideoPrompt(
        fragment_id="frag_001",
        prompt=prompt_text,
        negative_prompt="blurry, distorted",
        duration=duration,
        model="runway_gen4",
        style=style,
        main_character=main_character,
    )


def _instructions(*prompts: AIVideoPrompt) -> AIVideoInstructions:
    """构造指令集样本"""
    return AIVideoInstructions(fragments=list(prompts))


class _FakeStorage:
    """记录落盘调用结果的存储桩"""

    def __init__(self) -> None:
        self.saved = []

    def save_obj_result(self, script_id, task_id, obj, filename):
        """记录保存结果"""
        self.saved.append((filename, obj))


# ---------------------------------------------------------------------------
# 结构化相机控制
# ---------------------------------------------------------------------------
def test_camera_builder_uses_shot_type_and_motion():
    camera = build_camera_control("close-up on her face", "close_up")
    assert camera.shot_type == "close_up"
    assert camera.rack_focus is True

    camera = build_camera_control("镜头横向移动跟随人物", None)
    assert camera.motion == CameraMotion.PAN
    assert camera.intensity > 0


def test_camera_builder_records_source_shot_type_for_traceability():
    """FR-034：camera 保留来源景别的归一化值与原始值"""
    camera = build_camera_control("slow pan across the room", "过肩")

    assert camera.shot_type == "over_shoulder"
    assert camera.source_shot_type == "over_shoulder"
    assert camera.shot_type_raw == "过肩"


def test_adapter_passes_structured_camera_when_supported():
    prompt = _prompt("close-up of a woman, rainy street")
    prompt.camera = build_camera_control("close-up", "close_up")

    package = get_adapter("kling_3").adapt(prompt)
    assert package.camera_control is not None
    assert package.camera_control.shot_type == "close_up"
    assert package.camera is None


def test_adapter_degrades_camera_to_text_when_unsupported():
    prompt = _prompt("close-up of a woman, slow pan, rainy street")
    prompt.camera = build_camera_control("slow pan", "close_up")

    package = get_adapter("sora_2").adapt(prompt)
    assert package.camera_control is None
    assert package.camera is not None
    assert "close_up" in package.camera


# ---------------------------------------------------------------------------
# 路由特征抽取
# ---------------------------------------------------------------------------
def test_extract_route_features_is_deterministic():
    prompt = _prompt(
        "A poster with subtitle text, a warrior runs and jumps", style="anime"
    )
    features = extract_route_features(prompt)

    assert features.has_critical_text is True
    assert features.motion_complexity == MotionComplexity.HIGH
    assert features.style_bias == AestheticBias.ANIME
    assert features.character_consistency_need == ConsistencyNeed.LOW


def test_extract_route_features_marks_character_consistency():
    features = extract_route_features(
        _prompt("a woman walks home", main_character="小雨")
    )
    assert features.character_consistency_need == ConsistencyNeed.MEDIUM


# ---------------------------------------------------------------------------
# 规则匹配与兜底
# ---------------------------------------------------------------------------
def test_routing_config_is_loaded_and_models_registered():
    assert settings.routing.enabled is True
    assert len(settings.routing.rules) >= 5
    assert all(
        get_capability(rule.model) is not None for rule in settings.routing.rules
    )


def test_critical_text_rule_has_highest_priority():
    instructions = _instructions(_prompt("woman holding a sign, slow pan"))
    packages = adapt_instructions(instructions, "runway_gen4")

    plan = build_route_plan(packages, instructions)

    assert plan.decisions[0].target_model == "kling_3"
    assert plan.decisions[0].reason == "critical_text"
    assert plan.decisions[0].mode == RouteMode.IMAGE_TO_VIDEO
    # 适配包按最终目标模型重建，避免提示词与模型不一致
    assert packages[0].target_model == "kling_3"


def test_routing_disabled_keeps_source_model(monkeypatch):
    monkeypatch.setattr(settings.routing, "enabled", False)
    instructions = _instructions(_prompt("woman holding a sign, slow pan"))
    packages = adapt_instructions(instructions, "runway_gen4")

    plan = build_route_plan(packages, instructions)

    assert plan.decisions[0].target_model == "runway_gen4"
    assert plan.decisions[0].reason == "fallback_current_model"


def test_duration_exceeding_capability_falls_back():
    # cinematic 长镜头命中 runway_gen4（上限 10s），20s 片段应兜底到可覆盖时长的模型
    instructions = _instructions(
        _prompt("wide cinematic landscape", duration=20.0, style="cinematic")
    )
    packages = adapt_instructions(instructions, "runway_gen4")

    plan = build_route_plan(packages, instructions)

    assert plan.decisions[0].target_model == "sora_2"
    assert "duration_fallback" in plan.decisions[0].reason
    assert packages[0].duration == 20.0
    assert packages[0].target_model == "sora_2"


# ---------------------------------------------------------------------------
# ROUTE_MODEL 节点
# ---------------------------------------------------------------------------
def test_route_model_node_rebuilds_route_plan():
    nodes = object.__new__(WorkflowNodes)
    nodes.storage = _FakeStorage()

    state = WorkflowState.from_raw_script(
        "测试剧本", task_id="task_001", script_id="script_001"
    )
    instructions = _instructions(_prompt("woman holding a sign, slow pan"))
    instructions.route_plan = {"stale": True}
    state.domain.instructions = instructions

    nodes.route_model_node(state)

    plan = state.domain.instructions.route_plan
    assert plan is not None
    assert plan["decisions"][0]["target_model"] == "kling_3"
    assert "stale" not in plan
    assert state.execution.current_node == PipelineNode.ROUTE_MODEL
    assert nodes.storage.saved[0][0] == "prompt_converter_result.json"


def test_route_model_node_does_not_block_on_failure():
    nodes = object.__new__(WorkflowNodes)
    nodes.storage = _FakeStorage()

    state = WorkflowState.from_raw_script(
        "测试剧本", task_id="task_002", script_id="script_002"
    )

    nodes.route_model_node(state)

    assert state.domain.instructions is None
    assert state.execution.current_node == PipelineNode.ROUTE_MODEL


def test_contract_schema_version_is_0_4_4():
    assert CONTRACT_SCHEMA_VERSION == "0.4.4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
