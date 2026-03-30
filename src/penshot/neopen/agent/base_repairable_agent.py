"""
@FileName: base_repairable_agent.py
@Description: 可修复智能体基类 - 定义统一的修复接口
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/3/28
"""
import time
from abc import abstractmethod
from typing import Optional, List, Dict, Any, Generic

from penshot.logger import debug, info, warning
from penshot.neopen.agent.base_agent import BaseAgent, T, K
from penshot.neopen.agent.quality_auditor.quality_auditor_models import BasicViolation, QualityRepairParams
from penshot.neopen.agent.workflow.workflow_models import PipelineNode


class BaseRepairableAgent(BaseAgent, Generic[T, K]):
    """
    可修复智能体基类

    定义统一的修复接口，所有需要支持修复的智能体都应继承此类
    """

    def __init__(self):
        """初始化"""
        self.repair_history: List[Dict[str, Any]] = []
        self.current_repair_params: Optional[QualityRepairParams] = None
        self.current_historical_context: Optional[Dict[str, Any]] = None

        # 历史上下文分析结果（子类可使用）
        self._historical_insights: Dict[str, Any] = {}
        self._context_applied: bool = False

    @abstractmethod
    def detect_issues(self, result: T, node_params: K) -> List[BasicViolation]:
        """
        检测结果中的问题

        Args:
            result: 处理结果
            node_params: 节点所需参数

        Returns:
            问题列表
        """
        pass

    def apply_historical_context(self, historical_context: Dict[str, Any]) -> None:
        """
        应用历史上下文，优化解析策略（基类实现，子类可重写扩展）

        Args:
            historical_context: 历史上下文
                - common_issues: 常见问题模式
                - historical_stats: 历史统计信息
                - recent_strategy: 最近成功策略
                - 其他自定义字段
        """
        if not historical_context:
            return

        # 保存到实例变量，供子类使用
        self.current_historical_context = historical_context
        self._context_applied = True

        info("应用历史上下文优化策略")

        # 1. 分析常见问题模式
        self._analyze_common_issues(historical_context)

        # 2. 分析历史统计信息
        self._analyze_historical_stats(historical_context)

        # 3. 分析最近成功策略
        self._analyze_recent_strategy(historical_context)

        # 4. 调用子类扩展方法
        self._on_historical_context_applied()

    def _analyze_common_issues(self, historical_context: Dict[str, Any]) -> None:
        """分析常见问题模式"""
        common_issues = historical_context.get("common_issues")
        if not common_issues or not isinstance(common_issues, list):
            self._historical_insights["common_issues"] = {}
            return

        # 统计问题类型
        issue_type_counts = {}
        for issue in common_issues:
            if isinstance(issue, dict):
                issue_type = issue.get("issue_type", {})
                if isinstance(issue_type, dict):
                    issue_type = issue_type.get("value", "unknown")
                else:
                    issue_type = issue_type if issue_type else "unknown"
            else:
                issue_type = getattr(issue, "issue_type", "unknown")
                if hasattr(issue_type, "value"):
                    issue_type = issue_type.value

            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1

        self._historical_insights["common_issues"] = issue_type_counts

        if issue_type_counts:
            debug(f"历史常见问题统计: {issue_type_counts}")

            # 提取高频问题（出现次数 > 3）
            high_freq_issues = {
                t: c for t, c in issue_type_counts.items()
                if c > 3
            }
            if high_freq_issues:
                warning(f"检测到高频问题: {high_freq_issues}")
                self._historical_insights["high_freq_issues"] = high_freq_issues

    def _analyze_historical_stats(self, historical_context: Dict[str, Any]) -> None:
        """分析历史统计信息"""
        historical_stats = historical_context.get("historical_stats")
        if not historical_stats or not isinstance(historical_stats, dict):
            self._historical_insights["stats"] = {}
            return

        self._historical_insights["stats"] = historical_stats

        # 提取关键指标
        avg_completeness = historical_stats.get("completeness_score", 0)
        avg_confidence = historical_stats.get("parsing_confidence", {}).get("overall", 0) if isinstance(historical_stats.get("parsing_confidence"), dict) else 0

        debug(f"历史质量指标: 平均完整度={avg_completeness:.0%}, 平均置信度={avg_confidence:.0%}")

        # 质量评估
        if avg_completeness < 0.6:
            self._historical_insights["quality_level"] = "poor"
            warning("历史解析质量较低，将启用增强验证模式")
        elif avg_completeness < 0.8:
            self._historical_insights["quality_level"] = "medium"
            info("历史解析质量中等，建议关注关键字段提取")
        else:
            self._historical_insights["quality_level"] = "good"

    def _analyze_recent_strategy(self, historical_context: Dict[str, Any]) -> None:
        """分析最近成功策略"""
        recent_strategy = historical_context.get("recent_strategy")
        if recent_strategy:
            debug(f"最近成功策略: {recent_strategy}")
            self._historical_insights["recent_strategy"] = recent_strategy

    def _on_historical_context_applied(self) -> None:
        """
        历史上下文应用后的回调方法

        子类可以重写此方法，根据 self._historical_insights 调整内部配置
        """
        pass

    def get_historical_insights(self) -> Dict[str, Any]:
        """获取历史上下文分析结果"""
        return self._historical_insights.copy()

    def get_common_issue_patterns(self) -> Dict[str, int]:
        """获取常见问题模式"""
        return self._historical_insights.get("common_issues", {})

    def get_quality_level(self) -> str:
        """获取历史质量等级: poor/medium/good"""
        return self._historical_insights.get("quality_level", "unknown")

    def should_use_enhanced_validation(self) -> bool:
        """是否需要增强验证"""
        return self.get_quality_level() == "poor"

    def build_history_hint(self) -> str:
        """
        构建用于LLM提示词的历史上下文说明

        子类可调用此方法获取通用提示，也可重写添加自定义内容
        """
        hints = []

        # 常见问题提示
        high_freq_issues = self._historical_insights.get("high_freq_issues", {})
        if high_freq_issues:
            issue_desc = ", ".join([f"{t}({c}次)" for t, c in high_freq_issues.items()])
            hints.append(f"历史常见问题: {issue_desc}，请特别注意避免这些问题。")

        # 质量提示
        quality_level = self.get_quality_level()
        if quality_level == "poor":
            hints.append("历史解析质量较低，请提高解析质量，确保输出结构的完整性和准确性。")
        elif quality_level == "medium":
            hints.append("历史解析质量中等，请重点关注关键字段的准确识别。")

        # 最近策略提示
        recent_strategy = self._historical_insights.get("recent_strategy")
        if recent_strategy:
            if isinstance(recent_strategy, dict):
                strategy_hint = recent_strategy.get("suggestion") or recent_strategy.get("strategy")
            else:
                strategy_hint = recent_strategy
            if strategy_hint:
                hints.append(f"参考最近成功策略: {strategy_hint}")

        if not hints:
            return ""

        return "\n".join([
            "",
            "【历史参考信息】",
            *[f"  - {hint}" for hint in hints],
            ""
        ])

    def clear_historical_context(self) -> None:
        """清空历史上下文"""
        self.current_historical_context = None
        self._historical_insights = {}
        self._context_applied = False

    def apply_repair_params(self, node: PipelineNode, repair_params: QualityRepairParams) -> None:
        """
        应用修复参数（在下次执行时生效）

        调用时机：在 process 方法执行之前，由工作流节点调用
        作用：将修复参数保存到 self.current_repair_params，供 process 方法使用
        """
        self.current_repair_params = repair_params

        info(f"{node.value}节点收到修复参数，问题类型: {repair_params.issue_types}")
        if repair_params.suggestions:
            info(f"修复建议: {repair_params.suggestions}")

        # 记录修复历史
        self.repair_history.append({
            "timestamp": time.time(),
            "repair_params": {
                "issue_types": repair_params.issue_types,
                "suggestions": repair_params.suggestions
            }
        })

        # 子类可以重写此方法，根据修复参数调整内部状态
        self._on_repair_params_applied()

    def _on_repair_params_applied(self) -> None:
        """
        修复参数应用后的回调方法

        子类可以重写此方法，根据 self.current_repair_params 调整内部配置
        例如：增加镜头数量、缩短时长阈值等
        """
        pass

    def repair_result(self, result: T, issues: List[BasicViolation], node_params: K) -> T:
        """
        修复已有结果（后处理修复）

        调用时机：质量审查后立即调用，不等待重试
        作用：直接修正已经生成的结果
        """
        # 记录修复历史
        self.repair_history.append({
            "timestamp": time.time(),
            "issues_count": len(issues),
            "repair_type": "post_process"
        })

        return result

    def clear_repair_params(self) -> None:
        """清空当前修复参数（修复成功后调用）"""
        self.current_repair_params = None

    def get_repair_history(self) -> List[Dict[str, Any]]:
        """获取修复历史"""
        return self.repair_history

    def clear_repair_history(self):
        """清空修复历史"""
        self.repair_history = []
