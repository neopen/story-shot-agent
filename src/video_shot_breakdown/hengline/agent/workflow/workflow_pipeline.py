"""
@FileName: multi_agent_pipeline.py
@Description: 多智能体协作流程，负责协调各个智能体完成端到端的分镜生成
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/10 - 至今
"""
from typing import Dict, Optional, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from video_shot_breakdown.hengline.agent.script_parser_agent import ScriptParserAgent
from video_shot_breakdown.logger import debug, error, info, warning
from video_shot_breakdown.utils.log_utils import print_log_exception
from .workflow_decision import PipelineDecision
from .workflow_models import AgentStage, PipelineNode, PipelineState
from .workflow_nodes import WorkflowNodes
from .workflow_output_fixer import WorkflowOutputFixer
from .workflow_states import WorkflowState
from ..prompt_converter_agent import PromptConverterAgent
from ..quality_auditor_agent import QualityAuditorAgent
from ..shot_segmenter_agent import ShotSegmenterAgent
from ..video_splitter_agent import VideoSplitterAgent
from ...hengline_config import HengLineConfig


class MultiAgentPipeline:
    """多智能体协作流程"""

    def __init__(self, task_id, config: Optional[HengLineConfig]):
        """
        初始化多智能体流程
        
        Args:
            task_id: 任务ID
            config: 用户配置（LLM）
        """
        self.task_id = task_id
        self.memory = MemorySaver()  # 状态记忆器
        self.config = config or HengLineConfig()
        self.llm = self.config.get_llm_by_config()
        self._init_agents()
        self.workflow = self._build_workflow()

    def _init_agents(self):
        """初始化各个智能体"""
        debug("初始化智能体组件")

        self.script_parser = ScriptParserAgent(llm=self.llm, config=self.config)
        self.shot_segmenter = ShotSegmenterAgent(llm=self.llm, config=self.config)
        self.video_splitter = VideoSplitterAgent(llm=self.llm, config=self.config)
        self.prompt_converter = PromptConverterAgent(llm=self.llm, config=self.config)
        self.quality_auditor = QualityAuditorAgent(llm=self.llm, config=self.config)

        # 初始化工作流节点集合
        self.workflow_nodes = WorkflowNodes(
            script_parser=self.script_parser,
            shot_segmenter=self.shot_segmenter,
            video_splitter=self.video_splitter,
            prompt_converter=self.prompt_converter,
            quality_auditor=self.quality_auditor,
            llm=self.llm
        )
        # 工作流决策函数
        self.decision_funcs = PipelineDecision()
        # 初始化修复器
        self.output_fixer = WorkflowOutputFixer()

    def _build_workflow(self):
        """初始化基于LangGraph的工作流"""
        debug("初始化LangGraph工作流")

        # 创建状态图
        workflow = StateGraph(WorkflowState)

        # ========== 定义所有工作流节点 ==========
        workflow.add_node(PipelineNode.PARSE_SCRIPT,
                          lambda graph_state: self.workflow_nodes.parse_script_node(graph_state))

        workflow.add_node(PipelineNode.SEGMENT_SHOT,
                          lambda graph_state: self.workflow_nodes.split_shots_node(graph_state))

        workflow.add_node(PipelineNode.SPLIT_VIDEO,
                          lambda graph_state: self.workflow_nodes.fragment_for_ai_node(graph_state))

        workflow.add_node(PipelineNode.CONVERT_PROMPT,
                          lambda graph_state: self.workflow_nodes.generate_prompts_node(graph_state))

        workflow.add_node(PipelineNode.AUDIT_QUALITY,
                          lambda graph_state: self.workflow_nodes.quality_audit_node(graph_state))

        workflow.add_node(PipelineNode.CONTINUITY_CHECK,
                          lambda graph_state: self.workflow_nodes.continuity_check_node(graph_state))

        workflow.add_node(PipelineNode.ERROR_HANDLER,
                          lambda graph_state: self.workflow_nodes.error_handler_node(graph_state))

        workflow.add_node(PipelineNode.GENERATE_OUTPUT,
                          lambda graph_state: self.workflow_nodes.generate_output_node(graph_state))

        workflow.add_node(PipelineNode.HUMAN_INTERVENTION,
                          lambda graph_state: self.workflow_nodes.human_intervention_node(graph_state))

        # 添加循环检查节点
        workflow.add_node(PipelineNode.LOOP_CHECK,
                          lambda graph_state: self.workflow_nodes.loop_check_node(graph_state))

        # ========== 定义工作流执行流程 ==========

        # 设置入口点
        workflow.set_entry_point(PipelineNode.PARSE_SCRIPT)

        workflow.add_conditional_edges(
            PipelineNode.PARSE_SCRIPT,
            lambda graph_state: self.decision_funcs.decide_after_parsing(graph_state),
            {
                # 解析成功，进入镜头拆分阶段
                PipelineState.SUCCESS: PipelineNode.SEGMENT_SHOT,

                # 解析需要人工干预
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,

                # 解析失败
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER
            }
        )

        # ========== 镜头拆分后的分支（保持原有逻辑，但能检测循环） ==========
        workflow.add_conditional_edges(
            PipelineNode.SEGMENT_SHOT,  # 当前节点：镜头拆分
            lambda graph_state: self.decision_funcs.decide_after_splitting(graph_state),  # 决策函数：拆分后判断
            {
                # 拆分成功，进入AI分段阶段（通过循环检查节点）
                PipelineState.SUCCESS: PipelineNode.LOOP_CHECK,  # 下一步：循环检查 -> AI分段

                # 拆分需要重试（如过长镜头过多、临时问题）
                PipelineState.RETRY: PipelineNode.SEGMENT_SHOT,  # 下一步：重试当前节点（镜头拆分）

                # 拆分需要修复/调整（如参数不合理）
                PipelineState.NEEDS_REPAIR: PipelineNode.SEGMENT_SHOT,  # 下一步：修复后重试当前节点

                # 拆分遇到严重错误，进入错误处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER  # 下一步：错误处理
            }
        )

        # ========== AI分段后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.SPLIT_VIDEO,  # 当前节点：AI分段（片段切割）
            lambda graph_state: self.decision_funcs.decide_after_fragmenting(graph_state),  # 决策函数：分段后判断
            {
                # 分段成功，进入提示词生成阶段（通过循环检查节点）
                PipelineState.SUCCESS: PipelineNode.LOOP_CHECK,  # 下一步：循环检查 -> 提示词生成

                # 分段需要修复/调整（如片段时长不合理）
                PipelineState.NEEDS_REPAIR: PipelineNode.SPLIT_VIDEO,  # 下一步：修复后重试当前节点（AI分段）

                # 分段需要重试（如临时问题）
                PipelineState.RETRY: PipelineNode.SPLIT_VIDEO,  # 下一步：重试当前节点

                # 分段遇到严重错误，进入错误处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER,  # 下一步：错误处理

                # 分段结果需要人工判断
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION  # 下一步：人工干预
            }
        )

        # ========== Prompt生成后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.CONVERT_PROMPT,  # 当前节点：提示词生成
            lambda graph_state: self.decision_funcs.decide_after_prompts(graph_state),  # 决策函数：生成后判断
            {
                # 生成成功，进入质量审查阶段（通过循环检查节点）
                PipelineState.SUCCESS: PipelineNode.LOOP_CHECK,  # 下一步：循环检查 -> 质量审查

                # 生成验证通过（有小问题），进入质量审查阶段
                PipelineState.VALID: PipelineNode.LOOP_CHECK,  # 下一步：循环检查 -> 质量审查

                # 生成需要修复/调整（如提示词质量不高、有空提示词）
                PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT,  # 下一步：修复提示词

                # 生成需要重试（如临时问题）
                PipelineState.RETRY: PipelineNode.CONVERT_PROMPT,  # 下一步：重试提示词生成

                # 生成遇到严重错误，进入错误处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER  # 下一步：错误处理
            }
        )

        # ========== 循环检查节点的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.LOOP_CHECK,
            lambda graph_state: self.decision_funcs.decide_after_loop_check(graph_state),
            {
                # 根据阶段决定下一个节点
                PipelineNode.SEGMENT_SHOT: PipelineNode.SEGMENT_SHOT,  # 继续到镜头拆分
                PipelineNode.SPLIT_VIDEO: PipelineNode.SPLIT_VIDEO,  # 继续到AI分段
                PipelineNode.CONVERT_PROMPT: PipelineNode.CONVERT_PROMPT,  # 继续到提示词生成
                PipelineNode.AUDIT_QUALITY: PipelineNode.AUDIT_QUALITY,  # 继续到质量审查

                # 特殊状态处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER,  # 循环超限，错误处理
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,  # 需要人工干预
            }
        )

        # ========== 质量审查后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.AUDIT_QUALITY,  # 当前节点：质量审查
            lambda graph_state: self.decision_funcs.decide_after_audit(graph_state),  # 决策函数：审查后判断
            {
                # 审查成功通过，进入连续性检查阶段
                PipelineState.SUCCESS: PipelineNode.CONTINUITY_CHECK,  # 下一步：连续性检查

                # 审查验证通过（有轻微问题），进入连续性检查阶段
                PipelineState.VALID: PipelineNode.CONTINUITY_CHECK,  # 下一步：连续性检查

                # 审查需要修复/调整（如提示词需要优化）
                PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT,  # 下一步：修复提示词

                # 审查需要重试（如临时问题）
                PipelineState.RETRY: PipelineNode.CONVERT_PROMPT,  # 下一步：重试提示词生成

                # 审查需要人工判断（如发现严重不确定性问题）
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,  # 下一步：人工干预

                # 审查失败（业务逻辑失败或系统错误），进入错误处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER,  # 下一步：错误处理
            }
        )

        # ========== 连续性检查后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.CONTINUITY_CHECK,  # 当前节点：连续性检查
            lambda graph_state: self.decision_funcs.decide_after_continuity(graph_state),  # 决策函数：检查后判断
            {
                # 检查成功通过，进入生成输出阶段
                PipelineState.SUCCESS: PipelineNode.GENERATE_OUTPUT,  # 下一步：生成输出

                # 检查验证通过（有可接受问题），进入生成输出阶段
                PipelineState.VALID: PipelineNode.GENERATE_OUTPUT,  # 下一步：生成输出

                # 检查需要修复/调整（如可修复的连续性问题）
                PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT,  # 下一步：修复提示词

                # 检查需要人工判断（如复杂的连续性问题）
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,  # 下一步：人工干预

                # 检查遇到严重错误，进入错误处理
                PipelineState.FAILED: PipelineNode.ERROR_HANDLER  # 下一步：错误处理
            }
        )

        # ========== 错误处理后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.ERROR_HANDLER,  # 当前节点：错误处理
            lambda graph_state: self.decision_funcs.decide_next_after_error(graph_state),  # 决策函数：处理后判断
            # {
            #     # 错误可恢复（如验证错误），根据错误来源决定重试节点
            #     PipelineState.VALID: self.decision_funcs.decide_retry_node_based_on_error_source,  # 根据错误来源决定
            #
            #     # 错误应该重试（如网络问题），根据错误来源决定重试节点
            #     PipelineState.RETRY: self.decision_funcs.decide_retry_node_based_on_error_source,  # 根据错误来源决定
            #
            #     # 错误需要修复/调整（如参数问题）
            #     PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT,  # 根据错误来源决定
            #
            #     # 错误需要人工处理（如多次重试失败）
            #     PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,
            #
            #     # 错误需要中止流程（如用户取消、超时）
            #     PipelineState.ABORT: END
            # }
        )

        # ========== 人工干预后的分支 ==========
        workflow.add_conditional_edges(
            PipelineNode.HUMAN_INTERVENTION,  # 当前节点：人工干预
            lambda graph_state: self.decision_funcs.decide_after_human(graph_state),  # 决策函数：干预后判断
            {
                # 人工决定继续流程
                PipelineState.SUCCESS: PipelineNode.GENERATE_OUTPUT,
                PipelineState.VALID: PipelineNode.GENERATE_OUTPUT,

                # 人工要求重试
                PipelineState.RETRY: PipelineNode.PARSE_SCRIPT,

                # 人工要求修复/调整
                PipelineState.NEEDS_REPAIR: PipelineNode.CONVERT_PROMPT,

                # 人工需要进一步干预
                PipelineState.NEEDS_HUMAN: PipelineNode.HUMAN_INTERVENTION,

                # 人工决定中止流程
                PipelineState.ABORT: END
            }
        )

        # ========== 结果生成后结束 ==========
        workflow.add_edge(PipelineNode.GENERATE_OUTPUT, END)  # 生成输出后直接结束

        return workflow.compile(checkpointer=self.memory)

        # ========== 公开接口 ==========

    async def run_process(self, raw_script: str, config: HengLineConfig) -> Dict:
        """执行完整的工作流"""
        # 计算全局循环限制：所有节点最大循环次数之和
        total_node_max_loops = config.max_total_loops
        default_global_max_loops = total_node_max_loops * 2  # 2倍安全系数

        initial_state = WorkflowState(
            raw_script=raw_script,
            user_config=config or {},
            task_id=self.task_id,
            current_stage=AgentStage.INIT,
            # 镜头及片段参数
            max_shot_duration=config.max_shot_duration,
            min_shot_duration=config.min_shot_duration,
            max_fragment_duration=config.max_fragment_duration,
            min_fragment_duration=config.min_fragment_duration,
            max_prompt_length=config.max_prompt_length,
            min_prompt_length=config.min_prompt_length,
            # 节点循环控制
            # node_max_loops=node_max_loops,
            # 阶段重试控制
            # stage_max_retries=stage_max_retries,

            # 全局循环控制
            global_max_loops=getattr(config, 'global_max_loops', default_global_max_loops),
            global_loop_exceeded=config.global_loop_exceeded,

            # 其他
            loop_warning_issued=config.loop_warning_issued,
            current_node=PipelineNode.PARSE_SCRIPT,
        )

        try:
            # 执行工作流
            debug(f"调用 workflow invoke()，任务ID: {self.task_id}")

            # final_state = await enhanced_workflow_invoke_async(
            #     self.workflow,
            #     initial_state
            # )

            final_result = await self._enhanced_workflow_execution(initial_state)
            info(f"工作流执行完成，最终状态类型: {type(final_result)}")

            # 处理返回结果
            success = final_result.get("success", False)
            data = final_result.get("data")
            info(f"工作流执行结果: success={success}, has_data={data is not None}")

            # 如果需要，可以添加额外的验证
            if success and data:
                self._validate_final_output(data)

            return final_result

        except Exception as e:
            error(f"执行工作流时出错: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "error": str(e),
                "data": None,
                "processing_stats": {
                    "error": "workflow_exception",
                    "exception_type": type(e).__name__,
                },
                "task_id": self.task_id,
                "workflow_status": "exception"
            }

    def _get_completed_stages(self, state) -> dict[str, Any]:
        """获取已完成的阶段列表和统计信息（支持字典和对象输入）"""
        try:
            # 如果是字典，直接使用
            if isinstance(state, dict):
                state_dict = state
            # 如果是对象，尝试转换为字典
            elif hasattr(state, 'dict'):
                state_dict = state.dict()
            elif hasattr(state, '__dict__'):
                state_dict = state.__dict__
            else:
                # 未知类型，返回空统计
                return {
                    "error": "unknown_state_type",
                    "completed_stages": [],
                    "stage_count": 0
                }

            stages = []

            # 检查各阶段是否完成
            parsed_script = state_dict.get('parsed_script')
            if parsed_script:
                stages.append("PARSER")

            shot_sequence = state_dict.get('shot_sequence')
            if shot_sequence:
                stages.append("SEGMENTER")

            fragment_sequence = state_dict.get('fragment_sequence')
            if fragment_sequence:
                stages.append("SPLITTER")

            instructions = state_dict.get('instructions')
            if instructions:
                stages.append("CONVERTER")

            audit_report = state_dict.get('audit_report')
            if audit_report:
                stages.append("AUDITOR")

            continuity_issues = state_dict.get('continuity_issues')
            if continuity_issues is not None:
                stages.append("CONTINUITY")

            # 获取当前节点和阶段
            current_node = state_dict.get('current_node')
            current_stage = state_dict.get('current_stage')

            # 转换为字符串（如果是枚举）
            if hasattr(current_node, 'value'):
                current_node = current_node.value
            if hasattr(current_stage, 'value'):
                current_stage = current_stage.value

            # 基本统计信息
            stats = {
                "completed_stages": stages,
                "stage_count": len(stages),
                "has_final_output": state_dict.get('final_output') is not None,
                "current_node": current_node,
                "current_stage": current_stage,
                "global_loops": state_dict.get('global_current_loops', 0),
                "global_max_loops": state_dict.get('global_max_loops', 0),
                "error_count": len(state_dict.get('error_messages', []))
            }

            # 添加审计信息
            last_audit_result = state_dict.get('last_audit_result')
            if last_audit_result:
                stats["audit"] = {
                    "score": last_audit_result.get('score', 0),
                    "status": last_audit_result.get('status'),
                    "passed_checks": last_audit_result.get('passed_checks', 0),
                    "total_checks": last_audit_result.get('total_checks', 0)
                }

            # 添加节点循环信息
            node_current_loops = state_dict.get('node_current_loops', {})
            if node_current_loops:
                # 转换为字符串键
                loops_summary = {}
                for node, count in node_current_loops.items():
                    if hasattr(node, 'value'):
                        loops_summary[node.value] = count
                    else:
                        loops_summary[str(node)] = count
                stats["node_loops"] = loops_summary

            return stats

        except Exception as e:
            error(f"获取完成阶段时出错: {str(e)}")
            return {
                "error": f"无法获取阶段信息: {str(e)}",
                "completed_stages": [],
                "stage_count": 0
            }

    async def _enhanced_workflow_execution(self, initial_state: WorkflowState) -> Dict[str, Any]:
        """
        增强的工作流执行方法

        这个方法封装了修复逻辑，确保返回正确的片段序列
        """
        try:
            debug("开始增强的工作流执行...")

            # 方法A：使用修复器实例（推荐）
            final_result = await self.output_fixer.enhanced_workflow_invoke(
                self.workflow,
                initial_state
            )

            # 方法B：如果修复器需要调整配置
            # config_dict = {"configurable": {"thread_id": f"process_{id(initial_state)}"}}
            # final_result = await self.output_fixer.enhanced_workflow_invoke_with_config(
            #     self.workflow,
            #     initial_state,
            #     config_dict
            # )

            # 验证修复结果
            if self._validate_fixed_result(final_result):
                info("工作流输出修复验证通过")
            else:
                warning("工作流输出修复验证有问题，但继续返回结果")

            return final_result

        except Exception as e:
            error(f"增强工作流执行失败: {str(e)}")

            # 尝试原始调用作为回退
            warning("尝试原始workflow调用作为回退...")
            try:
                raw_state = await self.workflow.ainvoke(
                    initial_state,
                    config={"configurable": {"thread_id": f"process_{id(initial_state)}"}}
                )

                # 转换为结果格式
                return self._convert_raw_state_to_result(raw_state, initial_state)

            except Exception as e2:
                error(f"原始调用也失败: {str(e2)}")
                raise e

    def _validate_fixed_result(self, result: Dict[str, Any]) -> bool:
        """验证修复后的结果"""
        try:
            if not result.get("success", False):
                warning("结果标记为不成功")
                return False

            data = result.get("data", {})
            if not isinstance(data, dict):
                warning(f"data字段不是字典: {type(data)}")
                return False

            # 检查是否有 instructions
            instructions = data.get("instructions")
            if not instructions:
                warning("结果中没有 instructions")
                return False

            # 检查片段数量
            fragments = instructions.fragments
            if not isinstance(fragments, list):
                warning(f"fragments不是列表: {type(fragments)}")
                return False

            # 检查是否有片段
            if len(fragments) == 0:
                warning("fragments列表为空")
                return False

            # 检查元数据
            metadata = instructions.metadata
            if metadata.get("fixed_by_output_fixer"):
                debug("结果已被修复器修复")

            # 检查片段ID是否唯一
            fragment_ids = [f.fragment_id for f in fragments]
            unique_ids = set(fragment_ids)
            if len(fragment_ids) != len(unique_ids):
                warning(f"片段ID不唯一: {len(fragment_ids)}个片段, {len(unique_ids)}个唯一ID")

            # 检查片段是否有提示词
            fragments_with_prompts = [f for f in fragments if f.prompt]
            if len(fragments_with_prompts) < len(fragments) * 0.8:  # 至少80%的片段应该有提示词
                warning(f"片段中提示词缺失较多: {len(fragments_with_prompts)}/{len(fragments)}个片段有提示词")

            # 检查音频提示词是否存在
            fragments_with_audio_prompts = [f for f in fragments if f.audio_prompt]
            if len(fragments_with_audio_prompts) < len(fragments) * 0.5:  # 至少50%的片段应该有音频提示词
                warning(f"片段中音频提示词缺失较多: {len(fragments_with_audio_prompts)}/{len(fragments)}个片段有音频提示词")

            info(f"验证通过: {len(fragments)}个片段")
            return True

        except Exception as e:
            error(f"验证结果时出错: {str(e)}")
            print_log_exception()
            return False

    def _validate_final_output(self, data: Dict[str, Any]):
        """验证最终输出"""
        try:
            if not isinstance(data, dict):
                return

            # 验证片段序列
            fragment_sequence = data.get("fragment_sequence")
            if fragment_sequence:
                fragments = fragment_sequence.get("fragments", [])
                shot_count = fragment_sequence.get("source_info", {}).get("shot_count", 0)

                info(f"最终输出验证: {shot_count}个镜头 -> {len(fragments)}个片段")

                # 如果片段数等于镜头数，可能有问题（除非真的没有分割）
                if len(fragments) == shot_count and shot_count > 0:
                    info(f"片段数({len(fragments)})等于镜头数({shot_count})，没有分割记录")

                    # 检查是否有AI分割标记
                    metadata = fragment_sequence.get("metadata", {})
                    ai_split_count = metadata.get("ai_split_count", 0)
                    # if ai_split_count == 0:
                    #     warning("没有AI分割记录，可能使用了错误的片段数据")
        except Exception as e:
            error(f"验证最终输出时出错: {str(e)}")

    def _convert_raw_state_to_result(self, raw_state: Any, initial_state: WorkflowState) -> Dict[str, Any]:
        """将原始状态转换为结果格式"""
        try:
            # 这是原来的转换逻辑
            if isinstance(raw_state, dict):
                state_dict = raw_state
            elif hasattr(raw_state, 'dict'):
                state_dict = raw_state.dict()
            elif hasattr(raw_state, '__dict__'):
                state_dict = raw_state.__dict__
            else:
                return {"success": False, "error": "无法解析状态"}

            # 提取信息
            success = False
            data = state_dict.get('final_output')

            if data is not None:
                success = True
            else:
                current_stage = state_dict.get('current_stage')
                current_node = state_dict.get('current_node')

                if current_stage == 'completed' or current_node == 'generate_output':
                    success = True
                    data = {
                        "task_id": state_dict.get('task_id', initial_state.task_id),
                        "instructions": state_dict.get('instructions'),
                        "fragment_sequence": state_dict.get('fragment_sequence'),
                        "audit_report": state_dict.get('audit_report'),
                        "status": "completed"
                    }

            # 获取处理统计
            processing_stats = self._get_completed_stages(state_dict)

            return {
                "success": success,
                "data": data,
                "errors": state_dict.get('error_messages', []),
                "processing_stats": processing_stats,
                "task_id": initial_state.task_id,
                "workflow_status": "completed" if success else "failed"
            }

        except Exception as e:
            error(f"转换原始状态时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "task_id": initial_state.task_id
            }