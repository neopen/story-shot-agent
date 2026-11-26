"""提示词阶段模型支持检查：路由产出的已注册模型不得误报或崩溃。"""

from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.shot_config import ShotConfig


def _agent() -> PromptConverterAgent:
    return PromptConverterAgent(
        llm=None, config=ShotConfig(enable_llm=False, enable_enhance=False)
    )


def _prompt(model: str) -> AIVideoPrompt:
    return AIVideoPrompt(
        fragment_id="frag_001",
        prompt="wide shot of a young woman waiting by the cafe window in the rain",
        duration=3.0,
        model=model,
    )


def test_routed_registered_model_does_not_crash_or_flag():
    """kling_3 等路由模型已注册，检测不得访问不存在的配置字段或误报"""
    instructions = AIVideoInstructions(fragments=[_prompt("kling_3")])

    issues = _agent().detect_issues(instructions, FragmentSequence())

    assert [i for i in issues if i.issue_code == "model_unsupported"] == []


def test_unknown_model_reported_with_registered_suggestion():
    """真正未注册的模型仍要告警，建议来自能力注册表"""
    instructions = AIVideoInstructions(fragments=[_prompt("totally_unknown_model")])

    issues = _agent().detect_issues(instructions, FragmentSequence())
    violations = [i for i in issues if i.issue_code == "model_unsupported"]

    assert len(violations) == 1
    assert "kling_3" in violations[0].suggestion
