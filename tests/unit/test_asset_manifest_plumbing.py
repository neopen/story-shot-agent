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
