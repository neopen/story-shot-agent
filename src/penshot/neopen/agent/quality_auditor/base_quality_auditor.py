"""
@FileName: base_quality_auditor.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/27 0:00
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List

from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport, BasicViolation, SeverityLevel, AuditStatus
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info


class BaseQualityAuditor(ABC):
    """质量审查器抽象基类"""

    def __init__(self, config: Optional[ShotConfig]):
        self.config = config
        self._initialize()

    def _initialize(self):
        """初始化审查器"""
        info(f"初始化质量审查器: {self.__class__.__name__}")
        # 添加状态阈值配置
        self.thresholds = {
            "critical_error_count": 1,  # 严重错误数量阈值
            "major_violation_count": 3,  # 主要违规阈值
            "total_violation_count": 5,  # 总违规阈值
            "warning_ratio": 0.3,  # 警告比例阈值
        }

        # 违规扣分规则
        self.penalty_weights = {
            SeverityLevel.INFO: 0.01,  # 信息级别扣1%
            SeverityLevel.WARNING: 0.05,  # 警告扣5%
            SeverityLevel.MODERATE: 0.15,  # 中度扣15%
            SeverityLevel.MAJOR: 0.30,  # 主要扣30%
            SeverityLevel.CRITICAL: 0.50,  # 严重扣50%
            SeverityLevel.ERROR: 1.00  # 错误扣100%
        }

    @abstractmethod
    def audit(self, instructions: AIVideoInstructions) -> QualityAuditReport:
        """审查AI视频指令（抽象方法）"""
        pass

    def post_process(self, report: QualityAuditReport) -> QualityAuditReport:
        """后处理：填充统计数据并确定状态"""

        # 1. 统计各种级别的违规数量
        violation_counts = self._count_violations_by_severity(report.violations)

        # 2. 统计检查项
        check_stats = self._calculate_check_stats(report.checks)

        # 3. 确定审计状态（基于严重程度规则）
        status = self._determine_audit_status(violation_counts, check_stats)

        # 4. 计算质量评分
        quality_score = self._calculate_quality_score(violation_counts, check_stats)

        # 5. 更新报告
        report.stats.update({
            **violation_counts,
            **check_stats,
            "quality_score": quality_score,
            "total_violations": len(report.violations),
            "has_issues": len(report.violations) > 0,
            "needs_human_review": violation_counts[SeverityLevel.CRITICAL] > 0 or violation_counts[SeverityLevel.MAJOR] > 2
        })

        report.status = status

        # 6. 生成结论和建议
        report.conclusion = self._generate_conclusion(status, violation_counts)
        report.detailed_analysis = self._generate_detailed_analysis(report)

        info(
            f"审查完成: 状态={status.value}, "
            f"检查通过={check_stats['passed_checks']}/{check_stats['total_checks']}, "
            f"违规={len(report.violations)}个, "
            f"评分={quality_score:.1%}"
        )

        return report

    def _count_violations_by_severity(self, violations: List[BasicViolation]) -> Dict[SeverityLevel, int]:
        """按严重程度统计违规数量"""
        counts = {
            SeverityLevel.INFO: 0,  # 信息级别
            SeverityLevel.WARNING: 0,  # 警告
            SeverityLevel.MODERATE: 0,  # 中度
            SeverityLevel.MAJOR: 0,  # 主要
            SeverityLevel.CRITICAL: 0,  # 严重
            SeverityLevel.ERROR: 0  # 错误
        }

        for violation in violations:
            severity = violation.severity.value
            if severity in counts:
                counts[severity] += 1

        return counts

    def _calculate_check_stats(self, checks: List[Dict[str, Any]]) -> Dict[str, int]:
        """计算检查项统计"""
        total_checks = len(checks)
        passed_checks = sum(1 for check in checks if check.get("status") == AuditStatus.PASSED)
        failed_checks = total_checks - passed_checks

        return {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "pass_rate": round(passed_checks / total_checks, 2) if total_checks > 0 else 1.0
        }

    def _determine_audit_status(self,
                                violation_counts: Dict[SeverityLevel, int],
                                check_stats: Dict[str, Any]) -> AuditStatus:
        """
        基于违规严重程度确定审计状态

        状态判定规则（优先级从上到下）：
        1. 有任何ERROR → FAILED
        2. 有CRITICAL违规 → CRITICAL_ISSUES
        3. 有2个以上MAJOR或MAJOR+MODERATE组合 → MAJOR_ISSUES
        4. 有MODERATE违规 → MODERATE_ISSUES
        5. 有WARNING违规 → MINOR_ISSUES
        6. 检查通过率<90% → MINOR_ISSUES
        7. 完美 → PASSED
        8. 特殊情况 → NEEDS_HUMAN
        """

        # 1. 检查错误级别（完全失败）
        if violation_counts[SeverityLevel.ERROR] > 0:
            return AuditStatus.FAILED

        # 2. 检查严重级别（需要人工干预）
        if violation_counts[SeverityLevel.CRITICAL] > 0:
            return AuditStatus.CRITICAL_ISSUES

        # 3. 检查主要问题级别（需要重新处理）
        if (violation_counts[SeverityLevel.MAJOR] >= 2 or
                (violation_counts[SeverityLevel.MAJOR] >= 1 and violation_counts[SeverityLevel.MODERATE] >= 2)):
            return AuditStatus.MAJOR_ISSUES

        # 4. 检查中度问题（需要调整）
        if violation_counts[SeverityLevel.MODERATE] > 0:
            return AuditStatus.MODERATE_ISSUES

        # 5. 检查警告级别（轻微问题）
        if violation_counts[SeverityLevel.WARNING] > 0:
            return AuditStatus.MINOR_ISSUES

        # 6. 检查通过率（如果检查项通过率低，也算轻微问题）
        if check_stats.get("pass_rate", 1.0) < 0.9:
            return AuditStatus.MINOR_ISSUES

        # 7. 完美通过
        if (violation_counts[SeverityLevel.INFO] == 0 and
                violation_counts[SeverityLevel.WARNING] == 0 and
                violation_counts[SeverityLevel.MODERATE] == 0 and
                violation_counts[SeverityLevel.MAJOR] == 0 and
                violation_counts[SeverityLevel.CRITICAL] == 0):
            return AuditStatus.PASSED

        # 8. 默认情况（需要人工检查）
        return AuditStatus.NEEDS_HUMAN

    def _calculate_quality_score(self,
                                 violation_counts: Dict[SeverityLevel, int],
                                 check_stats: Dict[str, Any]) -> float:
        """计算质量评分（0-1之间）"""

        # 基础分（基于检查通过率）
        base_score = check_stats.get("pass_rate", 1.0)

        # 计算总扣分
        total_penalty = 0.0
        for severity, count in violation_counts.items():
            if severity in self.penalty_weights:
                # 扣分随数量增加而增加，但设置上限
                max_count = 5 if severity in [SeverityLevel.INFO, SeverityLevel.WARNING] else 3
                effective_count = min(count, max_count)
                penalty = self.penalty_weights[severity] * effective_count
                total_penalty += penalty

        # 最终得分（不能低于0）
        final_score = max(0.0, base_score - total_penalty)

        return round(final_score, 2)

    def _generate_conclusion(self, status: AuditStatus, violation_counts: Dict[SeverityLevel, int]) -> str:
        """生成审查结论"""

        conclusions = {
            AuditStatus.PASSED: "审查通过，可以开始视频生成",

            AuditStatus.MINOR_ISSUES: (
                f"有{violation_counts[SeverityLevel.WARNING]}个警告问题，建议优化后继续"
            ),

            AuditStatus.MODERATE_ISSUES: (
                f"发现{violation_counts[SeverityLevel.MODERATE]}个中度问题，需要调整后再继续"
            ),

            AuditStatus.MAJOR_ISSUES: (
                f"发现{violation_counts[SeverityLevel.MAJOR]}个主要问题，建议重新处理相关片段"
            ),

            AuditStatus.CRITICAL_ISSUES: (
                f"发现{violation_counts[SeverityLevel.CRITICAL]}个严重问题，需要人工干预"
            ),

            AuditStatus.FAILED: (
                f"发现{violation_counts[SeverityLevel.ERROR]}个错误，无法继续视频生成"
            ),

            AuditStatus.NEEDS_HUMAN: "发现特殊情况，需要人工决策"
        }

        return conclusions.get(status, "审查完成，需要进一步分析")

    def _generate_detailed_analysis(self, report: QualityAuditReport) -> Dict[str, Any]:
        """生成详细分析报告"""

        # 按严重程度分组违规
        violations_by_severity = {}
        for severity in SeverityLevel:
            severity_violations = [
                {
                    "rule_name": v.rule_name,
                    "description": v.description,
                    "fragment_id": v.fragment_id,
                    "suggestion": v.suggestion
                }
                for v in report.violations if v.severity == severity
            ]
            violations_by_severity[severity.value] = severity_violations

        # 高风险片段识别
        fragment_violations = {}
        for violation in report.violations:
            if violation.fragment_id:
                frag_id = violation.fragment_id
                if frag_id not in fragment_violations:
                    fragment_violations[frag_id] = []
                fragment_violations[frag_id].append({
                    "severity": violation.severity.value,
                    "rule_name": violation.rule_name,
                    "description": violation.description
                })

        # 识别高风险片段（有严重或主要问题的片段）
        high_risk_fragments = [
            frag_id for frag_id, violations in fragment_violations.items()
            if any(v["severity"] in [SeverityLevel.CRITICAL, SeverityLevel.MAJOR, SeverityLevel.ERROR] for v in violations)
        ]

        return {
            "violations_by_severity": violations_by_severity,
            "fragment_violation_summary": {
                "total_fragments_with_issues": len(fragment_violations),
                "high_risk_fragments": high_risk_fragments,
                "fragment_details": fragment_violations
            },
            "recommended_actions": self._generate_recommended_actions(report),
            "timeline_impact": self._assess_timeline_impact(report.status)
        }

    def _generate_recommended_actions(self, report: QualityAuditReport) -> List[str]:
        """生成推荐操作"""
        actions = []

        # 根据状态推荐不同操作
        if report.status == AuditStatus.PASSED:
            actions.append("可以直接开始视频生成")

        elif report.status == AuditStatus.MINOR_ISSUES:
            actions.append("检查并修复警告级别的问题")
            actions.append("优化提示词长度和内容")

        elif report.status == AuditStatus.MODERATE_ISSUES:
            actions.append("重新生成有问题的提示词")
            actions.append("调整片段时长设置")

        elif report.status == AuditStatus.MAJOR_ISSUES:
            actions.append("重新分割有问题的视频片段")
            actions.append("重新分析镜头拆分逻辑")

        elif report.status == AuditStatus.CRITICAL_ISSUES:
            actions.append("需要人工审核和决策")
            actions.append("检查是否存在系统性问题")

        elif report.status == AuditStatus.FAILED:
            actions.append("停止当前流程")
            actions.append("修复根本性错误")
            actions.append("重新开始整个工作流")

        # 添加具体的修复建议
        for violation in report.violations:
            if violation.suggestion and violation.severity in [
                SeverityLevel.MODERATE,
                SeverityLevel.MAJOR,
                SeverityLevel.CRITICAL,
                SeverityLevel.ERROR
            ]:
                actions.append(f"修复: {violation.rule_name} - {violation.suggestion}")

        return list(set(actions))  # 去重

    def _assess_timeline_impact(self, status: AuditStatus) -> Dict[str, Any]:
        """评估对时间线的影响"""
        impact_levels = {
            AuditStatus.PASSED: {
                "impact": "无影响",
                "estimated_delay": "0分钟",
                "priority": "低",
                "can_proceed": True
            },
            AuditStatus.MINOR_ISSUES: {
                "impact": "轻微影响",
                "estimated_delay": "5-10分钟",
                "priority": "中低",
                "can_proceed": True
            },
            AuditStatus.MODERATE_ISSUES: {
                "impact": "中度影响",
                "estimated_delay": "15-30分钟",
                "priority": "中",
                "can_proceed": True
            },
            AuditStatus.MAJOR_ISSUES: {
                "impact": "较大影响",
                "estimated_delay": "30-60分钟",
                "priority": "高",
                "can_proceed": False
            },
            AuditStatus.CRITICAL_ISSUES: {
                "impact": "严重影响",
                "estimated_delay": "1-2小时",
                "priority": "紧急",
                "can_proceed": False
            },
            AuditStatus.FAILED: {
                "impact": "完全阻塞",
                "estimated_delay": "未知",
                "priority": "最高",
                "can_proceed": False
            },
            AuditStatus.NEEDS_HUMAN: {
                "impact": "依赖人工",
                "estimated_delay": "取决于响应时间",
                "priority": "高",
                "can_proceed": False
            }
        }

        return impact_levels.get(status, impact_levels[AuditStatus.NEEDS_HUMAN])

    def _add_check(self, report: QualityAuditReport, check_name: str, status: str, details: str = "") -> None:
        """添加检查记录"""
        report.checks.append({
            "name": check_name,
            "status": status,
            "details": details,
            "checked_at": datetime.now().isoformat()
        })

    def _add_violation(self, report: QualityAuditReport, rule_id: str, rule_name: str,
                       description: str, severity: str = "warning",
                       fragment_id: Optional[str] = None, suggestion: Optional[str] = None) -> None:
        """添加违规记录"""
        violation = BasicViolation(
            rule_id=rule_id,
            rule_name=rule_name,
            description=description,
            severity=severity,
            fragment_id=fragment_id,
            suggestion=suggestion
        )
        report.violations.append(violation)
