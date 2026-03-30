"""
@FileName: workflow_output.py
@Description: 工作流输出封装 - 异步保存各类报告，不阻塞主流程
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/30
"""
import asyncio
import threading
from datetime import datetime
from typing import Dict, Optional

from penshot.logger import debug, error, info
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.agent.workflow.workflow_states import WorkflowState
from penshot.neopen.tools.memory.memory_manager import MemoryManager, MemoryType
from penshot.neopen.tools.result_storage_tool import ResultStorage


class WorkflowOutputWriter:
    """
    工作流输出写入器 - 异步保存各类报告，不阻塞主流程

    设计原则：
    1. 所有保存操作异步执行
    2. 不阻塞主工作流
    3. 异常不影响主流程
    """

    def __init__(self, storage: ResultStorage, memory: MemoryManager):
        """
        初始化输出写入器

        Args:
            storage: 结果存储工具
            memory: 记忆管理器
        """
        self.storage = storage
        self.memory = memory
        self._background_loop: Optional[asyncio.AbstractEventLoop] = None
        self._background_thread: Optional[threading.Thread] = None
        self._start_background_loop()

    def _start_background_loop(self):
        """启动后台事件循环"""

        def run_loop():
            self._background_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._background_loop)
            self._background_loop.run_forever()

        self._background_thread = threading.Thread(target=run_loop, daemon=True)
        self._background_thread.start()

        # 等待循环启动
        import time
        timeout = 5
        start = time.time()
        while self._background_loop is None and (time.time() - start) < timeout:
            time.sleep(0.01)

    def _run_async(self, coro):
        """在后台事件循环中运行协程"""
        if self._background_loop is None:
            # 降级：同步执行
            try:
                loop = asyncio.new_event_loop()
                return loop.run_until_complete(coro)
            except Exception as e:
                error(f"同步执行失败: {e}")
                return
        return asyncio.run_coroutine_threadsafe(coro, self._background_loop)

    def save_all_reports(self, state: WorkflowState, task_id: str):
        """
        保存所有报告（异步）

        Args:
            state: 工作流状态
            task_id: 任务ID
        """
        self._run_async(self._save_all_reports_async(state, task_id))

    async def _save_all_reports_async(self, state: WorkflowState, task_id: str):
        """异步保存所有报告"""
        tasks = [
            self._save_execution_summary(state, task_id),
            self._save_stage_statistics(state, task_id),
            self._save_issues_report(state, task_id),
            self._save_repair_history(state, task_id),
            self._save_quality_report(state, task_id),
            self._save_continuity_report(state, task_id),
            self._save_memory_report(state, task_id)
        ]

        # 并发执行所有保存任务
        await asyncio.gather(*tasks, return_exceptions=True)
        debug(f"任务 {task_id} 所有报告已保存")

    async def _save_execution_summary(self, state: WorkflowState, task_id: str):
        """保存执行摘要"""
        try:
            # 计算总时长
            total_duration = 0
            if state.instructions:
                total_duration = sum(f.duration for f in state.instructions.fragments)

            # 获取审查分数
            audit_score = state.audit_report.score if state.audit_report else 0
            audit_status = state.audit_report.status.value if state.audit_report else "unknown"

            summary = {
                "task_id": task_id,
                "status": "completed",
                "created_at": state.final_output.get("created_at") if state.final_output else datetime.now().isoformat(),
                "completed_at": state.final_output.get("completed_at") if state.final_output else datetime.now().isoformat(),
                "statistics": {
                    "total_fragments": len(state.instructions.fragments) if state.instructions else 0,
                    "total_duration": total_duration,
                    "shot_count": len(state.shot_sequence.shots) if state.shot_sequence else 0,
                    "scene_count": len(state.parsed_script.scenes) if state.parsed_script else 0,
                    "character_count": len(state.parsed_script.characters) if state.parsed_script else 0
                },
                "audit_summary": {
                    "status": audit_status,
                    "score": audit_score,
                    "violations_count": len(state.audit_report.violations) if state.audit_report else 0
                }
            }

            await self._save_json_async(task_id, summary, "execution_summary.json")
            debug(f"执行摘要已保存: {task_id}")
        except Exception as e:
            error(f"保存执行摘要失败: {e}")

    async def _save_stage_statistics(self, state: WorkflowState, task_id: str):
        """保存阶段统计"""
        try:
            # 从记忆模块获取各阶段统计
            parse_stats = self.memory.recall(f"stats_{PipelineNode.PARSE_SCRIPT.value}", memory_type=MemoryType.MEDIUM)
            segment_stats = self.memory.recall(f"stats_{PipelineNode.SEGMENT_SHOT.value}", memory_type=MemoryType.MEDIUM)
            split_stats = self.memory.recall(f"stats_{PipelineNode.SPLIT_VIDEO.value}", memory_type=MemoryType.MEDIUM)
            convert_stats = self.memory.recall(f"stats_{PipelineNode.CONVERT_PROMPT.value}", memory_type=MemoryType.MEDIUM)

            stage_stats = {
                "script_parser": parse_stats,
                "shot_segmenter": segment_stats,
                "video_splitter": split_stats,
                "prompt_converter": convert_stats
            }

            await self._save_json_async(task_id, stage_stats, "stage_statistics.json")
            debug(f"阶段统计已保存: {task_id}")
        except Exception as e:
            error(f"保存阶段统计失败: {e}")

    async def _save_issues_report(self, state: WorkflowState, task_id: str):
        """保存问题追踪报告"""
        try:
            # 从记忆模块获取各阶段问题
            parse_issues = self.memory.recall(f"issues_{PipelineNode.PARSE_SCRIPT.value}", memory_type=MemoryType.SHORT) or []
            segment_issues = self.memory.recall(f"issues_{PipelineNode.SEGMENT_SHOT.value}", memory_type=MemoryType.SHORT) or []
            split_issues = self.memory.recall(f"issues_{PipelineNode.SPLIT_VIDEO.value}", memory_type=MemoryType.SHORT) or []
            convert_issues = self.memory.recall(f"issues_{PipelineNode.CONVERT_PROMPT.value}", memory_type=MemoryType.SHORT) or []
            continuity_issues = self.memory.recall("continuity_issues_history", memory_type=MemoryType.MEDIUM) or []

            # 按严重程度分组
            def group_by_severity(issues):
                severity_groups = {"critical": 0, "major": 0, "moderate": 0, "warning": 0, "info": 0}
                for issue in issues:
                    severity = issue.get("severity", {}).get("value", "unknown") if isinstance(issue, dict) else getattr(issue, "severity", None)
                    if severity and severity in severity_groups:
                        severity_groups[severity] += 1
                return severity_groups

            issues_report = {
                "task_id": task_id,
                "total_issues": len(parse_issues) + len(segment_issues) + len(split_issues) + len(convert_issues),
                "by_stage": {
                    "script_parser": {
                        "count": len(parse_issues),
                        "by_severity": group_by_severity(parse_issues),
                        "issues": parse_issues
                    },
                    "shot_segmenter": {
                        "count": len(segment_issues),
                        "by_severity": group_by_severity(segment_issues),
                        "issues": segment_issues
                    },
                    "video_splitter": {
                        "count": len(split_issues),
                        "by_severity": group_by_severity(split_issues),
                        "issues": split_issues
                    },
                    "prompt_converter": {
                        "count": len(convert_issues),
                        "by_severity": group_by_severity(convert_issues),
                        "issues": convert_issues
                    },
                    "continuity": {
                        "count": len(continuity_issues),
                        "by_severity": group_by_severity(continuity_issues),
                        "issues": continuity_issues
                    }
                }
            }

            await self._save_json_async(task_id, issues_report, "issues_report.json")
            debug(f"问题报告已保存: {task_id}")
        except Exception as e:
            error(f"保存问题报告失败: {e}")

    async def _save_repair_history(self, state: WorkflowState, task_id: str):
        """保存修复历史记录"""
        try:
            # 从记忆模块获取修复历史
            repair_parse = self.memory.recall(f"repair_{PipelineNode.PARSE_SCRIPT.value}", memory_type=MemoryType.MEDIUM)
            repair_segment = self.memory.recall(f"repair_{PipelineNode.SEGMENT_SHOT.value}", memory_type=MemoryType.MEDIUM)
            repair_split = self.memory.recall(f"repair_{PipelineNode.SPLIT_VIDEO.value}", memory_type=MemoryType.MEDIUM)
            repair_convert = self.memory.recall(f"repair_{PipelineNode.CONVERT_PROMPT.value}", memory_type=MemoryType.MEDIUM)

            repair_history = {
                "task_id": task_id,
                "repair_count": sum(1 for r in [repair_parse, repair_segment, repair_split, repair_convert] if r),
                "repairs": {
                    "script_parser": repair_parse,
                    "shot_segmenter": repair_segment,
                    "video_splitter": repair_split,
                    "prompt_converter": repair_convert
                }
            }

            await self._save_json_async(task_id, repair_history, "repair_history.json")
            debug(f"修复历史已保存: {task_id}")
        except Exception as e:
            error(f"保存修复历史失败: {e}")

    async def _save_quality_report(self, state: WorkflowState, task_id: str):
        """保存质量审查报告"""
        try:
            # 从记忆模块获取审查历史
            audit_history = self.memory.recall("audit_results_history", memory_type=MemoryType.MEDIUM) or []
            latest_audit = self.memory.recall("latest_audit_result", memory_type=MemoryType.SHORT)

            # 计算质量分数趋势
            quality_trend = []
            for i, audit in enumerate(audit_history[-10:]):
                quality_trend.append({
                    "index": i,
                    "score": audit.get("score", 0),
                    "timestamp": audit.get("timestamp")
                })

            quality_report = {
                "task_id": task_id,
                "total_audits": len(audit_history),
                "latest_audit": latest_audit,
                "audit_history": audit_history,
                "quality_score_trend": quality_trend,
                "final_score": state.audit_report.score if state.audit_report else 0,
                "final_status": state.audit_report.status.value if state.audit_report else "unknown"
            }

            await self._save_json_async(task_id, quality_report, "quality_report.json")
            debug(f"质量报告已保存: {task_id}")
        except Exception as e:
            error(f"保存质量报告失败: {e}")

    async def _save_continuity_report(self, state: WorkflowState, task_id: str):
        """保存连续性检查报告"""
        try:
            # 从记忆模块获取连续性历史
            continuity_history = self.memory.recall("continuity_issues_history", memory_type=MemoryType.MEDIUM) or []

            # 按类型分组
            issues_by_type = {}
            issues_by_severity = {"critical": 0, "major": 0, "moderate": 0, "warning": 0, "info": 0}

            for issue in continuity_history:
                issue_type = issue.get("type", "unknown")
                severity = issue.get("severity", "moderate")

                issues_by_type[issue_type] = issues_by_type.get(issue_type, 0) + 1
                if severity in issues_by_severity:
                    issues_by_severity[severity] += 1

            continuity_report = {
                "task_id": task_id,
                "total_continuity_issues": len(continuity_history),
                "issues_by_type": issues_by_type,
                "issues_by_severity": issues_by_severity,
                "continuity_retry_count": state.continuity_retry_count,
                "continuity_passed": state.continuity_passed,
                "issues": continuity_history[-50:]  # 只保留最近50条
            }

            await self._save_json_async(task_id, continuity_report, "continuity_report.json")
            debug(f"连续性报告已保存: {task_id}")
        except Exception as e:
            error(f"保存连续性报告失败: {e}")

    async def _save_memory_report(self, state: WorkflowState, task_id: str):
        """保存记忆统计报告"""
        try:
            # 获取记忆统计
            memory_stats = self.memory.get_stats()
            most_accessed = self.memory.get_most_accessed(5)

            memory_report = {
                "task_id": task_id,
                "memory_statistics": memory_stats,
                "most_accessed": most_accessed,
                "short_term_size": self.memory.short_term.size() if hasattr(self.memory, 'short_term') else 0,
                "medium_term_stages": len(self.memory.medium_term.stage_memories) if hasattr(self.memory, 'medium_term') else 0,
                "long_term_enabled": self.memory.long_term is not None
            }

            await self._save_json_async(task_id, memory_report, "memory_report.json")
            debug(f"记忆报告已保存: {task_id}")
        except Exception as e:
            error(f"保存记忆报告失败: {e}")

    async def _save_json_async(self, task_id: str, data: Dict, filename: str):
        """异步保存 JSON 文件"""
        try:
            # 使用线程池执行同步保存操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.storage.save_json_result,
                task_id,
                data,
                filename
            )
        except Exception as e:
            error(f"保存 JSON 失败 {filename}: {e}")

    def shutdown(self):
        """关闭后台线程"""
        if self._background_loop:
            self._background_loop.call_soon_threadsafe(self._background_loop.stop)
        if self._background_thread and self._background_thread.is_alive():
            self._background_thread.join(timeout=5)
        info("WorkflowOutputWriter 已关闭")
