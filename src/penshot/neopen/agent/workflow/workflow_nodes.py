"""
@FileName: workflow_nodes.py
@Description: LangGraph工作流节点实现，包含所有工作流执行功能
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import time
import traceback
from datetime import datetime
from typing import Dict, Any, List

from penshot.logger import error, debug, info, warning
from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import ContinuityGuardianChecker
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import ContinuityCheckResult, ContinuityIssueType, ContinuityIssue
from penshot.neopen.agent.continuity_guardian.continuity_repair_generator import ContinuityRepairGenerator
from penshot.neopen.agent.human_decision.human_decision_intervention import HumanIntervention
from penshot.neopen.agent.quality_auditor.quality_auditor_models import AuditStatus, QualityAuditReport, SeverityLevel, QualityRepairParams
from penshot.neopen.agent.workflow.workflow_models import AgentStage, PipelineNode
from penshot.neopen.agent.workflow.workflow_output import WorkflowOutputWriter
from penshot.neopen.agent.workflow.workflow_states import WorkflowState
from penshot.neopen.task.task_models import TaskStage, TaskStatus
from penshot.neopen.tools.memory.memory_manager import MemoryManager
from penshot.neopen.tools.memory.memory_models import MemoryConfig, MemoryLevel
from penshot.neopen.tools.result_storage_tool import create_result_storage
from penshot.utils.log_utils import print_log_exception


class WorkflowNodes:
    """工作流节点集合，封装所有工作流执行功能"""

    def __init__(self, script_id, script_parser, shot_segmenter, video_splitter,
                 prompt_converter, quality_auditor,
                 llm, embeddings, task_manager):
        """
        初始化工作流节点集合

        Args:
            script_id: 脚本ID
            script_parser: 剧本解析器实例
            shot_segmenter: 分镜生成器实例
            video_splitter: 视频分割器实例
            prompt_converter: 提示词转换器实例
            quality_auditor: 质量审查实例
            llm: 语言模型实例
            embeddings: 嵌入模型实例
            task_manager: 任务管理器实例
        """
        self.script_id = script_id
        self.llm = llm
        self.embeddings = embeddings
        self.task_manager = task_manager

        # 初始化记忆管理器时配置记忆层级
        self.memory = MemoryManager(
            llm=self.llm,
            script_id=self.script_id,
            config=MemoryConfig(
                embeddings=self.embeddings,
                short_term_size=20,
                short_term_ttl=3600,
                medium_term_max_tokens=500,
                long_term_enabled=True,
                long_term_k=3,
            )
        )

        # 启动时恢复长期记忆中的常见问题模式
        self._load_common_patterns()

        self.script_parser = script_parser
        self.shot_segmenter = shot_segmenter
        self.video_splitter = video_splitter
        self.prompt_converter = prompt_converter
        self.quality_auditor = quality_auditor

        # 初始化人工干预节点
        self.human_intervention = HumanIntervention(timeout_seconds=180)
        self.storage = create_result_storage()

        # 连续性守护
        self.generator = ContinuityRepairGenerator()
        self.checker = ContinuityGuardianChecker()
        # 初始化输出写入器
        self.output_writer = WorkflowOutputWriter(self.storage, self.memory)

    def parse_script_node(self, state: WorkflowState) -> WorkflowState:
        """
        剧本解析节点（增强版）
        功能：将原始剧本解析为结构化元素序列，支持修复参数
        """
        try:
            # 更新状态：开始解析
            self._update_task_status(state.task_id, TaskStatus.PROCESSING)
            self._update_task_progress(state.task_id, TaskStage.PARSING_START, 0)

            # ========== 1. 加载历史上下文 ==========
            recent_strategy = self._get_memory_dict("parsing_strategy_recent", level=MemoryLevel.SHORT_TERM)
            historical_stats = self._get_memory_dict("stats_parse_script", level=MemoryLevel.MEDIUM_TERM)
            common_issues = self._get_memory_list("common_parse_issues", level=MemoryLevel.LONG_TERM, default=[])

            historical_context = {
                "recent_strategy": recent_strategy,
                "historical_stats": historical_stats,
                "common_issues": common_issues
            }

            # 只有存在有效内容时才应用历史上下文
            if historical_context and any(v is not None for v in historical_context.values()):
                self.script_parser.apply_historical_context(historical_context)

            # ========== 2. 加载修复参数 ==========
            repair_params = state.repair_params.get(PipelineNode.PARSE_SCRIPT, None)
            if repair_params:
                self.script_parser.apply_repair_params(PipelineNode.PARSE_SCRIPT, repair_params)

                info(f"剧本解析节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")
            else:
                debug("剧本解析节点执行（无修复参数）")

            # 更新状态：解析中
            self._update_task_progress(state.task_id, TaskStage.PARSING_SCRIPT, 30)

            # ========== 3. 执行解析 ==========
            parsed_script = self.script_parser.process(state.raw_script)

            debug(f"剧本解析完成，场景数: {len(parsed_script.scenes)}，角色数: {len(parsed_script.characters)}")
            debug(f"完整性评分: {parsed_script.stats.get('completeness_score', 0)}")

            # 更新状态：解析完成
            self._update_task_progress(state.task_id, TaskStage.PARSING_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.PARSING_COMPLETE, {
                "scene_count": len(parsed_script.scenes),
                "character_count": len(parsed_script.characters),
                "completeness_score": parsed_script.stats.get("completeness_score", 0)
            })

            # ========== 4. 保存结果 ==========
            self.storage.save_obj_result(state.script_id, state.task_id, parsed_script, "script_parser_result.json")

            # ========== 5. 问题检测与记忆存储 ==========
            parse_issues = self.script_parser.detect_issues(parsed_script, state.raw_script)
            if parse_issues:
                # 短期记忆：当前任务的问题
                self.memory.add(
                    f"issues_{PipelineNode.PARSE_SCRIPT.value}",
                    [issue.dict() for issue in parse_issues],
                    level=MemoryLevel.SHORT_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )

                # 长期记忆：更新常见问题模式
                existing_common = self._get_memory_list("common_parse_issues", level=MemoryLevel.LONG_TERM, default=[])
                # 确保 existing_common 是列表
                if not isinstance(existing_common, list):
                    # 如果是字符串，尝试解析为 JSON
                    if isinstance(existing_common, str):
                        try:
                            import json
                            existing_common = json.loads(existing_common)
                        except:
                            existing_common = []
                    else:
                        existing_common = []

                all_issues = existing_common + [issue.dict() for issue in parse_issues]
                if len(all_issues) > 100:
                    all_issues = all_issues[-100:]
                self.memory.add("common_parse_issues", all_issues, level=MemoryLevel.LONG_TERM,
                    metadata={"_serialized": True})

            # ========== 6. 更新状态 ==========
            state.parsed_script = parsed_script
            state.current_stage = AgentStage.PARSER
            state.current_node = PipelineNode.PARSE_SCRIPT

            # ========== 7. 存储解析统计（中期记忆） ==========
            current_stats = {
                "timestamp": datetime.now().isoformat(),
                "parse_attempts": parsed_script.stats.get("parse_attempts", 1),
                "completeness_score": parsed_script.stats.get("completeness_score", 0),
                "parsing_confidence": parsed_script.stats.get("parsing_confidence", {}),
                "repair_applied": repair_params is not None,
                "issue_count": len(parse_issues)
            }

            self.memory.add(
                f"stats_{PipelineNode.PARSE_SCRIPT.value}",
                current_stats,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 8. 存储修复历史（中期记忆） ==========
            self.memory.add(
                f"repair_{PipelineNode.PARSE_SCRIPT.value}",
                {
                    "timestamp": datetime.now().isoformat(),
                    "repair_params": repair_params.model_dump() if repair_params else None,
                    "success": True,
                    "stats": current_stats
                },
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 9. 日志输出 ==========
            stats = self._get_memory_dict(f"stats_{PipelineNode.PARSE_SCRIPT.value}", level=MemoryLevel.MEDIUM_TERM)
            info(f"剧本解析节点完成，统计: {stats}")

            # ========== 10. 节点成功完成，清理临时状态 ==========
            self.script_parser.clear_repair_params()
            self.script_parser.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"剧本解析失败: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)
            debug(f"解析异常堆栈: {traceback.format_exc()}")

            state.current_node = PipelineNode.PARSE_SCRIPT
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.PARSE_SCRIPT

        return state

    def split_shots_node(self, state: WorkflowState) -> WorkflowState:
        """
        镜头拆分节点（增强版）
        功能：将结构化剧本拆分为视觉镜头，支持修复参数
        """
        try:
            # 更新状态：开始拆分
            self._update_task_progress(state.task_id, TaskStage.SEGMENT_START, 0)

            # ========== 1. 加载历史上下文 ==========
            historical_shot_stats = self._get_memory_dict(f"stats_{PipelineNode.SEGMENT_SHOT.value}", level=MemoryLevel.MEDIUM_TERM)
            historical_shot_issues = self._get_memory_list(f"issues_{PipelineNode.SEGMENT_SHOT.value}", level=MemoryLevel.SHORT_TERM, default=[])
            common_shot_patterns = self._get_memory_list("common_shot_patterns", level=MemoryLevel.LONG_TERM, default=[])

            historical_context = {
                "historical_stats": historical_shot_stats,
                "historical_issues": historical_shot_issues,
                "common_patterns": common_shot_patterns
            }

            # 只有存在有效内容时才应用历史上下文
            if historical_context and any(v is not None for v in historical_context.values()):
                self.shot_segmenter.apply_historical_context(historical_context)

            # ========== 2. 加载修复参数 ==========
            repair_params = state.repair_params.get(PipelineNode.SEGMENT_SHOT, None)

            if repair_params:
                self.shot_segmenter.apply_repair_params(PipelineNode.SEGMENT_SHOT, repair_params)

                info(f"分镜生成节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")

                # 记录修复来源到记忆
                self.memory.add(
                    f"repair_{PipelineNode.SEGMENT_SHOT.value}",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions,
                        "success": True
                    },
                    level=MemoryLevel.MEDIUM_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )
            else:
                debug("分镜生成节点执行（无修复参数）")

            # 更新状态：拆分中
            self._update_task_progress(state.task_id, TaskStage.SEGMENTING, 50)

            # ========== 3. 执行分镜生成 ==========
            shot_sequence = self.shot_segmenter.process(state.parsed_script)

            # 更新状态：拆分完成
            self._update_task_progress(state.task_id, TaskStage.SEGMENT_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.SEGMENT_COMPLETE, {
                "shot_count": len(shot_sequence.shots),
                "total_duration": sum(s.duration for s in shot_sequence.shots)
            })

            if not shot_sequence:
                raise Exception("分镜生成返回空结果")

            debug(f"分镜解析完成，镜头数: {len(shot_sequence.shots)}")
            debug(f"总时长: {sum(s.duration for s in shot_sequence.shots):.1f}秒")

            # 统计镜头类型分布
            shot_types = {}
            for shot in shot_sequence.shots:
                shot_types[shot.shot_type.value] = shot_types.get(shot.shot_type.value, 0) + 1
            debug(f"镜头类型分布: {shot_types}")

            # ========== 4. 保存结果 ==========
            self.storage.save_obj_result(state.script_id, state.task_id, shot_sequence, "shot_segmenter_result.json")

            # ========== 5. 问题检测与记忆存储 ==========
            segment_issues = self.shot_segmenter.detect_issues(shot_sequence, state.parsed_script)
            if segment_issues:
                debug(f"分镜过程发现问题: {len(segment_issues)}个")
                self.memory.add(
                    f"issues_{PipelineNode.SEGMENT_SHOT.value}",
                    [issue.dict() for issue in segment_issues],
                    level=MemoryLevel.SHORT_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )

            # ========== 6. 更新状态 ==========
            state.shot_sequence = shot_sequence
            state.current_stage = AgentStage.SEGMENTER
            state.current_node = PipelineNode.SEGMENT_SHOT

            # ========== 7. 存储分镜统计（中期记忆） ==========
            current_stats = {
                "timestamp": datetime.now().isoformat(),
                "shot_count": len(shot_sequence.shots),
                "total_duration": sum(s.duration for s in shot_sequence.shots),
                "avg_duration": sum(s.duration for s in shot_sequence.shots) / len(shot_sequence.shots) if shot_sequence.shots else 0,
                "shot_types": shot_types,
                "repair_applied": repair_params is not None,
                "issue_count": len(segment_issues)
            }

            self.memory.add(
                f"stats_{PipelineNode.SEGMENT_SHOT.value}",
                current_stats,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 8. 存储修复历史 ==========
            self.memory.add(
                f"repair_{PipelineNode.SEGMENT_SHOT.value}",
                {
                    "timestamp": datetime.now().isoformat(),
                    "repair_params": repair_params.model_dump() if repair_params else None,
                    "success": True,
                    "stats": current_stats
                },
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 9. 日志输出 ==========
            stats = self._get_memory_dict(f"stats_{PipelineNode.SEGMENT_SHOT.value}", level=MemoryLevel.MEDIUM_TERM)
            info(f"分镜生成节点完成，统计: {stats}")

            # ========== 10. 节点成功完成，清理临时状态 ==========
            self.shot_segmenter.clear_repair_params()
            self.shot_segmenter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"分镜解析节点异常: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)

            state.current_node = PipelineNode.SEGMENT_SHOT
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.SEGMENT_SHOT

        return state

    def fragment_for_ai_node(self, state: WorkflowState) -> WorkflowState:
        """
        AI分段节点（增强版）
        功能：将镜头按限制切分为AI可处理的片段，支持修复参数
        """
        try:
            # 更新状态：开始分段
            self._update_task_progress(state.task_id, TaskStage.SPLIT_START, 0)

            # ========== 1. 加载历史上下文 ==========
            historical_split_stats = self._get_memory_dict(f"stats_{PipelineNode.SPLIT_VIDEO.value}", level=MemoryLevel.MEDIUM_TERM)
            historical_split_issues = self._get_memory_list(f"issues_{PipelineNode.SPLIT_VIDEO.value}", level=MemoryLevel.SHORT_TERM, default=[])
            common_split_patterns = self._get_memory_list("common_split_patterns", level=MemoryLevel.LONG_TERM, default=[])

            historical_context = {
                "historical_stats": historical_split_stats,
                "historical_issues": historical_split_issues,
                "common_patterns": common_split_patterns
            }

            # 只有存在有效内容时才应用历史上下文
            if historical_context and any(v is not None for v in historical_context.values()):
                self.video_splitter.apply_historical_context(historical_context)

            # ========== 2. 加载修复参数 ==========
            repair_params = state.repair_params.get(PipelineNode.SPLIT_VIDEO, None)

            if repair_params:
                self.video_splitter.apply_repair_params(PipelineNode.SPLIT_VIDEO, repair_params)

                info(f"视频分割节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")

                self.memory.add(
                    f"repair_{PipelineNode.SPLIT_VIDEO.value}",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions,
                        "success": True
                    },
                    level=MemoryLevel.MEDIUM_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )
            else:
                debug("视频分割节点执行（无修复参数）")

            # 更新状态：分段中
            self._update_task_progress(state.task_id, TaskStage.SPLITTING, 50)

            # ========== 3. 执行视频分割 ==========
            fragment_sequence = self.video_splitter.process(
                state.shot_sequence,
                parsed_script=state.parsed_script,
            )

            # 更新状态：分段完成
            self._update_task_progress(state.task_id, TaskStage.SPLIT_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.SPLIT_COMPLETE, {
                "fragment_count": len(fragment_sequence.fragments),
                "total_duration": sum(f.duration for f in fragment_sequence.fragments)
            })

            if not fragment_sequence:
                raise Exception("视频分割返回空结果")

            debug(f"视频分段完成，视频片段数: {len(fragment_sequence.fragments)}")
            total_duration = sum(f.duration for f in fragment_sequence.fragments)
            debug(f"总时长: {total_duration:.1f}秒")

            # 统计片段时长分布
            durations = [f.duration for f in fragment_sequence.fragments]
            debug(f"时长分布: 最小={min(durations):.1f}s, 最大={max(durations):.1f}s, 平均={sum(durations) / len(durations):.1f}s")

            # ========== 4. 保存结果 ==========
            self.storage.save_obj_result(state.script_id, state.task_id, fragment_sequence, "video_splitter_result.json")

            # ========== 5. 问题检测与记忆存储 ==========
            split_issues = self.video_splitter.detect_issues(fragment_sequence, state.shot_sequence)
            if split_issues:
                debug(f"分割过程发现问题: {len(split_issues)}个")
                self.memory.add(
                    f"issues_{PipelineNode.SPLIT_VIDEO.value}",
                    [issue.dict() for issue in split_issues],
                    level=MemoryLevel.SHORT_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )

            # ========== 6. 更新状态 ==========
            state.fragment_sequence = fragment_sequence
            state.current_stage = AgentStage.SPLITTER
            state.current_node = PipelineNode.SPLIT_VIDEO

            # 获取metadata
            metadata = getattr(fragment_sequence, 'metadata', {})

            # ========== 7. 存储分割统计（中期记忆） ==========
            current_stats = {
                "timestamp": datetime.now().isoformat(),
                "fragment_count": len(fragment_sequence.fragments),
                "total_duration": total_duration,
                "avg_duration": total_duration / len(fragment_sequence.fragments) if fragment_sequence.fragments else 0,
                "min_duration": min(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0,
                "repair_applied": repair_params is not None,
                "ai_split_count": metadata.get('ai_split_count', 0),
                "rule_split_count": metadata.get('rule_split_count', 0),
                "issue_count": len(split_issues)
            }

            self.memory.add(
                f"stats_{PipelineNode.SPLIT_VIDEO.value}",
                current_stats,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 8. 存储修复历史 ==========
            self.memory.add(
                f"repair_{PipelineNode.SPLIT_VIDEO.value}",
                {
                    "timestamp": datetime.now().isoformat(),
                    "repair_params": repair_params.model_dump() if repair_params else None,
                    "success": True,
                    "stats": current_stats
                },
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 9. 日志输出 ==========
            stats = self._get_memory_dict(f"stats_{PipelineNode.SPLIT_VIDEO.value}", level=MemoryLevel.MEDIUM_TERM)
            info(f"视频分割节点完成，统计: {stats}")

            # ========== 10. 节点成功完成，清理临时状态 ==========
            self.video_splitter.clear_repair_params()
            self.video_splitter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"视频分段异常: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)

            state.current_node = PipelineNode.SPLIT_VIDEO
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.SPLIT_VIDEO

        return state

    def generate_prompts_node(self, state: WorkflowState) -> WorkflowState:
        """
        Prompt生成节点（增强版）
        功能：为每个片段生成AI视频生成提示词，支持修复参数
        """
        try:
            # 更新状态：开始转换
            self._update_task_progress(state.task_id, TaskStage.CONVERT_START, 0)

            # ========== 1. 加载历史上下文 ==========
            historical_convert_stats = self._get_memory_dict(f"stats_{PipelineNode.CONVERT_PROMPT.value}", level=MemoryLevel.MEDIUM_TERM)
            historical_convert_issues = self._get_memory_list(f"issues_{PipelineNode.CONVERT_PROMPT.value}", level=MemoryLevel.SHORT_TERM, default=[])
            successful_prompts = self._get_memory_list("successful_prompt_patterns", level=MemoryLevel.LONG_TERM, default=[])

            historical_context = {
                "historical_stats": historical_convert_stats,
                "historical_issues": historical_convert_issues,
                "successful_patterns": successful_prompts
            }

            # 只有存在有效内容时才应用历史上下文
            if historical_context and any(v is not None for v in historical_context.values()):
                self.prompt_converter.apply_historical_context(historical_context)

            # ========== 2. 加载修复参数 ==========
            repair_params = state.repair_params.get(PipelineNode.CONVERT_PROMPT, None)

            if repair_params:
                self.prompt_converter.apply_repair_params(PipelineNode.CONVERT_PROMPT, repair_params)

                info(f"提示词转换节点收到修复参数，问题类型: {repair_params.issue_types}")
                if repair_params.suggestions:
                    info(f"修复建议: {repair_params.suggestions}")

                self.memory.add(
                    f"repair_{PipelineNode.CONVERT_PROMPT.value}",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "issue_types": repair_params.issue_types,
                        "suggestions": repair_params.suggestions,
                        "success": True
                    },
                    level=MemoryLevel.MEDIUM_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )
            else:
                debug("提示词转换节点执行（无修复参数）")

            # 更新状态：转换中
            self._update_task_progress(state.task_id, TaskStage.CONVERTING, 50)

            # ========== 3. 执行提示词转换 ==========
            instructions = self.prompt_converter.process(
                state.fragment_sequence,
                parsed_script=state.parsed_script,
            )

            # 更新状态：转换完成
            self._update_task_progress(state.task_id, TaskStage.CONVERT_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.CONVERT_COMPLETE, {
                "prompt_count": len(instructions.fragments),
                "audio_prompt_count": sum(1 for f in instructions.fragments if f.audio_prompt)
            })

            if not instructions:
                raise Exception("提示词转换返回空结果")

            debug(f"片段指令转换完成，指令片段数: {len(instructions.fragments)}")

            # 统计提示词信息
            prompt_lengths = [len(f.prompt) for f in instructions.fragments]
            debug(f"提示词长度统计: 平均={sum(prompt_lengths) / len(prompt_lengths):.0f}, "
                  f"最小={min(prompt_lengths)}, 最大={max(prompt_lengths)}")

            # 统计音频提示词
            audio_count = sum(1 for f in instructions.fragments if f.audio_prompt)
            debug(f"音频提示词: {audio_count}/{len(instructions.fragments)}个片段")

            # 统计风格分布
            styles = {}
            for f in instructions.fragments:
                if f.style:
                    styles[f.style] = styles.get(f.style, 0) + 1
            if styles:
                debug(f"风格分布: {styles}")

            # ========== 4. 保存结果 ==========
            self.storage.save_obj_result(state.script_id, state.task_id, instructions, "prompt_converter_result.json")

            # ========== 5. 问题检测与记忆存储 ==========
            convert_issues = self.prompt_converter.detect_issues(instructions, state.fragment_sequence)
            if convert_issues:
                debug(f"转换过程发现问题: {len(convert_issues)}个")
                self.memory.add(
                    f"issues_{PipelineNode.CONVERT_PROMPT.value}",
                    [issue.dict() for issue in convert_issues],
                    level=MemoryLevel.SHORT_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )

            # ========== 6. 更新状态 ==========
            state.instructions = instructions
            state.current_stage = AgentStage.CONVERTER
            state.current_node = PipelineNode.CONVERT_PROMPT

            # ========== 7. 存储转换统计（中期记忆） ==========
            current_stats = {
                "timestamp": datetime.now().isoformat(),
                "prompt_count": len(instructions.fragments),
                "avg_prompt_length": sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0,
                "min_prompt_length": min(prompt_lengths) if prompt_lengths else 0,
                "max_prompt_length": max(prompt_lengths) if prompt_lengths else 0,
                "audio_prompt_count": audio_count,
                "style_distribution": styles,
                "repair_applied": repair_params is not None,
                "issue_count": len(convert_issues)
            }

            self.memory.add(
                f"stats_{PipelineNode.CONVERT_PROMPT.value}",
                current_stats,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 8. 存储修复历史 ==========
            self.memory.add(
                f"repair_{PipelineNode.CONVERT_PROMPT.value}",
                {
                    "timestamp": datetime.now().isoformat(),
                    "repair_params": repair_params.model_dump() if repair_params else None,
                    "success": True,
                    "stats": current_stats
                },
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # ========== 9. 日志输出 ==========
            stats = self._get_memory_dict(f"stats_{PipelineNode.CONVERT_PROMPT.value}", level=MemoryLevel.MEDIUM_TERM)
            info(f"提示词转换节点完成，统计: {stats}")

            # ========== 10. 节点成功完成，清理临时状态 ==========
            self.prompt_converter.clear_repair_params()
            self.prompt_converter.clear_historical_context()

        except Exception as e:
            print_log_exception()
            error_msg = f"片段指令转换异常: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)

            state.current_node = PipelineNode.CONVERT_PROMPT
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.CONVERT_PROMPT

        return state

    def quality_audit_node(self, state: WorkflowState) -> WorkflowState:
        """
        质量审查节点（增强版）
        功能：合并基本规则审查和LLM深度审查，输出详细的审查报告

        变更说明：
        - 新增LLM深度审查能力
        - 支持问题分类和来源追溯
        - 生成增强的修复参数
        - 自动调用各阶段修复器
        """
        # 更新状态：开始审查
        self._update_task_progress(state.task_id, TaskStage.AUDIT_START, 0)

        # 从记忆模块获取各阶段问题
        all_stage_issues = {
            PipelineNode.PARSE_SCRIPT: self._get_memory_list(f"issues_{PipelineNode.PARSE_SCRIPT.value}", level=MemoryLevel.SHORT_TERM, default=[]),
            PipelineNode.SEGMENT_SHOT: self._get_memory_list(f"issues_{PipelineNode.SEGMENT_SHOT.value}", level=MemoryLevel.SHORT_TERM, default=[]),
            PipelineNode.SPLIT_VIDEO: self._get_memory_list(f"issues_{PipelineNode.SPLIT_VIDEO.value}", level=MemoryLevel.SHORT_TERM, default=[]),
            PipelineNode.CONVERT_PROMPT: self._get_memory_list(f"issues_{PipelineNode.CONVERT_PROMPT.value}", level=MemoryLevel.SHORT_TERM, default=[]),
        }

        # 回忆历史审查经验
        historical_audit_results = self._get_memory_list("audit_results_history", level=MemoryLevel.MEDIUM_TERM, default=[])
        successful_repair_patterns = self._get_memory_list("repair_success_patterns", level=MemoryLevel.LONG_TERM, default=[])

        # 构建历史上下文
        historical_context = {
            "historical_audit_results": historical_audit_results,
            "successful_repair_patterns": successful_repair_patterns
        }

        # 检查是否短时间内重复执行
        if state.audit_executed and state.audit_timestamp:
            last_time = datetime.fromisoformat(state.audit_timestamp)
            current_time = datetime.now()
            time_diff = (current_time - last_time).total_seconds()

            if time_diff < 10:
                last_result = self.memory.get_latest_deserialized("latest_audit_result", MemoryLevel.SHORT_TERM)
                if last_result:
                    report_data = last_result.get("report")
                    if report_data:
                        state.audit_report = QualityAuditReport(**report_data)
                        return state

        info(f"进入质量审查节点（增强版），当前阶段={state.current_stage.value}")
        info(f"审查前状态: 片段数={len(state.fragment_sequence.fragments) if state.fragment_sequence else 0}")

        # 更新状态：审查中
        self._update_task_progress(state.task_id, TaskStage.AUDITING, 50)

        try:
            # 执行质量审查（传入各阶段问题和历史上下文）
            result = self.quality_auditor.qa_process(
                state.instructions,
                all_stage_issues,
                historical_context
            )

            debug(f"质量审查完成:")
            debug(f"  - 审查状态: {result.status.value}")
            debug(f"  - 质量分数: {result.score}%")
            debug(f"  - 总问题数: {len(result.violations)}")
            debug(f"  - 检查项数: {len(result.checks)}")

            # 更新状态：审查完成
            self._update_task_progress(state.task_id, TaskStage.AUDIT_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.AUDIT_COMPLETE, {
                "status": result.status.value,
                "score": result.score,
                "violations_count": len(result.violations)
            })

            # 更新执行标志
            state.audit_executed = True
            state.repair_params = result.repair_params
            state.audit_timestamp = datetime.now().isoformat()

            # 存储最新审查结果
            self.memory.add(
                "latest_audit_result",
                {
                    "timestamp": datetime.now().isoformat(),
                    "status": result.status.value,
                    "score": result.score,
                    "violations": [v.dict() for v in result.violations],
                    "repair_params": {k: v.model_dump() for k, v in result.repair_params.items()} if result.repair_params else None,
                    "report": result.model_dump()
                },
                level=MemoryLevel.SHORT_TERM,
                metadata={"_serialized": True}  # 添加序列化标记
            )

            # 更新审查历史（中期记忆）
            audit_history = self._get_memory_list("audit_results_history", level=MemoryLevel.MEDIUM_TERM, default=[])
            audit_history.append({
                "timestamp": datetime.now().isoformat(),
                "status": result.status.value,
                "score": result.score,
                "violations_count": len(result.violations)
            })
            if len(audit_history) > 50:
                audit_history = audit_history[-50:]
            self.memory.add("audit_results_history", audit_history, level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True})

            info(f"审计结果汇总: 状态={result.status.value}, 分数={result.score}%, 问题统计={result.stats}")

            # 记录错误来源（根据审查结果）
            if result.status in [AuditStatus.FAILED, AuditStatus.CRITICAL_ISSUES]:
                state.error_source = PipelineNode.AUDIT_QUALITY
                critical_issues = [
                    v for v in result.violations
                    if v.severity in [SeverityLevel.CRITICAL, SeverityLevel.ERROR]
                ]
                if critical_issues:
                    state.error = f"质量审查发现严重问题: {len(critical_issues)}个"
                    state.error_messages.extend([
                        f"[{v.severity.value}] {v.description}"
                        for v in critical_issues[:3]
                    ])

            # ========== 关键修复：调用各阶段修复器 ==========
            if result.repair_params:
                repair_success = True
                self.memory.add(
                    f"repair_result_{state.task_id}",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "success": repair_success,
                        "stages_fixed": list(result.repair_params.keys())
                    },
                    level=MemoryLevel.SHORT_TERM,
                    metadata={"_serialized": True}  # 添加序列化标记
                )

                repair_count = 0
                for node, params in result.repair_params.items():
                    if not params.fix_needed:
                        continue

                    debug(f"开始修复阶段 {node.value}，问题类型: {params.issue_types}")

                    try:
                        if node == PipelineNode.PARSE_SCRIPT:
                            state.parsed_script = self.script_parser.repair_result(
                                state.parsed_script,
                                params.issues if hasattr(params, 'issues') else [],
                                state.raw_script
                            )
                            repair_count += 1
                            info(f"剧本解析修复完成，执行了{len(params.issues) if hasattr(params, 'issues') else 0}个修复")

                        elif node == PipelineNode.SEGMENT_SHOT:
                            state.shot_sequence = self.shot_segmenter.repair_result(
                                state.shot_sequence,
                                params.issues if hasattr(params, 'issues') else [],
                                state.parsed_script
                            )
                            repair_count += 1
                            info(f"分镜生成修复完成")

                        elif node == PipelineNode.SPLIT_VIDEO:
                            state.fragment_sequence = self.video_splitter.repair_result(
                                state.fragment_sequence,
                                params.issues if hasattr(params, 'issues') else [],
                                state.shot_sequence
                            )
                            repair_count += 1
                            info(f"视频分割修复完成")

                        elif node == PipelineNode.CONVERT_PROMPT:
                            state.instructions = self.prompt_converter.repair_result(
                                state.instructions,
                                params.issues if hasattr(params, 'issues') else [],
                                state.fragment_sequence
                            )
                            repair_count += 1
                            debug(f"提示词转换修复完成")

                    except Exception as e:
                        error(f"修复阶段 {node.value} 时出错: {str(e)}")
                        print_log_exception()
                        state.error_messages.append(f"修复{node.value}失败: {str(e)}")

            # 保存审查结果
            self.storage.save_obj_result(state.script_id, state.task_id, result, "quality_auditor_result.json")

            if hasattr(result, 'detailed_analysis'):
                self.storage.save_obj_result(state.script_id, state.task_id, result.detailed_analysis, "quality_auditor_detailed_analysis.json")

            state.audit_report = result
            state.current_stage = AgentStage.AUDITOR
            state.current_node = PipelineNode.AUDIT_QUALITY

            # 根据审查状态决定后续流程
            if result.status == AuditStatus.PASSED:
                info("质量审查通过，继续执行后续流程")
            elif result.status == AuditStatus.MINOR_ISSUES:
                info("质量审查发现轻微问题，可以继续但建议关注")
            elif result.status in [AuditStatus.MODERATE_ISSUES, AuditStatus.MAJOR_ISSUES]:
                warning(f"质量审查发现中等问题，需要修复")
            elif result.status in [AuditStatus.CRITICAL_ISSUES, AuditStatus.FAILED]:
                error(f"质量审查发现严重问题，需要人工干预")
                state.needs_human_review = True
                state.error_source = PipelineNode.AUDIT_QUALITY

        except Exception as e:
            print_log_exception()
            error_msg = f"质量审查异常: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)

            state.current_node = PipelineNode.AUDIT_QUALITY
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.AUDIT_QUALITY

            state.audit_report = self._create_fallback_audit_report(state)

        return state

    def continuity_check_node(self, state: WorkflowState) -> WorkflowState:
        """
        连续性守护节点

        职责：
        1. 检查所有阶段的连续性（视觉、角色、场景、动作）
        2. 识别连续性问题的来源阶段
        3. 生成修复方案并触发重试
        """
        # 更新状态：开始检查
        self._update_task_progress(state.task_id, TaskStage.CONTINUITY_START, 0)

        try:
            # ========== 初始化或获取重试计数 ==========
            if not hasattr(state, 'continuity_retry_count'):
                state.continuity_retry_count = 0
            if not hasattr(state, 'max_continuity_retries'):
                state.max_continuity_retries = 3

            # 回忆历史连续性问题
            historical_continuity_issues = self._get_memory_list("continuity_issues_history", level=MemoryLevel.MEDIUM_TERM, default=[])
            successful_continuity_fixes = self._get_memory_list("successful_continuity_fixes", level=MemoryLevel.LONG_TERM, default=[])

            # 构建历史上下文
            historical_context = {
                "historical_issues": historical_continuity_issues,
                "successful_fixes": successful_continuity_fixes
            }

            # 1. 收集所有阶段的输出
            continuity_context = {
                "parsed_script": state.parsed_script,
                "shot_sequence": state.shot_sequence,
                "fragment_sequence": state.fragment_sequence,
                "instructions": state.instructions,
                "historical_context": historical_context
            }

            # 更新状态：检查中
            self._update_task_progress(state.task_id, TaskStage.CONTINUITY_CHECKING, 50)

            # 2. 执行连续性检查（返回 ContinuityCheckResult）
            check_result = self._check_continuity(continuity_context)

            # 更新状态：检查完成
            self._update_task_progress(state.task_id, TaskStage.CONTINUITY_COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.CONTINUITY_COMPLETE, {
                "passed": check_result.passed,
                "total_issues": check_result.total_issues,
                "retry_count": state.continuity_retry_count
            })

            # 3. 如果没有问题，通过检查
            if check_result.passed and check_result.total_issues == 0:
                debug("连续性检查通过")
                state.continuity_passed = True
                state.current_stage = AgentStage.CONTINUITY
                # 重置重试计数
                state.continuity_retry_count = 0
                return state

            # 4. 获取问题列表
            continuity_issues = check_result.issues
            state.continuity_issues = continuity_issues

            # 5. 分析问题来源
            issues_by_stage = self._analyze_continuity_issues(continuity_issues, continuity_context)

            # 更新连续性历史
            continuity_history = self._get_memory_list("continuity_issues_history", level=MemoryLevel.MEDIUM_TERM, default=[])
            for issue in continuity_issues:
                continuity_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "type": issue.type.value,
                    "severity": issue.severity.value,
                    "description": issue.description,
                    "source_stage": issue.source_stage
                })
            if len(continuity_history) > 100:
                continuity_history = continuity_history[-100:]
            self.memory.add("continuity_issues_history", continuity_history, level=MemoryLevel.MEDIUM_TERM,
                            metadata={"_serialized": True})

            warning(f"发现 {len(continuity_issues)} 个连续性问题，分布在: {[s.name for s in issues_by_stage.keys()]}, "
                    f"重试次数: {state.continuity_retry_count}/{state.max_continuity_retries}")

            # 6. 检查重试限制
            if state.continuity_retry_count < state.max_continuity_retries:
                # 7. 生成修复参数并触发重试
                for stage, issues in issues_by_stage.items():
                    repair_params = self._create_continuity_repair_params(issues, stage)
                    state.repair_params[stage] = repair_params
                    info(f"为阶段 {stage.value} 生成连续性修复参数，共{len(issues)}个问题")

                # 标记需要重试
                state.continuity_retry_count += 1
                state.needs_continuity_repair = True
                state.error_source = PipelineNode.CONTINUITY_CHECK

                info(f"连续性修复重试 ({state.continuity_retry_count}/{state.max_continuity_retries})")

                # 返回到需要修复的阶段
                return self._route_to_fix_stage(state, issues_by_stage)
            else:
                # 重试次数超限，需要人工干预
                error(f"连续性修复重试次数超限: {state.continuity_retry_count}/{state.max_continuity_retries}")
                state.needs_human_review = True
                state.error_source = PipelineNode.CONTINUITY_GUARDIAN
                state.current_stage = AgentStage.CONTINUITY

        except Exception as e:
            error(f"连续性守护节点异常: {e}")
            print_log_exception()
            error_msg = f"连续性检查失败: {str(e)}"
            error(error_msg)
            state.error = error_msg
            state.error_messages.append(error_msg)

            state.current_node = PipelineNode.CONTINUITY_CHECK
            state.current_stage = AgentStage.ERROR_HANDLER
            state.error_source = PipelineNode.CONTINUITY_CHECK

            state.audit_report = self._create_fallback_audit_report(state)

        return state

    def error_handler_node(self, graph_state: WorkflowState) -> WorkflowState:
        """
        错误处理节点 - 处理工作流中的错误和异常

        职责：
        1. 收集和分类错误信息
        2. 根据错误类型制定恢复策略
        3. 记录错误处理日志
        4. 决定是否可以恢复或需要人工干预

        设计原则：
        - 尽可能自动恢复
        - 提供详细的错误信息
        - 避免无限重试循环
        - 必要时请求人工干预
        """
        # 记录进入错误处理的时间
        error_time = time.time()

        # 确保有错误信息集合
        if not graph_state.error_messages:
            graph_state.error_messages = ["未知错误：进入错误处理节点但没有错误信息"]
            warning("错误处理节点没有接收到错误信息")

        # 获取最近的重要错误
        recent_errors = graph_state.error_messages[-5:] if len(graph_state.error_messages) > 5 else graph_state.error_messages

        # 错误分类和分析
        error_analysis = self._analyze_errors(recent_errors)

        info(f"进入错误处理节点，错误分析: {error_analysis}")

        # 根据错误类型采取相应措施
        recovery_action = self._determine_recovery_action(error_analysis, graph_state)

        # 记录错误处理详情
        error_details = {
            "timestamp": error_time,
            "recent_errors": recent_errors,
            "error_analysis": error_analysis,
            "recovery_action": recovery_action,
            "current_node": graph_state.current_node,
            "global_loops": getattr(graph_state, 'global_current_loops', 0),
            "retry_count": getattr(graph_state, 'total_retries', 0),
        }

        # 保存错误处理历史
        graph_state.error_handling_history.append(error_details)

        # 清理过长的错误历史（保留最近10次）
        if len(graph_state.error_handling_history) > 10:
            graph_state.error_handling_history = graph_state.error_handling_history[-10:]

        # 根据恢复行动采取具体措施
        self._execute_recovery_action(recovery_action, graph_state, error_analysis)

        # 更新节点状态
        graph_state.current_node = PipelineNode.ERROR_HANDLER
        graph_state.current_stage = AgentStage.ERROR_HANDLER

        # 记录错误处理完成
        processing_time = time.time() - error_time
        info(f"错误处理完成，采取行动: {recovery_action}，耗时: {processing_time:.2f}秒")

        return graph_state

    def generate_output_node(self, state: WorkflowState) -> WorkflowState:
        """
        结果生成节点
        功能：组装最终输出结果
        输入：所有阶段的结果
        输出：final_output (完整处理结果)
        """
        debug("进入生成输出节点")
        # 更新状态：开始输出
        self._update_task_progress(state.task_id, TaskStage.OUTPUT_START, 0)

        try:
            # 生成最终输出
            output_data = {
                "task_id": state.task_id,
                "script_analysis": state.parsed_script.model_dump() if state.parsed_script else None,
                "shot_sequence": state.shot_sequence.model_dump() if state.shot_sequence else None,
                "fragment_sequence": state.fragment_sequence.model_dump() if state.fragment_sequence else None,
                "instructions": state.instructions.model_dump() if state.instructions else None,
                "audit_report": state.audit_report.model_dump() if state.audit_report else None,
                "continuity_issues": state.continuity_issues,
                "created_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "status": "completed"
            }

            # 设置最终输出
            state.final_output = output_data
            # 更新阶段为 END
            state.current_stage = AgentStage.END
            state.current_node = PipelineNode.GENERATE_OUTPUT

            # 更新状态：生成中
            self._update_task_progress(state.task_id, TaskStage.OUTPUT_GENERATING, 50)

            # ========== 异步保存各类报告（不阻塞） ==========
            self.output_writer.save_all_reports(state)

            # 更新状态：完成
            self._update_task_progress(state.task_id, TaskStage.COMPLETE, 100)
            self._complete_stage(state.task_id, TaskStage.COMPLETE, {
                "status": "completed"
            })

            # ========== 任务完成，清理该任务的记忆 ==========
            self.memory.clear_script(state.script_id)

            # 清理所有智能体状态
            self.script_parser.clear_all_state()
            self.shot_segmenter.clear_all_state()
            self.video_splitter.clear_all_state()
            self.prompt_converter.clear_all_state()

            state.continuity_issues = []

            info(f"生成输出完成，数据大小: {len(str(output_data))} 字符，阶段更新为 END")

        except Exception as e:
            error(f"生成输出时出错: {str(e)}")
            print_log_exception()
            state.error_messages.append(f"生成输出失败: {str(e)}")
            state.current_stage = AgentStage.ERROR_HANDLER
            state.current_node = PipelineNode.GENERATE_OUTPUT
            state.error_source = PipelineNode.GENERATE_OUTPUT

        return state

    def human_intervention_node(self, state: WorkflowState) -> WorkflowState:
        """
        人工干预节点
        功能：暂停流程等待人工输入
        输入：需要人工决策的状态
        输出：人工处理后的状态
        """
        state.current_stage = AgentStage.HUMAN_INTERVENTION
        state.current_node = PipelineNode.HUMAN_INTERVENTION

        # 只有在需要人工审查时才执行干预
        if state.needs_human_review:
            info(f"进入人工干预节点，任务ID: {state.task_id}")

            # 执行人工干预（会更新 state.human_feedback）
            state = self.human_intervention(state)

            # 清理人工审查标志，避免重复进入
            state.needs_human_review = False

            # 记录干预结果
            decision = state.human_feedback.get("decision", "CONTINUE")
            info(f"人工干预完成，决策: {decision}")
        else:
            # 如果不需要人工审查但进入了此节点，使用默认继续
            warning("进入人工干预节点但不需要人工审查，使用默认继续")
            state.human_feedback = {
                "decision": "CONTINUE",
                "timeout": False,
                "auto_decision": True,
                "timestamp": time.time(),
                "raw_input": "AUTO_CONTINUE",
            }

        return state

    def loop_check_node(self, graph_state: WorkflowState) -> WorkflowState:
        """
        循环检查节点 - 检查节点循环次数并记录状态
        """
        # 增加全局循环计数
        graph_state.global_current_loops += 1

        # 获取当前节点
        current_node = graph_state.current_node or None

        # 增加当前节点的循环计数
        current_node_loops = graph_state.node_current_loops.get(current_node, 0) + 1
        graph_state.node_current_loops[current_node] = current_node_loops

        # 获取该节点的最大循环次数
        node_max_loops = graph_state.node_max_loops.get(current_node, 3)

        info(f"节点循环检查: 节点={current_node}, "
             f"节点循环={current_node_loops}/{node_max_loops}, "
             f"全局循环={graph_state.global_current_loops}/{graph_state.global_max_loops}")

        # 1. 检查节点循环限制
        if current_node_loops > node_max_loops:
            graph_state.node_loop_exceeded[current_node] = True
            error(f"节点 '{current_node}' 循环次数超过限制: {current_node_loops}/{node_max_loops}")

            graph_state.error_messages.append(
                f"节点 '{current_node}' 循环次数超过限制 ({current_node_loops}/{node_max_loops})"
            )

        # 2. 检查全局循环限制
        if graph_state.global_current_loops > graph_state.global_max_loops:
            graph_state.global_loop_exceeded = True
            error(f"全局循环次数超过限制: {graph_state.global_current_loops}/{graph_state.global_max_loops}")

            graph_state.error_messages.append(
                f"全局循环次数超过限制 ({graph_state.global_current_loops}/{graph_state.global_max_loops})"
            )

        # 3. 检查是否接近节点限制（警告）
        elif current_node_loops >= node_max_loops * 0.8:
            if not graph_state.loop_warning_issued:
                graph_state.loop_warning_issued = True
                warning(f"节点 '{current_node}' 循环次数接近限制: {current_node_loops}/{node_max_loops}")

        # 4. 记录节点进入详情（可选，便于调试）
        graph_state.node_loop_details.append({
            "node": current_node,
            "node_loop": current_node_loops,
            "global_loop": graph_state.global_current_loops,
            "timestamp": time.time()
        })

        # 更新节点追踪
        graph_state.last_node = current_node

        return graph_state

    # =============================================== 私有方法 ===============================================

    def _create_fallback_audit_report(self, state: WorkflowState) -> QualityAuditReport:
        """创建回退报告（当审查异常时）"""
        return QualityAuditReport(
            project_info={
                "title": getattr(state.instructions, 'project_info', {}).get("title", "未知项目"),
                "fragment_count": len(state.instructions.fragments) if state.instructions else 0,
                "total_duration": getattr(state.instructions, 'project_info', {}).get("total_duration", 0.0)
            },
            status=AuditStatus.FAILED,
            checks=[],
            violations=[],
            stats={"error": "audit_exception", "message": state.error},
            score=0.0
        )

    def _analyze_errors(self, error_list: List[str]) -> Dict[str, Any]:
        """分析错误列表，分类错误类型

        Args:
            error_list: 错误信息列表

        Returns:
            Dict: 错误分析结果
        """
        analysis = {
            "total_errors": len(error_list),
            "error_types": {},
            "most_common_error": "",
            "suggested_action": "unknown",
            "can_recover": True,
        }

        if not error_list:
            return analysis

        # 错误类型分类
        error_categories = {
            "network": ["network", "timeout", "connection", "socket", "http", "request"],
            "validation": ["validation", "invalid", "format", "type", "value"],
            "resource": ["memory", "disk", "cpu", "resource", "out of"],
            "configuration": ["configuration", "config", "parameter", "setting"],
            "business": ["业务", "逻辑", "规则", "requirement", "business"],
            "external": ["api", "external", "third", "service", "dependency"],
            "system": ["system", "os", "kernel", "fatal", "critical", "segmentation"],
            "data": ["data", "corrupt", "missing", "empty", "null"],
            "loop": ["循环", "loop", "exceeded", "超过限制"],
            "auth": ["401", "unauthorized", "authentication", "api-key", "apikey", "invalid api"],
            "unknown": ["unknown", "未定义", "不明"],
        }

        # 统计错误类型
        type_counts = {category: 0 for category in error_categories.keys()}

        for error_msg in error_list:
            error_msg_lower = error_msg.lower()
            matched = False

            for category, keywords in error_categories.items():
                for keyword in keywords:
                    if keyword in error_msg_lower:
                        type_counts[category] += 1
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                type_counts["unknown"] += 1

        # 找出最常见的错误类型
        if type_counts:
            most_common = max(type_counts.items(), key=lambda x: x[1])
            analysis["most_common_error"] = most_common[0]
            analysis["error_types"] = {k: v for k, v in type_counts.items() if v > 0}

        # 根据错误类型建议恢复行动
        if type_counts.get("system", 0) > 0 or type_counts.get("fatal", 0) > 0:
            analysis["suggested_action"] = "abort"
            analysis["can_recover"] = False
        elif type_counts.get("auth", 0) > 0:
            # 认证错误（如401）需要人工干预
            analysis["suggested_action"] = "human_intervention"
            analysis["can_recover"] = False
        elif type_counts.get("loop", 0) > 0:
            analysis["suggested_action"] = "human_intervention"
            analysis["can_recover"] = False
        elif type_counts.get("resource", 0) > 0:
            analysis["suggested_action"] = "retry_with_delay"
        elif type_counts.get("network", 0) > 0:
            analysis["suggested_action"] = "retry"
        elif type_counts.get("validation", 0) > 0 or type_counts.get("data", 0) > 0:
            analysis["suggested_action"] = "repair"
        else:
            analysis["suggested_action"] = "retry"

        return analysis

    def _determine_recovery_action(self, error_analysis: Dict[str, Any],
                                   state: WorkflowState) -> str:
        """根据错误分析和当前状态确定恢复行动

        Args:
            error_analysis: 错误分析结果
            state: 当前工作流状态

        Returns:
            str: 恢复行动类型
        """
        # 检查是否超过30分钟超时
        if hasattr(state, 'workflow_start_time'):
            elapsed_time = time.time() - state.workflow_start_time
            if elapsed_time > 1800:  # 30分钟 = 1800秒
                warning(f"工作流执行超时: {elapsed_time:.1f}秒，超过30分钟限制")
                return "abort"
        
        # 检查循环限制
        if getattr(state, 'global_loop_exceeded', False):
            return "abort"

        # 检查节点循环限制
        current_node = getattr(state, 'current_node', "")
        if hasattr(state, 'node_loop_exceeded') and current_node:
            if state.node_loop_exceeded.get(current_node, False):
                return "human_intervention"

        # 检查重试次数
        total_retries = getattr(state, 'total_retries', 0)
        max_allowed_retries = sum(getattr(state, 'stage_max_retries', {}).values())

        if total_retries >= max_allowed_retries:
            return "human_intervention"

        # 根据错误分析决定
        suggested_action = error_analysis.get("suggested_action", "retry")

        # 调整基于具体情况的行动
        if suggested_action == "retry":
            # 检查最近是否已经重试过多次
            if hasattr(state, 'error_handling_history'):
                recent_retries = sum(1 for h in state.error_handling_history[-3:]
                                     if h.get("recovery_action") == "retry")
                if recent_retries >= 2:
                    return "retry_with_delay"
            return "retry"

        elif suggested_action == "repair":
            return "repair_with_adjustment"

        elif suggested_action == "abort":
            return "abort"

        elif suggested_action == "human_intervention":
            return "human_intervention"

        else:
            return "retry_with_delay"

    def _execute_recovery_action(self, action: str, state: WorkflowState,
                                 error_analysis: Dict[str, Any]) -> None:
        """执行具体的恢复行动

        Args:
            action: 恢复行动类型
            state: 工作流状态（会修改）
            error_analysis: 错误分析结果
        """
        info(f"执行恢复行动: {action}")

        if action == "retry":
            state.error_messages = state.error_messages[-3:]
            info("准备重试：清理错误信息，保持原状态")

        elif action == "retry_with_delay":
            state.error_messages = state.error_messages[-3:]

            if not hasattr(state, 'recovery_flags'):
                state.recovery_flags = {}
            state.recovery_flags['need_delay'] = True
            state.recovery_flags['delay_seconds'] = 5

            warning("检测到连续错误，将在重试前延迟5秒")

        elif action == "repair":
            state.error_messages = state.error_messages[-3:]

            if not hasattr(state, 'recovery_flags'):
                state.recovery_flags = {}
            state.recovery_flags['need_repair'] = True
            state.recovery_flags['repair_type'] = error_analysis.get("most_common_error", "general")

            if error_analysis.get("most_common_error") == "validation":
                state.recovery_flags['adjust_validation'] = True
            elif error_analysis.get("most_common_error") == "configuration":
                state.recovery_flags['adjust_config'] = True

            info(f"准备修复：错误类型={error_analysis.get('most_common_error')}")

        elif action == "repair_with_adjustment":
            state.error_messages = state.error_messages[-3:]

            if not hasattr(state, 'recovery_flags'):
                state.recovery_flags = {}

            state.recovery_flags['need_repair'] = True
            state.recovery_flags['need_adjustment'] = True

            common_error = error_analysis.get("most_common_error", "")
            if common_error == "network":
                state.recovery_flags['adjust_timeout'] = True
                state.recovery_flags['timeout_multiplier'] = 1.5
            elif common_error == "resource":
                state.recovery_flags['reduce_load'] = True
                state.recovery_flags['batch_size'] = 0.5

            warning(f"准备修复并调整参数：{common_error}")

        elif action == "human_intervention":
            state.needs_human_review = True

            if not hasattr(state, 'human_intervention_info'):
                state.human_intervention_info = {}

            state.human_intervention_info['reason'] = "自动恢复失败，需要人工决策"
            state.human_intervention_info['error_summary'] = error_analysis
            state.human_intervention_info['suggested_actions'] = [
                "retry_with_adjusted_params",
                "skip_current_stage",
                "abort_process"
            ]

            warning("错误需要人工干预：自动恢复失败")

        elif action == "abort":
            state.error_messages.append("流程被中止：无法恢复的错误")

            if not hasattr(state, 'recovery_flags'):
                state.recovery_flags = {}
            state.recovery_flags['should_abort'] = True

            error("流程中止：无法恢复的错误")

        else:
            warning(f"未知恢复行动: {action}，使用默认重试")
            state.error_messages = state.error_messages[-3:]

    # ======================== 连续性节点 ========================

    def _check_continuity(self, context: Dict[str, Any]) -> ContinuityCheckResult:
        """
        执行连续性检查

        Args:
            context: 包含各阶段输出的上下文
                - parsed_script: 解析后的剧本
                - shot_sequence: 镜头序列
                - fragment_sequence: 片段序列
                - instructions: AI指令

        Returns:
            ContinuityCheckResult: 连续性检查结果对象
        """
        info("开始执行连续性检查...")

        # 执行连续性检查
        result = self.checker.check_all_continuity(context)

        # 记录检查结果摘要
        summary = result.get_summary()
        info(f"连续性检查完成: 通过={summary['passed']}, "
             f"问题总数={summary['total_issues']}, "
             f"严重={summary['critical']}, "
             f"主要={summary['major']}, "
             f"中度={summary['moderate']}, "
             f"轻微={summary['minor']}")

        # 记录每个问题的详细信息
        for issue in result.issues:
            warning(f"连续性问题 [{issue.severity.value}]: {issue.type.value} - {issue.description}")
            if issue.suggestion:
                debug(f"  修复建议: {issue.suggestion}")

        return result

    def _analyze_continuity_issues(self, issues: List[ContinuityIssue],
                                   context: Dict) -> Dict[PipelineNode, List[ContinuityIssue]]:
        """
        分析连续性问题的来源阶段

        Args:
            issues: ContinuityIssue 列表
            context: 上下文信息

        Returns:
            按阶段分组的问题字典
        """
        issues_by_stage = {
            PipelineNode.PARSE_SCRIPT: [],
            PipelineNode.SEGMENT_SHOT: [],
            PipelineNode.SPLIT_VIDEO: [],
            PipelineNode.CONVERT_PROMPT: [],
        }

        for issue in issues:
            # 使用 issue 自带的 source_stage
            if issue.source_stage:
                try:
                    stage = PipelineNode(issue.source_stage)
                    if stage in issues_by_stage:
                        issues_by_stage[stage].append(issue)
                        continue
                except ValueError:
                    pass

            # 根据问题类型推断来源
            source = self._infer_issue_source(issue.type)
            issues_by_stage[source].append(issue)

        # 返回非空的阶段
        return {k: v for k, v in issues_by_stage.items() if v}

    def _infer_issue_source(self, issue_type: ContinuityIssueType) -> PipelineNode:
        """根据问题类型推断来源阶段"""
        source_mapping = {
            ContinuityIssueType.CHARACTER_MISSING: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.SCENE_JUMP: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.SCENE_TOO_FREQUENT: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.ACTION_BREAK: PipelineNode.SEGMENT_SHOT,
            ContinuityIssueType.STYLE_INCONSISTENT: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.STYLE_SUDDEN_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.TIME_GAP: PipelineNode.SPLIT_VIDEO,
            ContinuityIssueType.TIME_OVERLAP: PipelineNode.SPLIT_VIDEO,
            ContinuityIssueType.PROP_CHANGE: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.PROP_DISAPPEAR: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.PROP_APPEAR: PipelineNode.PARSE_SCRIPT,
            ContinuityIssueType.LIGHTING_CHANGE: PipelineNode.CONVERT_PROMPT,
            ContinuityIssueType.COLOR_INCONSISTENT: PipelineNode.CONVERT_PROMPT,
        }
        return source_mapping.get(issue_type, PipelineNode.CONVERT_PROMPT)

    def _create_continuity_repair_params(self, issues: List, stage: PipelineNode) -> QualityRepairParams:
        """创建连续性修复参数"""
        return self.generator.generate_repair_params(issues, stage)

    def _can_retry_continuity(self, state: WorkflowState) -> bool:
        """检查连续性修复是否可重试"""
        max_retries = getattr(state, 'max_continuity_retries', 3)
        current_retries = getattr(state, 'continuity_retry_count', 0)
        return current_retries < max_retries

    def _route_to_fix_stage(self, state: WorkflowState, issues_by_stage: Dict) -> WorkflowState:
        """路由到需要修复的阶段"""
        stage_priority = [
            PipelineNode.PARSE_SCRIPT,
            PipelineNode.SEGMENT_SHOT,
            PipelineNode.SPLIT_VIDEO,
            PipelineNode.CONVERT_PROMPT,
        ]

        for stage in stage_priority:
            if stage in issues_by_stage:
                info(f"路由到阶段 {stage.value} 进行连续性修复")
                state.current_node = stage

                stage_mapping = {
                    PipelineNode.PARSE_SCRIPT: AgentStage.PARSER,
                    PipelineNode.SEGMENT_SHOT: AgentStage.SEGMENTER,
                    PipelineNode.SPLIT_VIDEO: AgentStage.SPLITTER,
                    PipelineNode.CONVERT_PROMPT: AgentStage.CONVERTER,
                }
                state.current_stage = stage_mapping.get(stage, AgentStage.CONVERTER)
                return state

        state.current_node = PipelineNode.CONVERT_PROMPT
        state.current_stage = AgentStage.CONVERTER
        return state

    # ============================= 记忆管理 =============================
    def _get_memory_dict(self, key: str, level: MemoryLevel, default: Dict = None) -> Dict:
        """
        从记忆获取字典类型数据（自动反序列化）

        Args:
            key: 记忆键
            level: 记忆级别
            default: 默认值

        Returns:
            字典类型数据
        """
        if default is None:
            default = {}

        value = self.memory.get(key, level=level, default=default)

        # 如果是字符串，尝试解析为 JSON
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except:
                return default

        # 确保返回字典
        if not isinstance(value, dict):
            return default

        return value

    def _get_memory_list(self, key: str, level: MemoryLevel, default: List = None) -> List:
        """
        从记忆获取列表类型数据（自动反序列化）

        Args:
            key: 记忆键
            level: 记忆级别
            default: 默认值

        Returns:
            列表类型数据
        """
        if default is None:
            default = []

        value = self.memory.get(key, level=level, default=default)

        # 如果是字符串，尝试解析为 JSON
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except:
                return default

        # 确保返回列表
        if not isinstance(value, list):
            # 如果不是列表，包装成列表
            return [value] if value else default

        return value

    def _load_common_patterns(self):
        """加载常见问题模式到缓存（全局知识，不依赖任务）"""
        if not hasattr(self, 'memory') or self.memory is None:
            return

        # 使用 _get_memory_list 获取长期记忆
        common_issues = self._get_memory_list("common_parse_issues", level=MemoryLevel.LONG_TERM, default=[])
        if common_issues:
            info(f"已加载 {len(common_issues)} 条常见问题模式")

        repair_patterns = self._get_memory_list("repair_success_patterns", level=MemoryLevel.LONG_TERM, default=[])
        if repair_patterns:
            info(f"已加载 {len(repair_patterns)} 条修复成功模式")

    # ============================= 节点任务状态 =============================

    def _update_task_status(self, task_id: str, status: TaskStatus):
        """更新任务状态"""
        try:
            if self.task_manager:
                self.task_manager.update_task_status(task_id, status)
        except Exception as e:
            warning(f"更新任务状态失败: {e}")

    def _update_task_progress(self, task_id: str, stage: TaskStage, progress: float = None, details: Dict = None):
        """更新任务进度"""
        try:
            if self.task_manager:
                self.task_manager.update_task_progress_detail(task_id, stage, progress, details)
        except Exception as e:
            warning(f"更新任务进度失败: {e}")
            print_log_exception()

    def _complete_stage(self, task_id: str, stage: TaskStage, result: Dict = None):
        """完成阶段"""
        try:
            if self.task_manager:
                self.task_manager.complete_stage(task_id, stage, result)
        except Exception as e:
            warning(f"完成阶段失败: {e}")
            print_log_exception()

    def _fail_stage(self, task_id: str, stage: TaskStage, error: str):
        """阶段失败"""
        try:
            if self.task_manager:
                self.task_manager.update_task_progress_detail(task_id, TaskStage.ERROR_HANDLING, 0, {"error": error})
                self.task_manager.fail_task(task_id, f"{stage.name}失败: {error}")
        except Exception as e:
            warning(f"记录阶段失败: {e}")
            print_log_exception()
