"""
@FileName: quality_auditor_agent.py
@Description: 质量审查器 - 合并基本规则和LLM审查结果
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/25 21:59
"""
from typing import Optional, Dict, List

from penshot.logger import debug, info, error
from penshot.neopen.agent.base_models import AgentMode
from penshot.neopen.agent.prompt_converter.prompt_converter_models import AIVideoInstructions
from penshot.neopen.agent.quality_auditor.quality_auditor_factory import QualityAuditorFactory
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityAuditReport, AuditStatus, SeverityLevel, IssueType, QualityRepairParams, BasicViolation
from penshot.neopen.agent.workflow.workflow_models import PipelineNode
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class QualityAuditorAgent:
    """质量审查器 - 合并基本规则和LLM审查结果"""

    def __init__(self, llm, config: Optional[ShotConfig]):
        """
        初始化质量审查器

        Args:
            llm: 语言模型实例
            config: 配置
        """
        self.llm = llm
        self.config = config or {}

        # 初始化各审查器
        if self.config.enable_llm:
            self.rule_auditor = QualityAuditorFactory.create_auditor(AgentMode.RULE, config)
            self.llm_auditor = QualityAuditorFactory.create_auditor(AgentMode.LLM, config, llm)
        else:
            self.rule_auditor = QualityAuditorFactory.create_auditor(AgentMode.RULE, config)
            self.llm_auditor = None

        # 问题类型到来源节点的映射（扩展）
        self.issue_source_mapping = {
            # 剧本解析阶段
            IssueType.SCENE: PipelineNode.PARSE_SCRIPT,
            IssueType.CHARACTER: PipelineNode.PARSE_SCRIPT,
            IssueType.DIALOGUE: PipelineNode.PARSE_SCRIPT,
            IssueType.ACTION: PipelineNode.PARSE_SCRIPT,

            # 分镜生成阶段
            IssueType.FRAGMENT: PipelineNode.SEGMENT_SHOT,
            IssueType.CONTINUITY: PipelineNode.SEGMENT_SHOT,

            # 视频分割阶段
            IssueType.DURATION: PipelineNode.SPLIT_VIDEO,

            # 提示词转换阶段
            IssueType.TRUNCATION: PipelineNode.CONVERT_PROMPT,
            IssueType.PROMPT: PipelineNode.CONVERT_PROMPT,
            IssueType.STYLE: PipelineNode.CONVERT_PROMPT,
            IssueType.MODEL: PipelineNode.CONVERT_PROMPT,
            IssueType.AUDIO: PipelineNode.CONVERT_PROMPT,

            # 其他
            IssueType.WEATHER: PipelineNode.PARSE_SCRIPT,
            IssueType.FORMAT: PipelineNode.PARSE_SCRIPT,
            IssueType.COMPLETENESS: PipelineNode.PARSE_SCRIPT,
        }

        # 严重程度权重
        self.severity_weights = {
            SeverityLevel.INFO: 1,
            SeverityLevel.WARNING: 5,
            SeverityLevel.MODERATE: 10,
            SeverityLevel.MAJOR: 20,
            SeverityLevel.CRITICAL: 30,
            SeverityLevel.ERROR: 50,
        }

    def qa_process(self, instructions: AIVideoInstructions,
                   stage_issues: Optional[Dict[PipelineNode, List[BasicViolation]]]) -> Optional[QualityAuditReport]:
        """
        执行质量审查 - 合并基本规则、LLM结果和各阶段问题

        Args:
            instructions: AI视频指令
            stage_issues: 各阶段检测到的问题（来自各个智能体的detect_issues方法）

        Returns:
            质量审查报告
        """
        debug("开始质量审查")

        # 初始化阶段问题
        if stage_issues is None:
            stage_issues = {}

        try:
            # 1. 执行基本规则审查
            rule_report = self.rule_auditor.audit(instructions)
            info(f"基本规则审查完成，发现{len(rule_report.violations)}个问题")

            # 2. 执行LLM深度审查（如果启用）
            llm_report = None
            if self.llm_auditor:
                llm_report = self.llm_auditor.audit(instructions)
                info(f"LLM审查完成，发现{len(llm_report.violations) if llm_report else 0}个问题")

            # 3. 合并报告（包含各阶段问题）
            merged_report = self._merge_reports(rule_report, llm_report, instructions, stage_issues)

            # 4. 增强报告：添加问题分类和修复参数
            enhanced_report = self._enhance_report(merged_report, instructions, stage_issues)

            # 5. 后处理（计算分数、状态等）
            final_report = self._post_process_report(enhanced_report)

            info(f"质量审查完成: 状态={final_report.status.value}, 分数={final_report.score}%, 问题={len(final_report.violations)}个")
            return final_report

        except Exception as e:
            print_log_exception()
            error(f"质量审查异常: {e}")
            return self._create_fallback_report(instructions)

    def _merge_reports(self, rule_report: QualityAuditReport,
                       llm_report: Optional[QualityAuditReport],
                       instructions: AIVideoInstructions,
                       stage_issues: Dict[PipelineNode, List[BasicViolation]]) -> QualityAuditReport:
        """合并基本规则、LLM审查报告和各阶段问题"""

        # 创建合并报告（基于规则报告）
        merged = QualityAuditReport(
            project_info=instructions.project_info,
            checks=rule_report.checks.copy(),
            violations=rule_report.violations.copy(),
            stats=rule_report.stats.copy()
        )

        # 1. 合并LLM报告的问题
        if llm_report:
            for violation in llm_report.violations:
                merged.violations.append(violation)

            for check in llm_report.checks:
                merged.checks.append(check)

        # 2. 合并各阶段检测到的问题
        total_stage_issues = 0
        for node, issues in stage_issues.items():
            if issues:
                total_stage_issues += len(issues)
                for issue in issues:
                    # 设置问题来源节点
                    if not hasattr(issue, 'source_node') or not issue.source_node:
                        issue.source_node = node
                    merged.violations.append(issue)

                info(f"合并阶段 {node.value} 的问题: {len(issues)}个")

        if total_stage_issues > 0:
            info(f"总共合并各阶段问题: {total_stage_issues}个")

        # 3. 更新分数（如果合并了问题，需要重新计算）
        if total_stage_issues > 0:
            merged.score = self._calculate_weighted_score(merged.violations)

        return merged

    def _calculate_weighted_score(self, violations: List[BasicViolation]) -> float:
        """根据问题计算加权分数"""
        base_score = 100.0
        for violation in violations:
            penalty = self.severity_weights.get(violation.severity, 5)
            base_score -= penalty
        return max(0.0, min(100.0, base_score))

    def _enhance_report(self, report: QualityAuditReport,
                        instructions: AIVideoInstructions,
                        stage_issues: Dict[PipelineNode, List[BasicViolation]]) -> QualityAuditReport:
        """增强报告：添加问题分类和修复参数"""

        # 初始化分类
        issues_by_source = {
            PipelineNode.PARSE_SCRIPT: [],
            PipelineNode.SEGMENT_SHOT: [],
            PipelineNode.SPLIT_VIDEO: [],
            PipelineNode.CONVERT_PROMPT: [],
        }

        issues_by_type = {issue_type: [] for issue_type in IssueType}
        issues_by_severity = {
            SeverityLevel.INFO: [],
            SeverityLevel.WARNING: [],
            SeverityLevel.MODERATE: [],
            SeverityLevel.MAJOR: [],
            SeverityLevel.CRITICAL: [],
            SeverityLevel.ERROR: [],
        }

        # 分类报告中的每个问题
        for violation in report.violations:
            # 按类型分类
            if violation.issue_type in issues_by_type:
                issues_by_type[violation.issue_type].append(violation)
            else:
                issues_by_type[IssueType.OTHER].append(violation)

            # 按严重程度分类
            severity = violation.severity
            if severity in issues_by_severity:
                issues_by_severity[severity].append(violation)

            # 按来源分类（优先使用问题自带的source_node）
            source = getattr(violation, 'source_node', None)
            if not source:
                source = self.issue_source_mapping.get(violation.issue_type, PipelineNode.CONVERT_PROMPT)

            if source in issues_by_source:
                issues_by_source[source].append(violation)
            else:
                issues_by_source[PipelineNode.CONVERT_PROMPT].append(violation)

        # 生成修复参数（包含各阶段问题）
        repair_params_by_source = {}
        for source, issues in issues_by_source.items():
            if issues:
                repair_params_by_source[source] = QualityRepairParams(
                    fix_needed=True,
                    issue_count=len(issues),
                    issue_types=list(set([i.issue_type.value for i in issues if i.issue_type])),
                    fragments=list(set([i.fragment_id for i in issues if i.fragment_id])),
                    suggestions=self._collect_suggestions(issues),
                    severity_summary=self._get_severity_summary(issues),
                    issues=issues  # 保存完整问题列表供修复使用
                )

        # 记录各阶段问题统计
        stage_issue_stats = {}
        for node, issues in stage_issues.items():
            if issues:
                stage_issue_stats[node.value] = {
                    "count": len(issues),
                    "by_severity": self._get_severity_summary(issues),
                    "by_type": self._get_type_summary(issues)
                }

        # 添加到报告
        report.detailed_analysis = {
            "issues_by_source": {
                source.value: [v.dict() for v in issues]
                for source, issues in issues_by_source.items() if issues
            },
            "issues_by_type": {
                issue_type.value: [v.dict() for v in issues]
                for issue_type, issues in issues_by_type.items() if issues
            },
            "issues_by_severity": {
                severity.value: [v.dict() for v in issues]
                for severity, issues in issues_by_severity.items() if issues
            },
            "repair_params_by_source": {
                source.value: params.model_dump() for source, params in repair_params_by_source.items()
            },
            "stage_issue_stats": stage_issue_stats
        }

        # 保存到报告属性
        report.issues_source = issues_by_source
        report.repair_params = repair_params_by_source

        return report

    def _get_type_summary(self, issues: List[BasicViolation]) -> Dict[str, int]:
        """获取问题类型摘要"""
        summary = {}
        for issue in issues:
            type_str = issue.issue_type.value if issue.issue_type else "unknown"
            summary[type_str] = summary.get(type_str, 0) + 1
        return summary

    def _collect_suggestions(self, issues: List) -> Dict[str, List[str]]:
        """收集修复建议"""
        suggestions = {}
        for issue in issues:
            if issue.fragment_id and issue.suggestion:
                if issue.fragment_id not in suggestions:
                    suggestions[issue.fragment_id] = []
                suggestions[issue.fragment_id].append(issue.suggestion)
            elif issue.suggestion:
                # 全局建议
                if "global" not in suggestions:
                    suggestions["global"] = []
                suggestions["global"].append(issue.suggestion)
        return suggestions

    def _get_severity_summary(self, issues: List) -> Dict[str, int]:
        """获取严重程度摘要"""
        summary = {severity.value: 0 for severity in SeverityLevel}
        for issue in issues:
            summary[issue.severity.value] = summary.get(issue.severity.value, 0) + 1
        return summary

    def _post_process_report(self, report: QualityAuditReport) -> QualityAuditReport:
        """后处理报告"""
        # 计算统计信息
        severity_counts = {severity.value: 0 for severity in SeverityLevel}
        for violation in report.violations:
            severity_counts[violation.severity.value] += 1

        report.stats.update({
            "total_violations": len(report.violations),
            SeverityLevel.INFO.value: severity_counts[SeverityLevel.INFO.value],
            SeverityLevel.WARNING.value: severity_counts[SeverityLevel.WARNING.value],
            SeverityLevel.MODERATE.value: severity_counts[SeverityLevel.MODERATE.value],
            SeverityLevel.MAJOR.value: severity_counts[SeverityLevel.MAJOR.value],
            SeverityLevel.CRITICAL.value: severity_counts[SeverityLevel.CRITICAL.value],
            SeverityLevel.ERROR.value: severity_counts[SeverityLevel.ERROR.value],
        })

        # 计算质量分数
        base_score = 100.0
        for violation in report.violations:
            penalty = self.severity_weights.get(violation.severity, 5)
            base_score -= penalty
        report.score = max(0.0, min(100.0, base_score))

        # 确定最终状态
        if severity_counts[SeverityLevel.ERROR.value] > 0:
            report.status = AuditStatus.FAILED
        elif severity_counts[SeverityLevel.CRITICAL.value] > 0:
            report.status = AuditStatus.CRITICAL_ISSUES
        elif severity_counts[SeverityLevel.MAJOR.value] > 0:
            report.status = AuditStatus.MAJOR_ISSUES
        elif severity_counts[SeverityLevel.MODERATE.value] > 0:
            report.status = AuditStatus.MODERATE_ISSUES
        elif severity_counts[SeverityLevel.WARNING.value] > 0:
            report.status = AuditStatus.MINOR_ISSUES
        else:
            report.status = AuditStatus.PASSED

        report.conclusion = self._generate_conclusion(report)

        return report

    def _generate_conclusion(self, report: QualityAuditReport) -> str:
        """生成结论"""
        if report.status == AuditStatus.PASSED:
            return "审查通过，可以开始视频生成"

        issues_summary = []
        if report.stats.get(SeverityLevel.ERROR.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.ERROR.value]}个错误")
        if report.stats.get(SeverityLevel.CRITICAL.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.CRITICAL.value]}个严重问题")
        if report.stats.get(SeverityLevel.MAJOR.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.MAJOR.value]}个主要问题")
        if report.stats.get(SeverityLevel.MODERATE.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.MODERATE.value]}个中度问题")
        if report.stats.get(SeverityLevel.WARNING.value, 0) > 0:
            issues_summary.append(f"{report.stats[SeverityLevel.WARNING.value]}个警告")

        if issues_summary:
            return f"发现{', '.join(issues_summary)}，请根据建议修复"
        return "审查完成"

    def _create_fallback_report(self, instructions: AIVideoInstructions) -> QualityAuditReport:
        """创建回退报告"""
        fragment_count = len(instructions.fragments)

        return QualityAuditReport(
            project_info={
                "title": instructions.project_info.get("title", "未命名项目"),
                "fragment_count": fragment_count,
                "total_duration": instructions.project_info.get("total_duration", 0.0)
            },
            status=AuditStatus.FAILED,
            checks=[],
            violations=[],
            stats={SeverityLevel.ERROR.value: fragment_count},
            score=0.0
        )