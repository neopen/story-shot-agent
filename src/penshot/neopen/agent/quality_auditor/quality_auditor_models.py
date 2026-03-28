"""
@FileName: quality_auditor_models.py
@Description: 质量审核模型
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/19 22:58
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from typing import List, Optional, Any, Dict, Literal

from pydantic import Field, BaseModel

from penshot.neopen.agent.workflow.workflow_models import PipelineNode


@unique
class SeverityLevel(str, Enum):
    """违规严重程度"""
    INFO = "info"  # 信息级别，不影响执行
    WARNING = "warning"  # 警告级别，建议修复
    MODERATE = "moderate"  # 中度问题，需要调整
    MAJOR = "major"  # 主要问题，需要重新处理
    CRITICAL = "critical"  # 严重问题，需要人工干预
    ERROR = "error"  # 错误级别，无法继续


@unique
class AuditStatus(str, Enum):
    """质量审查状态枚举"""
    PASSED = "passed"  # 完全通过
    MINOR_ISSUES = "minor_issues"  # 轻微问题（警告级别）
    MODERATE_ISSUES = "moderate_issues"  # 中度问题（需要调整）
    MAJOR_ISSUES = "major_issues"  # 主要问题（需要重新处理）
    CRITICAL_ISSUES = "critical_issues"  # 严重问题（需要人工干预）
    FAILED = "failed"  # 完全失败
    NEEDS_HUMAN = "needs_human"  # 需要人工决策

    NEEDS_REVIEW = "needs_review"  # 需要审查
    WARNING = "warning"  # 有警告


class IssueType(str, Enum):
    """问题类型枚举"""
    SCENE = "scene"                 # 场景问题
    CHARACTER = "character"         # 角色问题
    WEATHER = "weather"             # 气候问题
    DIALOGUE = "dialogue"           # 对话问题
    ACTION = "action"               # 动作问题
    DURATION = "duration"           # 时长问题
    PROMPT = "prompt"               # 提示词问题
    AUDIO = "audio"                 # 音频问题
    STYLE = "style"                 # 风格问题
    MODEL = "model"                 # 模型问题
    FRAGMENT = "fragment"           # 片段问题
    CONTINUITY = "continuity"       # 连续性问题
    TRUNCATION = "truncation"       # 截断问题
    FORMAT = "format"               # 格式问题
    COMPLETENESS = "completeness"   # 完整性问题
    OTHER = "other"                 # 其他问题


@dataclass
class Rule:
    """规则定义"""
    code: str
    description: str
    issue_type: 'IssueType'


class RuleType(str, Enum):
    """规则类型枚举 - 统一管理所有审查规则"""

    # ==================== LLM审查规则 ====================
    LLM_COHERENCE = Rule("llm_coherence", "LLM连贯性检查", IssueType.CONTINUITY)

    # ==================== 剧本解析规则 (Parse Agent) ====================
    # 场景相关
    SCENE_MISSING = Rule("scene_missing", "场景缺失", IssueType.SCENE)
    SCENE_INSUFFICIENT = Rule("scene_insufficient", "场景数量不足", IssueType.SCENE)
    SCENE_DESC_MISSING = Rule("scene_desc_missing", "场景描述缺失", IssueType.SCENE)

    # 角色相关
    CHARACTER_MISSING = Rule("character_missing", "角色缺失", IssueType.CHARACTER)
    CHARACTER_INCONSISTENT = Rule("character_inconsistent", "角色不一致", IssueType.CHARACTER)
    CHARACTER_DESC_MISSING = Rule("character_desc_missing", "角色描述缺失", IssueType.CHARACTER)
    CHARACTER_DUPLICATE = Rule("character_duplicate", "角色重复", IssueType.CHARACTER)

    # 对话相关
    DIALOGUE_MISSING = Rule("dialogue_missing", "对话缺失", IssueType.DIALOGUE)
    DIALOGUE_CHARACTER_MISSING = Rule("dialogue_character_missing", "对话缺少角色", IssueType.DIALOGUE)
    DIALOGUE_EMOTION_MISSING = Rule("dialogue_emotion_missing", "对话情感标注缺失", IssueType.DIALOGUE)

    # 动作相关
    ACTION_INSUFFICIENT = Rule("action_insufficient", "动作提取不足", IssueType.ACTION)
    ACTION_DESC_MISSING = Rule("action_desc_missing", "动作描述缺失", IssueType.ACTION)
    ACTION_INTENSITY_DEFAULT = Rule("action_intensity_default", "动作强度使用默认值", IssueType.ACTION)

    # 元素相关
    ELEMENT_DURATION_TOO_SHORT = Rule("element_duration_too_short", "元素时长过短", IssueType.DURATION)
    ELEMENT_DURATION_TOO_LONG = Rule("element_duration_too_long", "元素时长过长", IssueType.DURATION)
    ELEMENT_SEQUENCE_WRONG = Rule("element_sequence_wrong", "元素顺序错误", IssueType.SCENE)
    ELEMENT_ID_FORMAT = Rule("element_id_format", "元素ID格式不规范", IssueType.FORMAT)

    # 情感相关
    EMOTION_MISMATCH = Rule("emotion_mismatch", "情感标注不匹配", IssueType.CHARACTER)
    EMOTION_INCONSISTENT = Rule("emotion_inconsistent", "情感前后不一致", IssueType.CONTINUITY)

    # ==================== 分镜生成规则 (Shot Segmenter) ====================
    # 镜头基本规则
    SHOT_MISSING = Rule("shot_missing", "未能生成任何镜头", IssueType.FRAGMENT)
    SHOT_INSUFFICIENT = Rule("shot_insufficient", "镜头数量不足", IssueType.FRAGMENT)
    SHOT_EXCESSIVE = Rule("shot_excessive", "镜头数量过多", IssueType.FRAGMENT)

    # 镜头时长
    SHOT_DURATION_TOO_SHORT = Rule("shot_duration_too_short", "镜头时长过短", IssueType.DURATION)
    SHOT_DURATION_TOO_LONG = Rule("shot_duration_too_long", "镜头时长过长", IssueType.DURATION)
    SHOT_DURATION_UNBALANCED = Rule("shot_duration_unbalanced", "镜头时长分布不均", IssueType.DURATION)

    # 镜头描述
    SHOT_DESCRIPTION_MISSING = Rule("shot_description_missing", "镜头描述缺失", IssueType.PROMPT)
    SHOT_DESCRIPTION_TOO_SHORT = Rule("shot_description_too_short", "镜头描述过短", IssueType.PROMPT)
    SHOT_DESCRIPTION_VAGUE = Rule("shot_description_vague", "镜头描述模糊", IssueType.PROMPT)

    # 镜头类型
    SHOT_TYPE_UNIFORM = Rule("shot_type_uniform", "镜头类型单一", IssueType.STYLE)
    SHOT_TYPE_INVALID = Rule("shot_type_invalid", "无效的镜头类型", IssueType.STYLE)
    SHOT_REPETITIVE = Rule("shot_repetitive", "镜头类型重复连续", IssueType.CONTINUITY)
    SHOT_TYPE_MISMATCH = Rule("shot_type_mismatch", "镜头类型与内容不匹配", IssueType.STYLE)

    # 角色相关
    CHARACTER_NOT_IN_SHOTS = Rule("character_not_in_shots", "角色未在镜头中出现", IssueType.CHARACTER)
    SHOT_MAIN_CHARACTER_MISSING = Rule("shot_main_character_missing", "镜头缺少主要角色标识", IssueType.CHARACTER)

    # 镜头连续性
    SHOT_TRANSITION_ABRUPT = Rule("shot_transition_abrupt", "镜头切换过于突兀", IssueType.CONTINUITY)
    SHOT_ACTION_BREAK = Rule("shot_action_break", "动作连续性中断", IssueType.CONTINUITY)

    # ==================== 视频分割规则 (Video Splitter) ====================
    # 片段基本规则
    FRAGMENT_MISSING = Rule("fragment_missing", "未生成视频片段", IssueType.FRAGMENT)
    FRAGMENT_INSUFFICIENT = Rule("fragment_insufficient", "片段数量不足", IssueType.FRAGMENT)
    FRAGMENT_EXCESSIVE = Rule("fragment_excessive", "片段数量过多", IssueType.FRAGMENT)

    # 片段时长
    FRAGMENT_DURATION_TOO_SHORT = Rule("fragment_duration_too_short", "片段时长过短", IssueType.DURATION)
    FRAGMENT_DURATION_TOO_LONG = Rule("fragment_duration_too_long", "片段时长过长", IssueType.DURATION)
    FRAGMENT_DURATION_LIMIT = Rule("fragment_duration_limit", "片段时长超出限制", IssueType.DURATION)

    # 片段描述
    FRAGMENT_DESCRIPTION_MISSING = Rule("fragment_description_missing", "片段描述缺失", IssueType.PROMPT)
    FRAGMENT_DESCRIPTION_TOO_SHORT = Rule("fragment_description_too_short", "片段描述过短", IssueType.PROMPT)

    # 片段连续性
    FRAGMENT_TIME_GAP = Rule("fragment_time_gap", "片段间存在时间间隔", IssueType.CONTINUITY)
    FRAGMENT_OVERLAP = Rule("fragment_overlap", "片段间存在时间重叠", IssueType.CONTINUITY)
    FRAGMENT_NO_CONTINUITY = Rule("fragment_no_continuity", "片段缺少连续性注释", IssueType.CONTINUITY)
    FRAGMENT_CONTINUITY_BROKEN = Rule("fragment_continuity_broken", "片段连续性被破坏", IssueType.CONTINUITY)

    # 元素关联
    FRAGMENT_NO_ELEMENTS = Rule("fragment_no_elements", "片段未关联剧本元素", IssueType.FRAGMENT)
    FRAGMENT_ELEMENT_MISMATCH = Rule("fragment_element_mismatch", "片段元素关联错误", IssueType.FRAGMENT)

    # ==================== 提示词转换规则 (Prompt Converter) ====================
    # 提示词基本规则
    PROMPT_MISSING = Rule("prompt_missing", "未生成任何提示词", IssueType.PROMPT)
    PROMPT_EMPTY = Rule("prompt_empty", "提示词为空", IssueType.PROMPT)
    PROMPT_TOO_LONG = Rule("prompt_too_long", "提示词过长", IssueType.PROMPT)
    PROMPT_TOO_SHORT = Rule("prompt_too_short", "提示词过短", IssueType.PROMPT)
    PROMPT_TRUNCATED = Rule("prompt_truncated", "提示词被截断", IssueType.TRUNCATION)
    PROMPT_INCOMPLETE = Rule("prompt_incomplete", "提示词不完整", IssueType.TRUNCATION)

    # 提示词内容
    PROMPT_LOW_QUALITY = Rule("prompt_low_quality", "提示词质量较低", IssueType.PROMPT)
    PROMPT_NO_VISUAL = Rule("prompt_no_visual", "提示词缺少视觉描述", IssueType.PROMPT)
    PROMPT_NO_ACTION = Rule("prompt_no_action", "提示词缺少动作描述", IssueType.ACTION)
    PROMPT_NO_EMOTION = Rule("prompt_no_emotion", "提示词缺少情感描述", IssueType.CHARACTER)

    # 风格相关
    STYLE_INCONSISTENT = Rule("style_inconsistent", "风格不一致", IssueType.STYLE)
    STYLE_INVALID = Rule("style_invalid", "无效的风格", IssueType.STYLE)
    NEGATIVE_PROMPT_MISSING = Rule("negative_prompt_missing", "缺少负面提示词", IssueType.PROMPT)
    NEGATIVE_PROMPT_INSUFFICIENT = Rule("negative_prompt_insufficient", "负面提示词不足", IssueType.PROMPT)

    # 音频相关
    AUDIO_PROMPT_MISSING = Rule("audio_prompt_missing", "缺少音频提示词", IssueType.AUDIO)
    AUDIO_PROMPT_TOO_SHORT = Rule("audio_prompt_too_short", "音频提示词过短", IssueType.AUDIO)
    AUDIO_DURATION_MISMATCH = Rule("audio_duration_mismatch", "音频时长与视频时长不匹配", IssueType.DURATION)
    AUDIO_VOICE_TYPE_INVALID = Rule("audio_voice_type_invalid", "无效的人声类型", IssueType.AUDIO)
    AUDIO_EMOTION_MISMATCH = Rule("audio_emotion_mismatch", "音频情感与画面不匹配", IssueType.AUDIO)

    # 模型相关
    MODEL_UNSUPPORTED = Rule("model_unsupported", "不支持的模型", IssueType.MODEL)
    MODEL_DEPRECATED = Rule("model_deprecated", "模型已弃用", IssueType.MODEL)

    # ==================== 通用规则 ====================
    # 格式规范
    ID_FORMAT_INVALID = Rule("id_format_invalid", "ID格式不规范", IssueType.FORMAT)
    TIMESTAMP_INVALID = Rule("timestamp_invalid", "时间戳无效", IssueType.FORMAT)
    DATA_TYPE_ERROR = Rule("data_type_error", "数据类型错误", IssueType.FORMAT)

    # 一致性检查
    CONSISTENCY_GENERAL = Rule("consistency_general", "一般一致性问题", IssueType.CONTINUITY)
    COLOR_CONSISTENCY = Rule("color_consistency", "色彩风格不一致", IssueType.CONTINUITY)
    LIGHTING_CONSISTENCY = Rule("lighting_consistency", "光照风格不一致", IssueType.CONTINUITY)

    # 完整性检查
    COMPLETENESS_GENERAL = Rule("completeness_general", "内容不完整", IssueType.COMPLETENESS)
    METADATA_MISSING = Rule("metadata_missing", "元数据缺失", IssueType.COMPLETENESS)

    def __init__(self, rule: Rule):
        self._code = rule.code
        self._description = rule.description
        self._issue_type = rule.issue_type

    @property
    def code(self) -> str:
        """获取规则代码"""
        return self._code

    @property
    def description(self) -> str:
        """获取规则描述"""
        return self._description

    @property
    def issue_type(self) -> 'IssueType':
        """获取问题类型"""
        return self._issue_type

    @classmethod
    def from_code(cls, code: str) -> Optional['RuleType']:
        """根据规则代码获取规则"""
        for rule in cls:
            if rule.code == code:
                return rule
        return None

    @classmethod
    def by_issue_type(cls, issue_type: 'IssueType') -> list:
        """根据问题类型获取所有相关规则"""
        return [rule for rule in cls if rule.issue_type == issue_type]

    def __str__(self) -> str:
        return f"{self.code}: {self.description} ({self.issue_type.value})"


class BasicViolation(BaseModel):
    """MVP违规记录"""
    rule_code: str = Field(..., description="规则编码")
    rule_name: str = Field(..., description="规则名称")
    description: str = Field(..., description="违规描述")
    issue_type: IssueType = Field(..., description="问题类型")
    source_node: PipelineNode = Field(..., description="原节点")
    severity: Literal[SeverityLevel.INFO, SeverityLevel.WARNING, SeverityLevel.ERROR,
    SeverityLevel.MAJOR, SeverityLevel.MODERATE, SeverityLevel.CRITICAL] = Field(
        default=SeverityLevel.WARNING,
        description="严重程度"
    )
    fragment_id: Optional[str] = Field(
        default=None,
        description="涉及的片段ID"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="改进建议"
    )


class QualityRepairParams(BaseModel):
    fix_needed: bool = Field(
        default=False,
        description="是否需要修复"
    )

    issue_count: int = Field(
        default=0,
        description="问题数量"
    )

    issue_types: List[IssueType] = Field(
        default_factory=list,
        description="修复类型"
    )

    issues: List[BasicViolation] = Field(
        default_factory=list,
        description="完整问题列表"
    )

    fragments: List[str] = Field(
        default_factory=list,
        description="对应的片段ID集合"
    )

    suggestions: Dict[str, List[str]] = Field(
        default=None,
        description="修复建议"
    )

    severity_summary: Dict[str, int] = Field(
        default=None,
        description="严重程度摘要"
    )



class QualityAuditReport(BaseModel):
    """MVP质量审查报告"""

    # 元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "audited_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "auditor_type": "basic"
        }
    )

    # 项目信息
    project_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "title": "",
            "fragment_count": 0,
            "total_duration": 0.0
        }
    )

    # 审查状态
    status: AuditStatus = Field(
        default=AuditStatus.PASSED,
        description="审查状态：passed=通过, needs_revision=需要调整, failed=失败"
    )

    # 检查明细
    checks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="执行的检查项目"
    )

    # 违规记录
    violations: List[BasicViolation] = Field(
        default_factory=list,
        description="发现的违规问题"
    )

    # 统计数据
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_checks": 0,
            "passed_checks": 0,
            SeverityLevel.WARNING.value: 0,
            SeverityLevel.ERROR.value: 0,
            "fragments_checked": 0
        }
    )

    # 简单建议
    suggestions: List[str] = Field(
        default_factory=lambda: [
            "检查所有片段时长是否≤5秒",
            "确保没有空提示词"
        ]
    )

    # 最终结论
    conclusion: str = Field(
        default="审查通过，可以开始视频生成",
        description="审查结论"
    )

    score: float = Field(
        default=100.0,
        description="质量评分（0-100）"
    )

    detailed_analysis: Dict[str, Any] = Field(
        default=None,
        description="详细分析报告"
    )

    issues_source: Dict[PipelineNode, List[BasicViolation]] = Field(
        default=None,
        description="问题来源"
    )

    repair_params: Dict[PipelineNode, QualityRepairParams] = Field(
        default=None,
        description="修复参数"
    )
