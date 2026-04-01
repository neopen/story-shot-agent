"""
@FileName: workflow_states.py
@Description: 分镜生成工作流的状态定义
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
import uuid
from dataclasses import field
from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel

from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport, QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.agent.workflow.workflow_models import AgentStage, PipelineNode
from penshot.neopen.shot_config import ShotConfig


class InputState(BaseModel):
    """工作流输入状态"""
    raw_script: str  # 原始剧本文本
    user_config: ShotConfig = {}  # 用户配置（模型选择、风格偏好等）
    script_id: str = str(uuid.uuid4())  # 剧本ID
    task_id: str = str(uuid.uuid4())  # 唯一标识符


class ScriptParsingState(BaseModel):
    """剧本解析相关状态"""
    parsed_script: ParsedScript = None  # 结构化剧本
    parse_errors: List[str] = []  # 解析错误信息
    parse_warnings: List[str] = []  # 解析警告信息


class ShotGeneratorState(BaseModel):
    """分镜生成相关状态"""
    shot_sequence: ShotSequence = None  # 镜头序列
    current_shot_index: int = None  # 当前处理的镜头索引
    shot_errors: Dict[str, List] = None  # 按镜头存储的错误


class VideoSegmenterState(BaseModel):
    """视频拆分相关状态"""
    fragment_sequence: FragmentSequence = None  # AI视频片段序列
    fragment_quality_scores: Dict[str, float] = None  # 片段质量评分


class PromptConverterState(BaseModel):
    """指令转换相关状态"""
    instructions: AIVideoInstructions = None  # AI生成指令
    prompt_templates_used: List[str] = None  # 使用的Prompt模板


class QualityAuditorState(BaseModel):
    """质量审查相关状态"""
    audit_report: Optional[QualityAuditReport] = None  # 质量审查报告
    audit_failures: List[str] = field(default_factory=list)  # 审查失败项
    audit_warnings: List[str] = field(default_factory=list)  # 审查警告项
    audit_history: List[Dict[str, Any]] = []  # 质量审查历史记录
    audit_executed: bool = False  #
    audit_timestamp: Optional[str] = None


class OutputState(BaseModel):
    """工作流输出状态"""
    final_output: Optional[Dict] = None  # 最终输出结果
    # execution_plan: Optional[Dict] = None  # 执行计划说明
    error: Optional[str] = None  # 错误信息
    error_source: Optional[PipelineNode] = None  # 错误来源节点


class NodeLoopState(BaseModel):
    """ 节点循环状态追踪 """
    # 每个节点的最大循环次数配置
    node_max_loops: Dict[PipelineNode, int] = {
        PipelineNode.PARSE_SCRIPT: 3,  # 剧本解析最多循环3次
        PipelineNode.SEGMENT_SHOT: 5,  # 镜头拆分最多循环5次（容易出现重试）
        PipelineNode.SPLIT_VIDEO: 5,  # AI分段最多循环5次（容易出现重试）
        PipelineNode.CONVERT_PROMPT: 3,  # 提示词生成最多循环3次
        PipelineNode.AUDIT_QUALITY: 3,  # 质量审查最多循环3次
        PipelineNode.CONTINUITY_CHECK: 3,  # 连续性检查最多循环3次
        PipelineNode.ERROR_HANDLER: 5,  # 错误处理最多循环5次
        PipelineNode.HUMAN_INTERVENTION: 1,  # 人工干预最多循环1次（避免无限等待）
    }
    # 每个节点的当前循环次数
    node_current_loops: Dict[PipelineNode, int] = {}
    # 节点循环超限标记
    node_loop_exceeded: Dict[PipelineNode, bool] = {}

    # ==== 阶段重试控制（每个阶段独立） ====
    stage_max_retries: Dict[PipelineNode, int] = {
        PipelineNode.PARSE_SCRIPT: 2,
        PipelineNode.SEGMENT_SHOT: 3,
        PipelineNode.SPLIT_VIDEO: 3,
        PipelineNode.CONVERT_PROMPT: 2,
        PipelineNode.AUDIT_QUALITY: 1,
        PipelineNode.CONTINUITY_CHECK: 1,
    }
    # 每个阶段的当前重试次数
    stage_current_retries: Dict[PipelineNode, int] = {}

    # ==== 全局循环控制（作为后备） ====
    global_max_loops: int = 30  # 全局最大循环次数
    global_current_loops: int = 0  # 全局当前循环次数
    global_loop_exceeded: bool = False  # 全局循环超限标记

    # ==== 其他字段 ====
    loop_warning_issued: bool = False  # 是否已发出循环警告
    last_node: Optional[PipelineNode] = None  # 上一个节点
    current_node: Optional[PipelineNode] = None  # 当前节点
    total_retries: int = 0  # 全局重试统计
    node_loop_details: list = []  # 每个节点的循环详情日志
    recovery_flags: Dict[str, Any] = {}  # 每个节点的恢复标记


class WorkflowState(InputState, ScriptParsingState, ShotGeneratorState, NodeLoopState,
                    VideoSegmenterState, PromptConverterState, QualityAuditorState, OutputState):
    """
    完整的分镜生成工作流状态
    通过继承多个特定功能的状态类来组合，实现高内聚低耦合
    """
    current_stage: AgentStage = AgentStage.START  # 当前处理阶段
    should_abort: bool = False  # 是否中止流程
    error_messages: List[str] = []  # 累计错误信息
    error_handling_history: List[Dict] = []  # 错误处理历史记录

    # === 连续性管理 ===
    continuity_state: Optional[Dict] = {}  # 当前连续性状态
    continuity_anchors: Optional[Dict] = {}  # 连续性锚点映射
    continuity_issues: List = []  # 连续性问题列表
    continuity_passed: bool = False
    continuity_retry_count: int = 0
    max_continuity_retries: int = 3
    needs_continuity_repair: bool = False

    # === 镜头拆分配置 ===
    max_shot_duration: float = 30.0  # 镜头允许的时长范围
    min_shot_duration: float = 1.0
    max_fragment_duration: float = 5.0  # 每个分镜的最大持续时间（秒）
    min_fragment_duration: float = 1.0  # 最小片段时长
    max_prompt_length: int = 200  # 最大提示词长度（字符数）
    min_prompt_length: int = 10

    # 人工决策
    needs_human_review: bool = False
    human_feedback: Dict[str, Any] = {}

    # 修复
    fix_summary: Optional[Dict[str, Any]] = {}
    repair_params: Dict[PipelineNode, QualityRepairParams] = {}  # 按来源的修复参数

    # 节点执行历史
    node_execution_history: Optional[List[Dict]] = []

    def add_node_execution(self, node: PipelineNode):
        """添加节点执行记录"""
        self.node_execution_history.append({
            "node": node.value,
            "timestamp": datetime.now().isoformat(),
            "stage": self.current_stage.value if self.current_stage else None
        })
