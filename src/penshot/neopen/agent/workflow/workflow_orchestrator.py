"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: workflow_orchestrator.py
@Description: 工作流编排器 - 负责流程结构定义和节点调度
@Author: NeoPen
@Time: 2026/4/29
"""

from __future__ import annotations

from typing import Dict, Any, Callable, Optional, List
from langgraph.graph import StateGraph, END

from penshot.logger import info, error, warning, debug
from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


class WorkflowOrchestrator:
    """工作流编排器 - 负责流程结构定义和节点调度"""

    def __init__(self):
        """初始化工作流编排器"""
        self.graph: Optional[StateGraph] = None
        # 编译缓存
        self._compiled_graph: Optional[Any] = None
        self.nodes: Dict[str, Callable] = {}
        self.edges: List[tuple] = []
        self.conditional_edges: List[tuple] = []
        self.decision_mapping: Dict[PipelineState, str] = {}

    def set_decision_mapping(self, mapping: Dict[PipelineState, str]) -> None:
        """
        设置决策状态到节点的映射

        Args:
            mapping: 决策状态到节点名称的映射
        """
        self.decision_mapping = mapping

    def add_node(self, name: str, node: Callable) -> None:
        """
        添加节点

        Args:
            name: 节点名称
            node: 节点执行函数
        """
        self.nodes[name] = node
        debug(f"注册节点: {name}")

    def add_edge(self, source: str, target: str) -> None:
        """
        添加边（无条件跳转）

        Args:
            source: 源节点名称
            target: 目标节点名称
        """
        self.edges.append((source, target))
        debug(f"添加边: {source} -> {target}")

    def add_conditional_edge(self, source: str, condition: Callable, 
                              mapping: Dict[Any, str]) -> None:
        """
        添加条件边

        Args:
            source: 源节点名称
            condition: 条件判断函数
            mapping: 条件结果到目标节点的映射
        """
        self.conditional_edges.append((source, condition, mapping))
        debug(f"添加条件边: {source} -> [条件判断] -> {list(mapping.values())}")

    def build(self, state_schema: type = WorkflowState) -> None:
        """
        构建工作流图

        Args:
            state_schema: 状态类型定义
        """
        self.graph = StateGraph(state_schema)

        # 添加所有节点
        for name, node_func in self.nodes.items():
            self.graph.add_node(name, node_func)

        # 添加无条件边
        for source, target in self.edges:
            self.graph.add_edge(source, target)

        # 添加条件边
        for source, condition, mapping in self.conditional_edges:
            self.graph.add_conditional_edges(source, condition, mapping)

        # 设置入口点：默认使用 PARSE_SCRIPT 作为起始节点
        if PipelineNode.PARSE_SCRIPT.value in self.nodes:
            self.graph.set_entry_point(PipelineNode.PARSE_SCRIPT.value)
            debug(f"设置入口点: {PipelineNode.PARSE_SCRIPT.value}")
        elif self.nodes:
            # 如果没有 PARSE_SCRIPT 节点，使用第一个添加的节点作为入口点
            first_node = next(iter(self.nodes.keys()))
            self.graph.set_entry_point(first_node)
            debug(f"设置入口点: {first_node} (默认第一个节点)")
        else:
            warning("没有找到任何节点，无法设置入口点")

        self._compiled_graph = self.graph.compile()
        info(f"工作流图构建完成，节点数: {len(self.nodes)}，边数: {len(self.edges) + len(self.conditional_edges)}")

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步运行工作流

        Args:
            input_data: 输入数据

        Returns:
            输出结果
        """
        if self._compiled_graph is None:
            raise RuntimeError("工作流图尚未构建，请先调用 build() 方法")

        try:
            result = self._compiled_graph.invoke(input_data)
            # 提取统计信息
            if isinstance(result, dict):
                self._extract_and_fix_stats(result)

            info(f"工作流执行完成，状态: {result.get('status', 'unknown')}")
            return result
        except Exception as e:
            error(f"工作流执行失败: {e}")
            raise

    def _extract_and_fix_stats(self, state: Dict[str, Any]):
        """提取并修复统计信息"""
        try:
            fragment_sequence = state.get("fragment_sequence")
            if fragment_sequence and isinstance(fragment_sequence, dict):
                shot_count = fragment_sequence.get("source_info", {}).get("shot_count", 0)
                fragments = fragment_sequence.get("fragments", [])
                stats = fragment_sequence.get("stats", {})

                # 计算实际分割数
                split_shots = set()
                for f in fragments:
                    if isinstance(f, dict):
                        metadata = f.get("metadata", {})
                        if metadata.get("is_split", False):
                            original_shot = metadata.get("original_shot")
                            if original_shot:
                                split_shots.add(original_shot)

                actual_split = len(split_shots)

                # 修复错误的统计
                if stats.get("fragments_split", 0) != actual_split and actual_split > 0:
                    stats["fragments_split"] = actual_split
                    stats["split_ratio"] = round(actual_split / shot_count, 2) if shot_count > 0 else 0
                    fragment_sequence["stats"] = stats
                    debug(f"修复统计: fragments_split={actual_split}, split_ratio={stats['split_ratio']}")

        except Exception as e:
            debug(f"提取统计信息时出错: {e}")


    async def arun(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步运行工作流

        Args:
            input_data: 输入数据

        Returns:
            输出结果
        """
        if self._compiled_graph is None:
            raise RuntimeError("工作流图尚未构建，请先调用 build() 方法")

        try:
            result = await self._compiled_graph.ainvoke(input_data)
            info(f"异步工作流执行完成，状态: {result.get('status', 'unknown')}")
            return result
        except Exception as e:
            error(f"异步工作流执行失败: {e}")
            raise

    def get_node(self, name: str) -> Optional[Callable]:
        """
        获取节点函数

        Args:
            name: 节点名称

        Returns:
            节点函数，如果不存在返回 None
        """
        return self.nodes.get(name)

    def has_node(self, name: str) -> bool:
        """
        检查节点是否存在

        Args:
            name: 节点名称

        Returns:
            是否存在
        """
        return name in self.nodes

    def remove_node(self, name: str) -> bool:
        """
        移除节点

        Args:
            name: 节点名称

        Returns:
            是否移除成功
        """
        if name in self.nodes:
            del self.nodes[name]
            # 移除相关的边
            self.edges = [(s, t) for s, t in self.edges if s != name and t != name]
            self.conditional_edges = [(s, c, m) for s, c, m in self.conditional_edges if s != name]
            info(f"移除节点: {name}")
            return True
        return False

    def clear(self) -> None:
        """清空所有节点和边"""
        self.nodes.clear()
        self.edges.clear()
        self.conditional_edges.clear()
        self.graph = None
        info("工作流编排器已清空")

    def get_graph_info(self) -> Dict[str, Any]:
        """
        获取工作流图信息

        Returns:
            图信息字典
        """
        return {
            "nodes": list(self.nodes.keys()),
            "edges": self.edges,
            "conditional_edges_count": len(self.conditional_edges),
            "is_built": self.graph is not None
        }

    @staticmethod
    def create_default_decision_mapping() -> Dict[PipelineState, str]:
        """
        创建默认的决策状态到节点的映射

        Returns:
            映射字典
        """
        return {
            PipelineState.SUCCESS: PipelineNode.SEGMENT_SHOT.value,
            PipelineState.VALID: PipelineNode.SEGMENT_SHOT.value,
            PipelineState.NEEDS_RETRY: PipelineNode.PARSE_SCRIPT.value,
            PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT.value,
            PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION.value,
            PipelineState.FAILED: END,
            PipelineState.ABORT: END,
        }

    def validate(self) -> bool:
        """
        验证工作流图的完整性

        Returns:
            是否有效
        """
        if not self.nodes:
            warning("工作流图验证失败: 没有注册任何节点")
            return False

        # 检查是否有起始节点
        if PipelineNode.PARSE_SCRIPT.value not in self.nodes:
            warning(f"工作流图验证失败: 缺少起始节点 {PipelineNode.PARSE_SCRIPT.value}")
            return False

        # 检查是否有结束节点（通过 END 标记）
        has_end = False
        for source, target in self.edges:
            if target == END:
                has_end = True
                break
        for source, _, mapping in self.conditional_edges:
            if END in mapping.values():
                has_end = True
                break

        if not has_end:
            warning("工作流图验证失败: 没有指向 END 的边")
            return False

        debug("工作流图验证通过")
        return True