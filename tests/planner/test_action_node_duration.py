"""
@FileName: test_action_node_duration.py
@Description: 动作节点识别与确定性时长公式（0.4.6 T-001/T-002）
@Author: neopen
@Time: 2026/11/13
"""

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.script_parser.script_parser_models import (
    BaseElement,
    ParsedScript,
    SceneInfo,
)
from penshot.neopen.agent.shot_segmenter.estimator.action_nodes import (
    compute_duration,
    compute_duration_from_text,
    count_action_nodes,
    count_dialogue_chars,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo

FRAG_003_DESCRIPTION = (
    "中景镜头：林晚低头看着手中的皱巴巴的白色纸条，上面写着一个地址。"
    "随后她缓缓抬头望向漆黑的隧道深处，眼神中流露出一丝犹豫和期待交织的情绪。"
)

EIGHT_NODE_TEXT = "林晚低头，抬头，转身，迈步，攥紧纸条，叹气，凝视窗外，微笑。"


def _shot(description: str, element_ids=None) -> ShotInfo:
    return ShotInfo(
        id="shot_001",
        scene_id="scene_001",
        description=description,
        element_ids=element_ids or [],
    )


def _script_with_element(element: BaseElement) -> ParsedScript:
    scene = SceneInfo(id="scene_001", location="城市地铁站台", elements=[element])
    return ParsedScript(scenes=[scene])


def test_count_action_nodes_frag_003() -> None:
    """样本 frag_003 的四个动作节点：低头、看着、抬头、望向"""
    assert count_action_nodes(FRAG_003_DESCRIPTION) == 4


def test_count_action_nodes_eight_nodes() -> None:
    """构造文本可识别出 8 个动作节点"""
    assert count_action_nodes(EIGHT_NODE_TEXT) == 8


def test_count_action_nodes_ignores_pure_environment() -> None:
    """纯环境描述不产生动作节点"""
    assert (
        count_action_nodes("深夜空旷的地铁站台笼罩在冷白色灯光中，远处隧道口漆黑一片。")
        == 0
    )


def test_count_action_nodes_empty_text() -> None:
    """空文本返回 0"""
    assert count_action_nodes("") == 0


def test_count_dialogue_chars_extracts_quoted_text() -> None:
    """对话元素只统计引号内台词，不把叙述动作计入"""
    element = BaseElement(
        id="elem_dialogue",
        type=ElementType.DIALOGUE,
        sequence=1,
        content="林晚没回头，轻声说：“我等的人，可能不来了。”",
    )
    script = _script_with_element(element)
    shot = _shot("特写镜头：林晚轻声说话。", element_ids=["elem_dialogue"])

    assert count_dialogue_chars(shot, script) == 9


def test_count_dialogue_chars_ignores_action_element() -> None:
    """动作元素不计入台词字数"""
    element = BaseElement(
        id="elem_action",
        type=ElementType.ACTION,
        sequence=1,
        content="林晚低头看着纸条。",
    )
    script = _script_with_element(element)
    shot = _shot("中景镜头：林晚看纸条。", element_ids=["elem_action"])

    assert count_dialogue_chars(shot, script) == 0


def test_count_dialogue_chars_without_script() -> None:
    """缺少剧本时返回 0，不抛异常"""
    shot = _shot("中景镜头：林晚看纸条。", element_ids=["elem_001"])

    assert count_dialogue_chars(shot, None) == 0


def test_compute_duration_static_floor() -> None:
    """静态无动作镜头取 2.5 秒下限"""
    assert compute_duration_from_text("空旷的地铁站台") == 2.5


def test_compute_duration_motion_increment() -> None:
    """含运镜时基础值从 1.5 提升到 2.0"""
    text = "镜头推近，林晚低头，抬头。"

    assert compute_duration_from_text(text) == 3.2
    assert compute_duration_from_text(text, has_motion=True) == 3.2
    assert compute_duration_from_text(text, has_motion=False) == 2.7


def test_compute_duration_frag_003_at_least_3_9() -> None:
    """4 个动作节点的样本片段达到 AC-071 的 3.9 秒"""
    duration = compute_duration_from_text(FRAG_003_DESCRIPTION)

    assert duration == 3.9
    assert duration >= 3.9


def test_compute_duration_clamps_upper_bound() -> None:
    """动作与台词叠加后夹取到 5.0 秒上限"""
    assert compute_duration_from_text(EIGHT_NODE_TEXT, dialogue_chars=40) == 5.0


def test_compute_duration_uses_shot_dialogue() -> None:
    """compute_duration 会从 element_ids 反查台词字数"""
    element = BaseElement(
        id="elem_dialogue",
        type=ElementType.DIALOGUE,
        sequence=1,
        content="林晚：“你好。”",
    )
    script = _script_with_element(element)
    shot = _shot("林晚低头看着纸条。", element_ids=["elem_dialogue"])

    assert count_dialogue_chars(shot, script) == 2
    assert compute_duration(shot, script) == 3.2


def test_compute_duration_is_deterministic() -> None:
    """重复调用结果一致"""
    first = compute_duration_from_text(FRAG_003_DESCRIPTION, dialogue_chars=9)
    second = compute_duration_from_text(FRAG_003_DESCRIPTION, dialogue_chars=9)

    assert first == second
