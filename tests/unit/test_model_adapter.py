"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_model_adapter.py
@Description: 目标模型适配层（M0.4.0）单元测试
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/01
"""

import json

import pytest

from penshot.neopen.agent.model_adapter import (
    AdaptedPromptPackage,
    AestheticBias,
    ModelCapability,
    RouteDecision,
    RoutePlan,
    adapt_instructions,
    all_capabilities,
    get_adapter,
    get_capability,
    list_model_names,
    register_model,
    resolve_model_name,
)
from penshot.neopen.agent.model_adapter.model_adapter import RunwayGen4Adapter
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)


def _make_prompt(fragment_id: str = "frag_001") -> AIVideoPrompt:
    """构造一个通用片段提示词样本（含可被相机探测的关键词）"""
    return AIVideoPrompt(
        fragment_id=fragment_id,
        prompt="close-up of a woman, slow pan, rainy neon street at night",
        negative_prompt="blurry, distorted, low quality",
        duration=12.0,
        model="runway_gen2",
        style="cinematic realism",
    )


def _make_instructions() -> AIVideoInstructions:
    """构造一份含两个片段的通用指令集"""
    return AIVideoInstructions(
        fragments=[
            _make_prompt("frag_001"),
            _make_prompt("frag_002"),
        ]
    )


# ---------------------------------------------------------------------------
# capability_registry 相关
# ---------------------------------------------------------------------------
def test_registry_covers_at_least_four_models():
    assert len(list_model_names()) >= 4


def test_capability_fields_are_valid():
    for cap in all_capabilities().values():
        assert cap.model_name
        assert cap.max_duration > 0
        assert 0.0 <= cap.text_rendering_score <= 1.0
        assert 0.0 <= cap.character_consistency <= 1.0
        assert cap.aesthetic_bias in {
            AestheticBias.CINEMATIC,
            AestheticBias.ANIME,
            AestheticBias.REALISTIC,
        }


def test_get_capability_unknown_returns_none():
    assert get_capability("not_a_real_model") is None


def test_register_model_overwrites():
    cap = ModelCapability(
        model_name="tmp_model",
        max_duration=3.0,
        text_rendering_score=0.1,
        character_consistency=0.2,
    )
    register_model(cap)
    assert get_capability("tmp_model") is cap


# ---------------------------------------------------------------------------
# 模型适配器结构差异相关
# ---------------------------------------------------------------------------
def test_adapter_outputs_structurally_different():
    prompt = _make_prompt()
    runway = get_adapter("runway_gen4").adapt(prompt)
    kling = get_adapter("kling_3").adapt(prompt)
    pika = get_adapter("pika_2").adapt(prompt)

    # 正向提示词、负向提示词、相机表述、模型参数各维度均应有可观测差异
    assert runway.prompt != kling.prompt
    assert runway.negative_prompt != kling.negative_prompt
    assert runway.camera != kling.camera
    assert runway.model_params != kling.model_params
    assert pika.camera is not None and pika.prompt.endswith(
        "anime style, smooth motion, vibrant colors"
    )


def test_sora_adapter_does_not_use_negative_prompt():
    package = get_adapter("sora_2").adapt(_make_prompt())
    assert package.negative_prompt == ""
    assert package.model_params.get("negative_prompt") is False


def test_duration_is_clamped_to_model_limit():
    # pika_2 max_duration=4.0，样本时长 12.0 应被收敛
    package = get_adapter("pika_2").adapt(_make_prompt())
    assert package.duration == 4.0

    # sora_2 max_duration=60.0，12.0 不受收敛影响
    package = get_adapter("sora_2").adapt(_make_prompt())
    assert package.duration == 12.0


def test_target_model_is_recorded():
    package = get_adapter("kling_3").adapt(_make_prompt())
    assert package.target_model == "kling_3"
    assert package.fragment_id == "frag_001"


# ---------------------------------------------------------------------------
# 工厂与别名相关
# ---------------------------------------------------------------------------
def test_resolve_model_name_aliases():
    assert resolve_model_name("runway_gen2") == "runway_gen4"
    assert resolve_model_name("Runway_Gen4") == "runway_gen4"
    assert resolve_model_name("kling") == "kling_3"
    assert resolve_model_name("unknown_model") == "unknown_model"
    assert resolve_model_name(None) == "runway_gen4"


def test_get_adapter_unknown_falls_back_to_default():
    adapter = get_adapter("does_not_exist")
    assert isinstance(adapter, RunwayGen4Adapter)
    assert adapter.model_name == "runway_gen4"


def test_adapt_instructions_produces_packages():
    packages = adapt_instructions(_make_instructions(), "kling_3")
    assert len(packages) == 2
    assert all(p.target_model == "kling_3" for p in packages)
    assert all(isinstance(p, AdaptedPromptPackage) for p in packages)


def test_adapt_instructions_uses_metadata_model_when_not_given():
    # 指令集 metadata.video_model 默认 runway_gen2 -> 归一化为 runway_gen4
    packages = adapt_instructions(_make_instructions())
    assert packages[0].target_model == "runway_gen4"


# ---------------------------------------------------------------------------
# RoutePlan 可序列化相关
# ---------------------------------------------------------------------------
def test_route_plan_is_json_serializable():
    capability = get_capability("runway_gen4")
    plan = RoutePlan(
        source_model="runway_gen2",
        decisions=[
            RouteDecision(
                fragment_id="frag_001", target_model="runway_gen4", reason="default"
            )
        ],
        adapted_packages=[],
    )
    data = json.loads(json.dumps(plan.to_dict()))
    assert data["source_model"] == "runway_gen2"
    assert data["decisions"][0]["target_model"] == "runway_gen4"
    assert capability is not None


def test_route_plan_model_dump_json_with_capability():
    # 覆盖内联接入路径：plan.model_dump(mode="json") 需把枚举降为字符串
    plan = RoutePlan(
        source_model="runway_gen2",
        decisions=[
            RouteDecision(
                fragment_id="frag_001",
                target_model="runway_gen4",
                reason="m0.4.0_inline",
                capability=get_capability("runway_gen4"),
            )
        ],
        adapted_packages=[get_adapter("runway_gen4").adapt(_make_prompt())],
    )
    payload = json.loads(json.dumps(plan.model_dump(mode="json")))
    assert payload["decisions"][0]["capability"]["aesthetic_bias"] == "cinematic"
    assert payload["adapted_packages"][0]["target_model"] == "runway_gen4"


def test_instructions_route_plan_survives_model_dump():
    # generate_output_node 用 instructions.model_dump() 出最终结果，route_plan 须随之落盘
    instructions = _make_instructions()
    plan = RoutePlan(
        source_model="runway_gen2",
        decisions=[],
        adapted_packages=adapt_instructions(instructions, "runway_gen4"),
    )
    instructions.route_plan = plan.model_dump(mode="json")
    dumped = json.loads(json.dumps(instructions.model_dump(mode="json")))
    assert dumped["route_plan"]["adapted_packages"][0]["target_model"] == "runway_gen4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
