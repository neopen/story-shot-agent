"""
@FileName: base_agent.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/9 21:23
"""
from abc import ABC
from abc import abstractmethod
from typing import Optional, TypeVar, Any, List, Dict

from penshot.logger import warning

T = TypeVar('T')  # 输出类型泛型
K = TypeVar('K')  # 输出类型泛型


class BaseAgent(ABC):
    """
        智能体基类

        定义统一的接口，所有需要的智能体都应继承此类
        """

    @abstractmethod
    def process(self, *args, **kwargs) -> Optional[T]:
        """
        核心处理方法 - 子类必须实现

        注意：子类在实现时，应直接使用 self.current_repair_params 和
        self.current_historical_context，无需再通过参数传递

        Returns:
            处理结果
        """
        pass

    # ===================== 通用数据提取函数 =====================
    def _extract_issue_type(self, issue: Any) -> str:
        """
        从各种格式的 issue 中提取类型

        Args:
            issue: 可以是 dict 或对象

        Returns:
            问题类型字符串
        """
        try:
            if isinstance(issue, dict):
                issue_type = issue.get("issue_type")
                if isinstance(issue_type, dict):
                    return issue_type.get("value", "unknown")
                elif isinstance(issue_type, str):
                    return issue_type
                return "unknown"
            else:
                # 对象类型
                issue_type = getattr(issue, "issue_type", "unknown")
                if hasattr(issue_type, 'value'):
                    return issue_type.value
                return str(issue_type)
        except Exception as e:
            warning(f"提取问题类型失败: {e}")
            return "unknown"

    def _extract_issue_severity(self, issue: Any) -> str:
        """
        从各种格式的 issue 中提取严重程度

        Args:
            issue: 可以是 dict 或对象

        Returns:
            严重程度字符串
        """
        try:
            if isinstance(issue, dict):
                severity = issue.get("severity")
                if isinstance(severity, dict):
                    return severity.get("value", "moderate")
                elif isinstance(severity, str):
                    return severity
                return "moderate"
            else:
                severity = getattr(issue, "severity", "moderate")
                if hasattr(severity, 'value'):
                    return severity.value
                return str(severity)
        except Exception as e:
            warning(f"提取严重程度失败: {e}")
            return "moderate"

    def _extract_issue_description(self, issue: Any) -> str:
        """
        从各种格式的 issue 中提取描述

        Args:
            issue: 可以是 dict 或对象

        Returns:
            问题描述字符串
        """
        try:
            if isinstance(issue, dict):
                return issue.get("description", "")
            else:
                return getattr(issue, "description", "")
        except Exception as e:
            warning(f"提取问题描述失败: {e}")
            return ""

    def _extract_issue_fragment_id(self, issue: Any) -> Optional[str]:
        """
        从各种格式的 issue 中提取片段ID

        Args:
            issue: 可以是 dict 或对象

        Returns:
            片段ID或None
        """
        try:
            if isinstance(issue, dict):
                return issue.get("fragment_id")
            else:
                return getattr(issue, "fragment_id", None)
        except Exception as e:
            warning(f"提取片段ID失败: {e}")
            return None

    def _extract_violation_type(self, violation: Any) -> str:
        """
        从各种格式的 violation 中提取类型（别名，保持语义清晰）

        Args:
            violation: 可以是 dict 或对象

        Returns:
            问题类型字符串
        """
        return self._extract_issue_type(violation)

    def _extract_violation_severity(self, violation: Any) -> str:
        """从 violation 中提取严重程度（别名）"""
        return self._extract_issue_severity(violation)

    # ===================== 统计和汇总函数 =====================

    def _count_issue_types(self, issues: List[Any], max_items: int = 30) -> Dict[str, int]:
        """
        统计问题类型出现次数

        Args:
            issues: 问题列表
            max_items: 最多处理条数

        Returns:
            问题类型计数字典
        """
        issue_counts = {}
        for issue in issues[:max_items]:
            issue_type = self._extract_issue_type(issue)
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        return issue_counts

    def _get_top_issues(self, issues: List[Any], top_n: int = 3, max_items: int = 30) -> List[str]:
        """
        获取最常见的问题类型

        Args:
            issues: 问题列表
            top_n: 返回前N个
            max_items: 最多处理条数

        Returns:
            格式化的问题列表，如 ["type1(5次)", "type2(3次)"]
        """
        issue_counts = self._count_issue_types(issues, max_items)
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [f"{t}({c}次)" for t, c in sorted_issues[:top_n]]

    def _get_issue_type_summary(self, issues: List[Any], max_items: int = 20) -> str:
        """
        获取问题类型摘要（用于提示词）

        Args:
            issues: 问题列表
            max_items: 最多处理条数

        Returns:
            格式化的问题摘要字符串
        """
        issue_counts = {}
        for issue in issues[:max_items]:
            issue_type = self._extract_issue_type(issue)
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

        if not issue_counts:
            return ""

        items = [f"{t}({c}次)" for t, c in list(issue_counts.items())[:3]]
        return ", ".join(items)

    # ===================== 上下文提取函数 =====================

    def _get_common_issues_hint(self, historical_context: Dict[str, Any],
                                context_name: str = "问题") -> Optional[str]:
        """
        获取常见问题提示

        Args:
            historical_context: 历史上下文
            context_name: 上下文名称（如"分镜"、"分割"等）

        Returns:
            格式化的问题提示，如果没有则返回None
        """
        common_issues = historical_context.get("common_issues")
        if not common_issues or not isinstance(common_issues, list):
            return None

        top_issues = self._get_top_issues(common_issues, top_n=3)
        if not top_issues:
            return None

        return f"常见{context_name}类型: {', '.join(top_issues)}，请特别注意避免这些问题。"

    def _get_historical_stats_hint(self, historical_context: Dict[str, Any],
                                   stat_keys: List[str],
                                   thresholds: Dict[str, tuple] = None) -> List[str]:
        """
        获取历史统计信息提示

        Args:
            historical_context: 历史上下文
            stat_keys: 要提取的统计键列表
            thresholds: 阈值配置，如 {"shot_count": (5, "偏少", "建议增加")}

        Returns:
            提示列表
        """
        hints = []
        historical_stats = historical_context.get("historical_stats")

        if not historical_stats or not isinstance(historical_stats, dict):
            return hints

        for key in stat_keys:
            value = historical_stats.get(key)
            if value is None:
                continue

            if thresholds and key in thresholds:
                threshold, low_msg, high_msg = thresholds[key]
                if value < threshold:
                    hints.append(low_msg)
                elif value > threshold:
                    hints.append(high_msg)

        return hints

    def _get_historical_issues_hint(self, historical_context: Dict[str, Any],
                                    context_name: str = "问题") -> Optional[str]:
        """
        获取历史问题模式提示

        Args:
            historical_context: 历史上下文
            context_name: 上下文名称

        Returns:
            格式化的问题模式提示
        """
        historical_issues = historical_context.get("historical_issues")
        if not historical_issues or not isinstance(historical_issues, list):
            return None

        issue_summary = self._get_issue_type_summary(historical_issues, max_items=20)
        if not issue_summary:
            return None

        return f"历史{context_name}: {issue_summary}，请参考避免。"
