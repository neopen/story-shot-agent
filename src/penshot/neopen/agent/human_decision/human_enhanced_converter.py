"""
@FileName: human_enhanced_converter.py
@Description: 增强版人工决策转换器
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/2/5 17:47
"""
from typing import Dict, Any

from penshot.neopen.agent.human_decision.human_decision_converter import HumanDecisionConverter
from penshot.neopen.agent.workflow.workflow_models import PipelineState


class EnhancedHumanDecisionConverter(HumanDecisionConverter):
    """增强版转换器 - 支持更多功能"""

    def __init__(self):
        super().__init__()
        # 添加自定义映射
        self.INPUT_TO_STANDARD_MAP.update({
            # 中文支持
            "继续": "CONTINUE",
            "重启": "RETRY",
            "重试": "RETRY",
            "修复": "REPAIR",
            "调整": "REPAIR",
            "优化": "REPAIR",
            "升级": "ESCALATE",
            "中止": "ABORT",
            "停止": "ABORT",

            # 更多英文变体
            "REPAIR": "REPAIR",
            "CORRECT": "REPAIR",
            "RESOLVE": "REPAIR",
            "HUMAN": "ESCALATE",
            "INTERVENTION": "ESCALATE",
            "STOP": "ABORT",
            "CANCEL": "ABORT",
        })

    def suggest_decision(self, context: Dict[str, Any]) -> str:
        """根据上下文建议决策

        Args:
            context: 上下文信息

        Returns:
            str: 建议的标准化决策
        """
        has_errors = context.get("has_errors", False)
        is_timeout = context.get("is_timeout", False)
        retry_count = context.get("retry_count", 0)
        max_retries = context.get("max_retries", 3)
        current_stage = context.get("current_stage", "")

        if is_timeout:
            return "CONTINUE"  # 超时默认继续

        if has_errors:
            if retry_count >= max_retries:
                return "ESCALATE"  # 超过重试次数，需要人工干预
            else:
                return "RETRY"  # 有错误但还可以重试

        # 根据当前阶段提供建议
        if current_stage:
            stage_suggestions = {
                "PARSER": "CONTINUE",  # 剧本解析后通常继续
                "SEGMENTER": "REPAIR",  # 镜头拆分有问题需要修复
                "SPLITTER": "REPAIR",  # 片段分割有问题需要修复
                "CONVERTER": "REPAIR",  # 提示词生成有问题需要修复
                "AUDITOR": "CONTINUE",  # 质量审查后通常继续
                "CONTINUITY": "CONTINUE",  # 连续性检查后通常继续
            }
            suggested = stage_suggestions.get(current_stage.upper(), "CONTINUE")
            return suggested

        # 默认建议
        return "CONTINUE"

    def explain_decision(self, decision_state: PipelineState,
                         input_str: str = None) -> Dict[str, str]:
        """解释决策

        Args:
            decision_state: 决策状态
            input_str: 原始输入（可选）

        Returns:
            Dict: 解释信息
        """
        explanation = {
            "decision": decision_state.value,
            "description": self.get_decision_description(decision_state),
            "impact": "",
            "next_steps": "",
        }

        # 根据决策状态添加影响
        impacts = {
            PipelineState.SUCCESS: "继续生成最终视频",
            PipelineState.VALID: "验证通过，继续生成最终视频",
            PipelineState.NEEDS_RETRY: "重新开始处理流程",
            PipelineState.NEEDS_REPAIR: "修复问题后继续处理",
            PipelineState.NEEDS_HUMAN: "等待进一步人工决策",
            PipelineState.FAILED: "处理失败，进入错误处理",
            PipelineState.ABORT: "立即停止所有处理",
        }

        # 根据决策状态添加下一步行动
        next_steps = {
            PipelineState.SUCCESS: "进入生成输出阶段",
            PipelineState.VALID: "进入生成输出阶段",
            PipelineState.NEEDS_RETRY: "重新开始流程（从剧本解析开始）",
            PipelineState.NEEDS_REPAIR: "根据具体问题进入相应修复阶段",
            PipelineState.NEEDS_HUMAN: "等待人工进一步决策",
            PipelineState.FAILED: "进入错误处理阶段",
            PipelineState.ABORT: "清理资源并结束工作流",
        }

        # 根据决策状态添加详细修复建议
        repair_details = {
            PipelineState.NEEDS_REPAIR: {
                "general": "检查并修复发现的问题",
                "parsing": "检查剧本格式和内容",
                "segmentation": "调整镜头拆分参数",
                "splitting": "重新分割视频片段",
                "prompt": "优化提示词质量",
                "continuity": "修复连续性问题",
            }
        }

        explanation["impact"] = impacts.get(decision_state, "继续处理")
        explanation["next_steps"] = next_steps.get(decision_state, "根据流程继续")

        # 如果是修复状态，添加详细建议
        if decision_state == PipelineState.NEEDS_REPAIR:
            explanation["repair_suggestions"] = repair_details[PipelineState.NEEDS_REPAIR]

        if input_str:
            explanation["input"] = input_str
            explanation["normalized"] = self.normalize_input(input_str)
            explanation["input_description"] = self.get_standard_input_description(explanation["normalized"])

        return explanation

    def get_context_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析上下文并提供决策建议

        Args:
            context: 上下文信息

        Returns:
            Dict: 分析结果和建议
        """
        analysis = {
            "situation": "normal",
            "suggested_decision": "CONTINUE",
            "reasons": [],
            "warnings": [],
        }

        # 分析各种情况
        retry_count = context.get("retry_count", 0)
        max_retries = context.get("max_retries", 3)
        has_errors = context.get("has_errors", False)
        error_count = context.get("error_count", 0)
        is_timeout = context.get("is_timeout", False)
        current_stage = context.get("current_stage", "")

        # 判断情况
        if is_timeout:
            analysis["situation"] = "timeout"
            analysis["suggested_decision"] = "CONTINUE"
            analysis["reasons"].append("处理超时，建议继续流程")

        elif error_count > 5:
            analysis["situation"] = "critical_errors"
            analysis["suggested_decision"] = "ESCALATE"
            analysis["reasons"].append(f"发现{error_count}个错误，问题严重")
            analysis["warnings"].append("需要人工干预检查")

        elif has_errors and retry_count >= max_retries:
            analysis["situation"] = "retry_exhausted"
            analysis["suggested_decision"] = "ESCALATE"
            analysis["reasons"].append(f"已重试{retry_count}次，超过最大重试限制{max_retries}")

        elif has_errors:
            analysis["situation"] = "needs_retry"
            analysis["suggested_decision"] = "RETRY"
            analysis["reasons"].append("存在错误，建议重试")

        elif current_stage in ["SEGMENTER", "SPLITTER", "CONVERTER"]:
            analysis["situation"] = "quality_issue"
            analysis["suggested_decision"] = "REPAIR"
            analysis["reasons"].append(f"当前处于{current_stage}阶段，建议检查质量")

        else:
            analysis["situation"] = "normal"
            analysis["suggested_decision"] = "CONTINUE"
            analysis["reasons"].append("一切正常，可以继续流程")

        # 获取建议决策的完整信息
        suggested_standard = analysis["suggested_decision"]
        suggested_state = self.STANDARD_TO_STATE_MAP.get(suggested_standard, PipelineState.SUCCESS)

        analysis["suggested_state"] = suggested_state.value
        analysis["suggested_description"] = self.get_decision_description(suggested_state)

        return analysis

    def validate_with_context(self, decision_state: PipelineState,
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """结合上下文验证决策

        Args:
            decision_state: 决策状态
            context: 上下文信息

        Returns:
            Dict: 验证结果和详细信息
        """
        validation_result = {
            "is_valid": True,
            "warnings": [],
            "suggestions": [],
            "alternatives": [],
        }

        # 基本验证
        is_valid = self.validate_decision(decision_state, context)
        validation_result["is_valid"] = is_valid

        if not is_valid:
            validation_result["warnings"].append("决策在当前上下文中不合理")

        # 检查重试次数
        retry_count = context.get("retry_count", 0)
        max_retries = context.get("max_retries", 3)

        if decision_state == PipelineState.NEEDS_RETRY and retry_count >= max_retries:
            validation_result["is_valid"] = False
            validation_result["warnings"].append(f"重试次数已耗尽 ({retry_count}/{max_retries})")
            validation_result["suggestions"].append("考虑使用NEEDS_REPAIR或NEEDS_HUMAN")

        # 如果是中止，确认上下文允许
        if decision_state == PipelineState.ABORT:
            validation_result["warnings"].append("中止操作不可恢复，请确认")
            validation_result["alternatives"].append("RETRY")  # 重试
            validation_result["alternatives"].append("NEEDS_REPAIR")  # 修复

        # 如果是人工干预，检查是否必要
        if decision_state == PipelineState.NEEDS_HUMAN:
            # 检查是否真的需要人工干预
            error_count = context.get("error_count", 0)
            if error_count < 2:
                validation_result["suggestions"].append("问题较少，可以考虑使用RETRY或NEEDS_REPAIR")

        # 添加决策解释
        validation_result["decision_explanation"] = self.explain_decision(decision_state)

        return validation_result
