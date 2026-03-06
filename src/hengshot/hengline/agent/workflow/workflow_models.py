"""
@FileName: workflow_models.py
@Description: 工作流模型定义文件，包含工作流状态和条件的枚举类
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/27 19:12
"""
from enum import Enum, unique


@unique
class AgentStage(str, Enum):
    """智能体工作流阶段枚举类，定义工作流的不同阶段状态"""
    START = "loaded"  # 开始状态
    INIT = "initialized"  # 初始化状态
    PARSER = "parsed"  # 剧本解析完成
    SEGMENTER = "segmented"  # 分镜拆分完成
    SPLITTER = "split"  # 片段分隔完成
    CONVERTER = "converted"  # 指令转换完成
    AUDITOR = "audited"  # 质量审查完成
    CONTINUITY = "continuity_check"  # 连续性检查完成
    END = "completed"  # 工作流完成
    ERROR_HANDLER = "error_handler"  # 错误处理
    HUMAN_INTERVENTION = "human_intervention"  # 人工干预
    FINAL_OUTPUT = "final_output"  # 最终输出


# ============================================================================
# 决策状态枚举
# ============================================================================
@unique
class PipelineState(str, Enum):
    """
    决策状态枚举 - 表示单个操作或检查的结果

    说明:
    - 用于决策函数的返回值
    - 表示操作的成功、失败、需要调整等状态
    - 是工作流分支决策的依据

    设计原则:
    1. 语义清晰: 每个状态都有明确的业务含义
    2. 正交性: 状态之间互斥，不重叠
    3. 可操作性: 每个状态都能映射到具体的下一步操作
    """
    # 成功状态
    SUCCESS = "success"  # 完全成功
    VALID = "valid"  # 验证通过（有小问题）

    # 修复状态（合并 NEEDS_ADJUSTMENT 和 NEEDS_FIX）
    NEEDS_REPAIR = "needs_repair"  # 需要修复/调整/优化

    # 重试状态
    RETRY = "retry"  # 需要重试

    # 人工状态
    NEEDS_HUMAN = "needs_human"  # 需要人工干预

    # 失败状态
    FAILED = "failed"  # 一般失败
    ABORT = "abort"  # 中止流程


# ============================================================================
# 工作流阶段枚举 (PipelineState)
# ============================================================================
@unique
class PipelineNode(str, Enum):
    """
    工作流管道节点枚举类，定义工作流管道中的节点
    说明:
    - 用于标识工作流图中的节点
    - 每个节点对应一个具体的处理功能
    - 决策状态会映射到这些节点

    分类说明:
    A. 核心处理阶段: 视频生成的主流程
    B. 质量控制阶段: 质量审查和检查
    C. 调整修复阶段: 针对问题的修复流程
    D. 特殊处理阶段: 人工干预和错误处理
    E. 流程状态: 流程的开始和结束
    """
    # 核心处理阶段
    PARSE_SCRIPT = "parse_script"  # 剧本解析节点
    SEGMENT_SHOT = "segment_shot"  # 分镜拆分节点
    SPLIT_VIDEO = "split_video"  # 片段分隔节点
    CONVERT_PROMPT = "convert_prompt"  # 指令转换节点
    AUDIT_QUALITY = "audit_quality"  # 质量审查节点
    CONTINUITY_CHECK = "continuity_check"  # 连续性检查节点

    # 调整修复阶段
    HUMAN_INTERVENTION = "human_intervention"  # 人工干预节点
    ERROR_HANDLER = "error_handler"  # 错误处理节点

    LOOP_CHECK = "loop_check"  # 循环检查节点

    # 生成与结束阶段
    GENERATE_OUTPUT = "generate_output"  # 生成输出节点
    # GENERATE_VIDEO = "generate_video"  # 生成视频
    END = "end"  # 结束节点
