"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_p2_regressions.py
@Description: P2 优化项回归测试（统计修复、处理统计结构、并发任务更新）
@Author: neopen
"""
import threading
import uuid

from penshot.neopen.agent.workflow.workflow_orchestrator import WorkflowOrchestrator
from penshot.neopen.agent.workflow.workflow_output_fixer import WorkflowOutputFixer
from penshot.neopen.agent.workflow.workflow_pipeline import MultiAgentPipeline
from penshot.neopen.task.task_repository import TaskRepository


def test_pipeline_fixes_split_stats_from_dict_fragments():
    """字典形态的片段也应能正确统计被分割的镜头数"""
    data = {
        "fragment_sequence": {
            "fragments": [
                {"metadata": {"is_split": True, "original_shot": 1}},
                {"metadata": {"is_split": False, "original_shot": 2}},
                {"metadata": {"is_split": True, "original_shot": 1}},
            ],
            "source_info": {"shot_count": 4},
            "stats": {"fragments_split": 4},
        }
    }

    result = MultiAgentPipeline._validate_and_fix_fragment_stats(object(), data)
    stats = result["fragment_sequence"]["stats"]

    assert stats["fragments_split"] == 1
    assert stats["split_ratio"] == 0.25


def test_pipeline_keeps_stats_when_no_split_metadata():
    """片段没有 is_split 标记时不应把已有统计清零"""
    data = {
        "fragment_sequence": {
            "fragments": [{"metadata": {}}],
            "source_info": {"shot_count": 3},
            "stats": {"fragments_split": 2},
        }
    }

    result = MultiAgentPipeline._validate_and_fix_fragment_stats(object(), data)

    assert result["fragment_sequence"]["stats"]["fragments_split"] == 2


def test_fixer_processing_stats_is_dict_with_fragment_stats():
    """输出修复器的处理统计应为 dict，并兼容字典形态的片段数据"""
    fixer = WorkflowOutputFixer(is_debug=True)

    stats = fixer._build_processing_stats(
        {
            "domain": {"fragment_sequence": {"fragments": [1, 2]}},
            "execution": {"current_node": "generate_output", "global_current_loops": 2},
            "errors": {"error_messages": ["e1"]},
        },
        {"fragments": [1, 2], "stats": {"avg_duration": 3.5}},
    )

    assert isinstance(stats, dict)
    assert isinstance(stats["completed_stages"], list)
    assert stats["fragment_stats"]["total_fragments"] == 2
    assert stats["fragment_stats"]["avg_duration"] == 3.5
    assert stats["global_loops"] == 2
    assert stats["error_count"] == 1


def test_orchestrator_reads_nested_domain_state():
    """编排器统计修复应兼容嵌套 domain 子状态"""
    orchestrator = WorkflowOrchestrator()
    state = {
        "domain": {
            "fragment_sequence": {
                "fragments": [{"metadata": {"is_split": True, "original_shot": 1}}],
                "source_info": {"shot_count": 2},
                "stats": {"fragments_split": 9},
            }
        }
    }

    orchestrator._extract_and_fix_stats(state)

    stats = state["domain"]["fragment_sequence"]["stats"]
    assert stats["fragments_split"] == 1
    assert stats["split_ratio"] == 0.5


def test_repository_update_task_is_thread_safe():
    """并发更新同一任务记录时不应丢失写入"""
    repository = TaskRepository()
    task_id = "TSKCHECK" + uuid.uuid4().hex[:8]
    repository.create_task(task_id, {"count": 0})

    def increase():
        for _ in range(25):
            repository.update_task(task_id, lambda rec: rec.__setitem__("count", rec.get("count", 0) + 1))

    try:
        threads = [threading.Thread(target=increase) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert repository.read_task(task_id)["count"] == 100
    finally:
        repository.delete_task(task_id)
