"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_workflow_orchestrator.py
@Description: 工作流编排器单元测试
@Author: NeoPen
@Time: 2026/4/29
"""

from unittest.mock import MagicMock

import pytest

from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_orchestrator import WorkflowOrchestrator


class TestWorkflowOrchestrator:
    """工作流编排器测试"""

    @pytest.fixture
    def orchestrator(self):
        return WorkflowOrchestrator()

    def test_add_node(self, orchestrator):
        """测试添加节点"""
        mock_node = MagicMock(return_value={})
        orchestrator.add_node("test_node", mock_node)

        assert orchestrator.has_node("test_node")
        assert orchestrator.get_node("test_node") == mock_node

    def test_remove_node(self, orchestrator):
        """测试移除节点"""
        mock_node = MagicMock(return_value={})
        orchestrator.add_node("test_node", mock_node)

        result = orchestrator.remove_node("test_node")

        assert result is True
        assert not orchestrator.has_node("test_node")

    def test_remove_nonexistent_node(self, orchestrator):
        """测试移除不存在的节点"""
        result = orchestrator.remove_node("nonexistent")

        assert result is False

    def test_add_edge(self, orchestrator):
        """测试添加边"""
        orchestrator.add_node("node1", MagicMock())
        orchestrator.add_node("node2", MagicMock())
        orchestrator.add_edge("node1", "node2")

        assert ("node1", "node2") in orchestrator.edges

    def test_create_default_decision_mapping(self, orchestrator):
        """测试创建默认决策映射"""
        mapping = orchestrator.create_default_decision_mapping()

        assert PipelineState.SUCCESS in mapping
        assert PipelineState.FAILED in mapping
        assert PipelineState.ABORT in mapping

    def test_set_decision_mapping(self, orchestrator):
        """测试设置决策映射"""
        custom_mapping = {
            PipelineState.SUCCESS: "next_node",
            PipelineState.FAILED: "error_node"
        }
        orchestrator.set_decision_mapping(custom_mapping)

        assert orchestrator.decision_mapping == custom_mapping

    def test_build_workflow(self, orchestrator):
        """测试构建工作流"""
        orchestrator.add_node(PipelineNode.PARSE_SCRIPT.value, MagicMock())
        orchestrator.add_node(PipelineNode.SEGMENT_SHOT.value, MagicMock())
        orchestrator.add_edge(PipelineNode.PARSE_SCRIPT.value, PipelineNode.SEGMENT_SHOT.value)

        orchestrator.build()

        assert orchestrator.graph is not None

    def test_validate_empty_workflow(self, orchestrator):
        """测试验证空工作流"""
        result = orchestrator.validate()

        assert result is False

    def test_validate_workflow_without_start_node(self, orchestrator):
        """测试验证缺少起始节点的工作流"""
        orchestrator.add_node("other_node", MagicMock())
        orchestrator.add_edge("other_node", "END")

        result = orchestrator.validate()

        assert result is False

    def test_validate_workflow_without_end(self, orchestrator):
        """测试验证缺少结束边的工作流"""
        orchestrator.add_node(PipelineNode.PARSE_SCRIPT.value, MagicMock())
        orchestrator.add_node(PipelineNode.SEGMENT_SHOT.value, MagicMock())
        orchestrator.add_edge(PipelineNode.PARSE_SCRIPT.value, PipelineNode.SEGMENT_SHOT.value)

        result = orchestrator.validate()

        assert result is False

    def test_validate_valid_workflow(self, orchestrator):
        """测试验证有效的工作流"""
        from langgraph.graph import END
        orchestrator.add_node(PipelineNode.PARSE_SCRIPT.value, MagicMock())
        orchestrator.add_node(PipelineNode.SEGMENT_SHOT.value, MagicMock())
        orchestrator.add_edge(PipelineNode.PARSE_SCRIPT.value, PipelineNode.SEGMENT_SHOT.value)
        orchestrator.add_edge(PipelineNode.SEGMENT_SHOT.value, END)

        result = orchestrator.validate()

        assert result is True

    def test_clear(self, orchestrator):
        """测试清空编排器"""
        orchestrator.add_node("test_node", MagicMock())
        orchestrator.add_edge("test_node", "END")
        orchestrator.build()

        orchestrator.clear()

        assert len(orchestrator.nodes) == 0
        assert len(orchestrator.edges) == 0
        assert orchestrator.graph is None

    def test_get_graph_info(self, orchestrator):
        """测试获取图信息"""
        orchestrator.add_node("node1", MagicMock())
        orchestrator.add_node("node2", MagicMock())
        orchestrator.add_edge("node1", "node2")

        info = orchestrator.get_graph_info()

        assert "nodes" in info
        assert "edges" in info
        assert "conditional_edges_count" in info
        assert "is_built" in info
        assert len(info["nodes"]) == 2
        assert len(info["edges"]) == 1


class TestWorkflowOrchestratorIntegration:
    """工作流编排器集成测试"""

    @pytest.fixture
    def orchestrator(self):
        return WorkflowOrchestrator()

    def test_simple_workflow_execution(self, orchestrator):
        """测试简单工作流执行"""
        from langgraph.graph import END
        from typing import Dict, Any

        # 定义节点函数
        def start_node(state: Dict[str, Any]) -> Dict[str, Any]:
            state["step"] = "start"
            return state

        def middle_node(state: Dict[str, Any]) -> Dict[str, Any]:
            state["step"] = "middle"
            return state

        def end_node(state: Dict[str, Any]) -> Dict[str, Any]:
            state["step"] = "end"
            return state

        # 构建工作流，使用字典作为状态模式
        orchestrator.add_node("start", start_node)
        orchestrator.add_node("middle", middle_node)
        orchestrator.add_node("end", end_node)
        orchestrator.add_edge("start", "middle")
        orchestrator.add_edge("middle", "end")
        orchestrator.add_edge("end", END)
        orchestrator.build(state_schema=Dict[str, Any])

        # 执行工作流
        input_state = {"initial": "data"}
        result = orchestrator.run(input_state)

        assert result["step"] == "end"
        assert result["initial"] == "data"

    def test_conditional_edge_workflow(self, orchestrator):
        """测试条件边工作流"""
        from langgraph.graph import END
        from typing import Dict, Any

        # 定义节点函数
        def check_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return state

        def success_node(state: Dict[str, Any]) -> Dict[str, Any]:
            state["result"] = "success"
            return state

        def failure_node(state: Dict[str, Any]) -> Dict[str, Any]:
            state["result"] = "failure"
            return state

        # 定义条件函数
        def check_condition(state: Dict[str, Any]) -> bool:
            return state.get("value", 0) > 5

        # 构建工作流，使用字典作为状态模式
        orchestrator.add_node("check", check_node)
        orchestrator.add_node("success", success_node)
        orchestrator.add_node("failure", failure_node)
        orchestrator.add_conditional_edge(
            "check",
            check_condition,
            {True: "success", False: "failure"}
        )
        orchestrator.add_edge("success", END)
        orchestrator.add_edge("failure", END)
        orchestrator.build(state_schema=Dict[str, Any])

        # 测试成功路径
        result1 = orchestrator.run({"value": 10})
        assert result1["result"] == "success"

        # 测试失败路径
        result2 = orchestrator.run({"value": 3})
        assert result2["result"] == "failure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
