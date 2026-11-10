"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_asset_manifest_plumbing.py
@Description: 验证 asset_manifest 在任务层、处理器与 REST/SDK 入参中的透传
@Author: NeoPen
@Time: 2026/11/05
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from penshot.api.rest_api import (
    BatchProcessRequest,
    ProcessRequest,
    SyncProcessRequest,
)
from penshot.neopen.task.task_processor import AsyncTaskProcessor


def _manifest() -> dict:
    """构造一个最小的下游资产回填清单"""
    return {
        "schema_version": "0.4.3",
        "task_id": "t1",
        "bindings": [
            {
                "asset_id": "ds_char_001",
                "asset_ref": "/cdn/ds_char_001.png",
                "source": "downstream",
            }
        ],
        "asset_id_map": {"char_001": "ds_char_001"},
    }


def test_process_requests_accept_asset_manifest():
    """REST 单任务请求应接受 asset_manifest"""
    manifest = _manifest()

    async_req = ProcessRequest(script="剧本", asset_manifest=manifest)
    sync_req = SyncProcessRequest(script="剧本", asset_manifest=manifest)

    assert async_req.asset_manifest == manifest
    assert sync_req.asset_manifest == manifest


def test_batch_request_requires_matching_manifest_length():
    """批量请求的回填清单数量必须与剧本数量一致"""
    req = BatchProcessRequest(
        scripts=["剧本1", "剧本2"],
        asset_manifests=[_manifest(), None],
    )
    assert len(req.asset_manifests) == 2

    with pytest.raises(ValidationError):
        BatchProcessRequest(
            scripts=["剧本1", "剧本2"],
            asset_manifests=[_manifest()],
        )


@pytest.mark.asyncio
async def test_processor_passes_asset_manifest_to_workflow():
    """任务处理器应从任务记录读取 asset_manifest 并传入工作流"""
    processor = object.__new__(AsyncTaskProcessor)
    manifest = _manifest()

    task_manager = MagicMock()
    task_manager.get_task.return_value = {
        "task_id": "t1",
        "script_id": "s1",
        "script": "剧本",
        "asset_manifest": manifest,
    }

    workflow = MagicMock()
    workflow.run_process = AsyncMock(
        return_value={"success": True, "data": {"instructions": {}}}
    )
    task_manager.get_workflow.return_value = workflow
    processor.task_manager = task_manager

    await processor._process_script_task_internal("t1")

    workflow.run_process.assert_awaited_once()
    _, kwargs = workflow.run_process.call_args
    assert kwargs["asset_manifest"] == manifest


def _plan_sync_state():
    """构造路由后回填所需的最小状态（资产计划 + 片段/镜头/场景）"""
    from types import SimpleNamespace

    from penshot.neopen.agent.asset_generator.asset_models import (
        AssetPlanDocument,
        AssetSpec,
        AssetType,
    )
    from penshot.neopen.agent.continuity_guardian.consistency_contract import (
        AssetContract,
        GlobalConsistencyContract,
        SceneContract,
    )
    from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
        AIVideoInstructions,
        AIVideoPrompt,
    )
    from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState

    state = WorkflowState.from_raw_script("剧本", task_id="t1", script_id="s1")
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(scene_num=1, location="咖啡店外", time_of_day="dusk")
    )
    contract.register_asset(
        AssetContract(
            asset_id="char_001",
            asset_type="character_sheet",
            owner_name="林小雨",
            image_prompt="character reference sheet of 林小雨",
        )
    )
    state.domain.contract = contract
    state.domain.instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001",
                prompt="woman waits by the coffee shop",
                duration=3.0,
                main_character="林小雨",
            )
        ]
    )
    state.domain.fragment_sequence = SimpleNamespace(
        fragments=[SimpleNamespace(id="frag_001", shot_id="shot_001")]
    )
    state.domain.shot_sequence = SimpleNamespace(
        shots=[
            SimpleNamespace(
                id="shot_001", scene_id="scene_001", main_character="林小雨"
            )
        ]
    )
    state.domain.parsed_script = SimpleNamespace(
        scenes=[SimpleNamespace(id="scene_001", location="咖啡店外")],
        global_metadata=SimpleNamespace(key_props=[]),
    )
    state.domain.asset_plan = AssetPlanDocument(
        task_id="t1",
        script_id="s1",
        assets=[
            AssetSpec(
                asset_id="char_001",
                asset_type=AssetType.CHARACTER_SHEET,
                owner_name="林小雨",
                image_prompt="character reference sheet of 林小雨",
            ),
            AssetSpec(
                asset_id="scene_001",
                asset_type=AssetType.SCENE,
                owner_name="咖啡店外",
                image_prompt="establishing shot still of 咖啡店外",
            ),
        ],
    ).to_dict()
    return state


class _RecordingStorage:
    """记录落盘调用结果的存储桩"""

    def __init__(self) -> None:
        self.saved = []

    def save_obj_result(self, script_id, task_id, obj, filename):
        self.saved.append((filename, obj))


def test_route_model_node_syncs_backfilled_asset_plan():
    """AC-017/FR-014：两份资产计划的 usage 一致且均来自回填结果"""
    from penshot.neopen.agent.asset_generator.asset_models import AssetPlanDocument
    from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes

    nodes = object.__new__(WorkflowNodes)
    nodes.storage = _RecordingStorage()
    state = _plan_sync_state()

    nodes.route_model_node(state)

    saved = dict(nodes.storage.saved)
    assert "asset_plan.json" in saved
    assert "prompt_converter_result.json" in saved

    plan_doc = saved["asset_plan.json"]
    assert isinstance(plan_doc, AssetPlanDocument)
    plan_usage = {spec.asset_id: spec.usage.fragments for spec in plan_doc.assets}
    instruction_usage = {
        item["asset_id"]: item["usage"]["fragments"]
        for item in state.domain.instructions.asset_plan["assets"]
    }
    assert plan_usage == instruction_usage
    assert plan_usage["char_001"] == ["frag_001"]
    assert plan_usage["scene_001"] == ["frag_001"]
