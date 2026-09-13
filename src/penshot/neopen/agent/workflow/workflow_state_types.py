"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: workflow_state_types.py
@Description: 分离的状态类型定义 - 执行状态与领域状态
@Author: NeoPen
@Time: 2026/4/29
"""

import time
import uuid
from dataclasses import field
from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, field_validator, model_validator

from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport, QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.agent.workflow.workflow_models import AgentStage, PipelineNode
from penshot.neopen.shot_config import ShotConfig


# ============================================================================
# 输入状态
# ============================================================================
class InputState(BaseModel):
    """工作流输入状态"""
    raw_script: str
    user_config: ShotConfig = None
    script_id: str = str(uuid.uuid4())
    task_id: str = str(uuid.uuid4())
    timeout: int = 600

    @field_validator('raw_script')
    def script_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('raw_script must not be empty')
        return v


# ============================================================================
# 领域状态 - 业务数据
# ============================================================================
class DomainState(BaseModel):
    """领域状态 - 包含所有业务数据"""
    
    # 剧本解析
    parsed_script: Optional[ParsedScript] = None
    parse_errors: List[str] = []
    parse_warnings: List[str] = []
    
    # 镜头序列
    shot_sequence: Optional[ShotSequence] = None
    current_shot_index: Optional[int] = None
    shot_errors: Dict[str, List] = {}
    
    # 片段序列
    fragment_sequence: Optional[FragmentSequence] = None
    fragment_quality_scores: Dict[str, float] = {}
    
    # 提示词指令
    instructions: Optional[AIVideoInstructions] = None
    prompt_templates_used: List[str] = []
    
    # 质量审查
    audit_report: Optional[QualityAuditReport] = None
    audit_failures: List[str] = field(default_factory=list)
    audit_warnings: List[str] = field(default_factory=list)
    audit_history: List[Dict[str, Any]] = []
    audit_executed: bool = False
    audit_timestamp: Optional[str] = None
    
    # 连续性管理
    continuity_state: Dict[str, Any] = {}
    continuity_anchors: Dict[str, Any] = {}
    continuity_issues: List[Any] = []
    continuity_passed: bool = False
    continuity_retry_count: int = 0
    max_continuity_retries: int = 3
    needs_continuity_repair: bool = False
    
    # 修复参数
    fix_summary: Dict[str, Any] = {}
    repair_params: Dict[PipelineNode, QualityRepairParams] = {}
    
    # 节点执行历史
    node_execution_history: List[Dict[str, Any]] = []

    def add_node_execution(self, node: PipelineNode):
        """添加节点执行记录"""
        self.node_execution_history.append({
            "node": node.value,
            "timestamp": datetime.now().isoformat(),
        })


# ============================================================================
# 执行状态 - 控制流程
# ============================================================================
class ExecutionState(BaseModel):
    """执行状态 - 包含所有流程控制数据"""
    
    # 当前位置
    current_stage: AgentStage = AgentStage.START
    current_node: Optional[PipelineNode] = None
    last_node: Optional[PipelineNode] = None
    
    # 节点循环控制
    node_max_loops: Dict[PipelineNode, int] = {
        PipelineNode.PARSE_SCRIPT: 3,
        PipelineNode.SEGMENT_SHOT: 5,
        PipelineNode.SPLIT_VIDEO: 5,
        PipelineNode.CONVERT_PROMPT: 5,
        PipelineNode.AUDIT_QUALITY: 3,
        PipelineNode.CONTINUITY_CHECK: 5,
        PipelineNode.ERROR_HANDLER: 5,
        PipelineNode.HUMAN_INTERVENTION: 1,
    }
    node_current_loops: Dict[PipelineNode, int] = {}
    node_loop_exceeded: Dict[PipelineNode, bool] = {}
    
    # 阶段重试控制
    stage_max_retries: Dict[PipelineNode, int] = {
        PipelineNode.PARSE_SCRIPT: 3,
        PipelineNode.SEGMENT_SHOT: 3,
        PipelineNode.SPLIT_VIDEO: 3,
        PipelineNode.CONVERT_PROMPT: 3,
        PipelineNode.AUDIT_QUALITY: 2,
        PipelineNode.CONTINUITY_CHECK: 2,
    }
    stage_current_retries: Dict[PipelineNode, int] = {}
    
    # 全局循环控制
    global_max_loops: int = 30
    global_current_loops: int = 0
    global_loop_exceeded: bool = False
    
    # 重试统计
    total_retries: int = 0
    node_loop_details: List[Dict[str, Any]] = []
    
    # 恢复标记
    recovery_flags: Dict[str, Any] = {}
    
    # 时间管理
    workflow_start_time: float = field(default_factory=lambda: time.time())
    loop_warning_issued: bool = False
    
    # 人工干预
    needs_human_review: bool = False
    human_feedback: Dict[str, Any] = {}
    human_intervention_info: Dict[str, Any] = {}

    # 中止控制
    should_abort: bool = False

    def increment_node_loop(self, node: PipelineNode) -> bool:
        """增加节点循环计数，返回是否超限"""
        current = self.node_current_loops.get(node, 0)
        self.node_current_loops[node] = current + 1
        self.global_current_loops += 1
        
        max_loops = self.node_max_loops.get(node, 3)
        if current + 1 >= max_loops:
            self.node_loop_exceeded[node] = True
            return True
        
        if self.global_current_loops >= self.global_max_loops:
            self.global_loop_exceeded = True
            return True
        
        return False

    def increment_stage_retry(self, node: PipelineNode):
        """增加阶段重试计数"""
        current = self.stage_current_retries.get(node, 0)
        self.stage_current_retries[node] = current + 1
        self.total_retries += 1

    def can_retry_stage(self, node: PipelineNode) -> bool:
        """检查阶段是否可以重试"""
        current = self.stage_current_retries.get(node, 0)
        max_retries = self.stage_max_retries.get(node, 3)
        return current < max_retries and not self.global_loop_exceeded


# ============================================================================
# 错误状态 - 统一错误管理
# ============================================================================
class ErrorState(BaseModel):
    """错误状态 - 统一的错误管理"""
    
    error: Optional[str] = None
    error_source: Optional[PipelineNode] = None
    error_messages: List[str] = []
    error_handling_history: List[Dict[str, Any]] = []
    last_error_timestamp: Optional[str] = None

    def add_error(self, message: str, source: Optional[PipelineNode] = None):
        """添加错误信息"""
        self.error_messages.append(message)
        self.error = message
        if source:
            self.error_source = source
        self.last_error_timestamp = datetime.now().isoformat()
        
        self.error_handling_history.append({
            "message": message,
            "source": source.value if source else None,
            "timestamp": self.last_error_timestamp,
            "retry_count": len([e for e in self.error_handling_history if e.get("source") == (source.value if source else None)])
        })

    def clear_errors(self):
        """清除所有错误"""
        self.error = None
        self.error_source = None
        self.error_messages = []

    def has_errors(self) -> bool:
        """检查是否有错误"""
        return len(self.error_messages) > 0


# ============================================================================
# 配置状态 - 运行时配置
# ============================================================================
class ConfigState(BaseModel):
    """配置状态 - 运行时配置参数"""
    
    # 镜头参数
    max_shot_duration: float = 30.0
    min_shot_duration: float = 1.0
    
    # 片段参数
    max_fragment_duration: float = 5.0
    min_fragment_duration: float = 1.0
    
    # 提示词参数
    max_prompt_length: int = 200
    min_prompt_length: int = 10

    @field_validator('max_fragment_duration')
    def fragment_duration_valid(cls, v, values):
        min_dur = values.data.get('min_fragment_duration', 1.0)
        if v <= min_dur:
            raise ValueError('max_fragment_duration must be greater than min_fragment_duration')
        return v

    @field_validator('max_prompt_length')
    def prompt_length_valid(cls, v, values):
        min_len = values.data.get('min_prompt_length', 10)
        if v <= min_len:
            raise ValueError('max_prompt_length must be greater than min_prompt_length')
        return v


# ============================================================================
# 输出状态 - 最终结果
# ============================================================================
class OutputState(BaseModel):
    """输出状态 - 工作流输出结果"""
    
    final_output: Optional[Dict[str, Any]] = None
    workflow_status: str = "running"

    def set_completed(self, data: Dict[str, Any]):
        """标记任务完成"""
        self.final_output = data
        self.workflow_status = "completed"

    def set_failed(self, error: str):
        """标记任务失败"""
        self.final_output = {"error": error}
        self.workflow_status = "failed"


# ============================================================================
# 组合状态 - 完整的工作流状态
# ============================================================================
class WorkflowState(BaseModel):
    """
    完整的工作流状态 - 使用组合而非继承
    """
    
    # 输入
    input: InputState
    
    # 领域数据
    domain: DomainState = field(default_factory=DomainState)
    
    # 执行控制
    execution: ExecutionState = field(default_factory=ExecutionState)
    
    # 错误管理
    errors: ErrorState = field(default_factory=ErrorState)
    
    # 配置
    config: ConfigState = field(default_factory=ConfigState)
    
    # 输出
    output: OutputState = field(default_factory=OutputState)

    @model_validator(mode='after')
    def validate_consistency(self):
        """验证状态一致性"""
        # 验证片段时长配置
        if self.config.max_fragment_duration <= self.config.min_fragment_duration:
            raise ValueError('max_fragment_duration must be greater than min_fragment_duration')
        # 验证提示词长度配置
        if self.config.max_prompt_length <= self.config.min_prompt_length:
            raise ValueError('max_prompt_length must be greater than min_prompt_length')
        return self

    @classmethod
    def from_raw_script(cls, raw_script: str, **kwargs) -> 'WorkflowState':
        """从原始剧本创建工作流状态"""
        return cls(
            input=InputState(raw_script=raw_script, **kwargs)
        )

    def model_dump(self, *args, exclude_unset=True, **kwargs):
        """优化序列化，默认排除未设置的字段"""
        return super().model_dump(*args, exclude_unset=exclude_unset, **kwargs)

    def model_dump_json(self, *args, exclude_unset=True, **kwargs):
        """优化JSON序列化，默认排除未设置的字段"""
        return super().model_dump_json(*args, exclude_unset=exclude_unset, **kwargs)

    # 向后兼容属性
    @property
    def raw_script(self):
        return self.input.raw_script
    
    @property
    def task_id(self):
        return self.input.task_id
    
    @property
    def script_id(self):
        return self.input.script_id
    
    @property
    def current_stage(self):
        return self.execution.current_stage
    
    @current_stage.setter
    def current_stage(self, value):
        self.execution.current_stage = value
    
    @property
    def current_node(self):
        return self.execution.current_node
    
    @current_node.setter
    def current_node(self, value):
        self.execution.current_node = value

    def add_error(self, message: str, source: Optional[PipelineNode] = None):
        """向后兼容的错误添加方法"""
        self.errors.add_error(message, source)

    def add_node_execution(self, node: PipelineNode):
        """向后兼容的节点执行记录方法"""
        self.domain.add_node_execution(node)