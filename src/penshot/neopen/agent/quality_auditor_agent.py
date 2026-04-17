"""
@FileName: quality_auditor_agent.py
@Description: 质量审查器 - 合并基本规则和LLM审查结果
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/25 21:59
"""
from typing import Optional, Dict, List, Any

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
                   stage_issues: Optional[Dict[PipelineNode, List[BasicViolation]]] = None,
                   historical_context: Optional[Dict[str, Any]] = None) -> Optional[QualityAuditReport]:
        """
        执行质量审查 - 合并基本规则、LLM结果和各阶段问题

        Args:
            instructions: AI视频指令
            stage_issues: 各阶段检测到的问题（来自各个智能体的detect_issues方法）
            historical_context: 历史上下文（可选，用于优化审查）

        Returns:
            质量审查报告
        """
        debug("开始质量审查")

        # 记录历史上下文信息
        if historical_context:
            debug("使用历史上下文优化质量审查")
            historical_audit_results = historical_context.get("historical_audit_results")
            if historical_audit_results:
                debug(f"加载了 {len(historical_audit_results)} 条历史审查记录")
            successful_repair_patterns = historical_context.get("successful_repair_patterns")
            if successful_repair_patterns:
                debug(f"加载了 {len(successful_repair_patterns) if isinstance(successful_repair_patterns, list) else 1} 条修复成功模式")

        # 初始化阶段问题
        if stage_issues is None:
            stage_issues = {}

        try:
            # 1. 执行基本规则审查
            rule_report = self.rule_auditor.audit(instructions)
            info(f"基本规则审查完成，发现{len(rule_report.violations)}个问题")

            # 2. 执行LLM深度审查（如果启用），传递历史上下文
            llm_report = None
            if self.llm_auditor:
                llm_report = self.llm_auditor.audit(instructions, historical_context)  # 传递历史上下文
                info(f"LLM审查完成，发现{len(llm_report.violations) if llm_report else 0}个问题")

            # 3. 合并报告（包含各阶段问题）
            merged_report = self._merge_reports(rule_report, llm_report, instructions, stage_issues)

            # 4. 增强报告：添加问题分类和修复参数
            enhanced_report = self._enhance_report(merged_report, instructions, stage_issues, historical_context)

            # 5. 后处理（计算分数、状态等）
            final_report = self._post_process_report(enhanced_report)

            info(f"质量审查完成: 状态={final_report.status.value}, 分数={final_report.score}%, 问题={len(final_report.violations)}个")
            return final_report

        except Exception as e:
            print_log_exception()
            error(f"质量审查异常: {e}")
            return self._create_fallback_report(instructions)


    def _enhance_report(self, report: QualityAuditReport,
                        instructions: AIVideoInstructions,
                        stage_issues: Dict[PipelineNode, List[BasicViolation]],
                        historical_context: Optional[Dict[str, Any]] = None) -> QualityAuditReport:
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
            # 确保获取 issue_type
            issue_type = self._get_issue_type(violation)
            severity = self._get_severity(violation)
            source = self._get_source_node(violation)

            # 按类型分类
            if issue_type in issues_by_type:
                issues_by_type[issue_type].append(violation)
            else:
                issues_by_type[IssueType.OTHER].append(violation)

            # 按严重程度分类
            if severity in issues_by_severity:
                issues_by_severity[severity].append(violation)

            # 按来源分类
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

        # ========== 新增：使用历史上下文优化修复参数 ==========
        if historical_context:
            # 获取历史成功修复模式
            successful_repair_patterns = historical_context.get("successful_repair_patterns")
            if successful_repair_patterns:
                # 根据历史成功模式优化修复建议
                self._optimize_repair_params_with_history(repair_params_by_source, successful_repair_patterns)

            # 获取历史审计结果
            historical_audit_results = historical_context.get("historical_audit_results")
            if historical_audit_results:
                # 根据历史结果调整问题严重程度
                self._adjust_severity_with_history(repair_params_by_source, historical_audit_results)

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
            "stage_issue_stats": stage_issue_stats,
            "historical_context_applied": historical_context is not None  # 标记是否使用了历史上下文
        }

        # 保存到报告属性
        report.issues_source = issues_by_source
        report.repair_params = repair_params_by_source

        return report

    def _optimize_repair_params_with_history(self, repair_params: Dict, successful_patterns: List):
        """
        根据历史成功修复模式优化修复参数

        Args:
            repair_params: 当前修复参数
            successful_patterns: 历史成功修复模式列表
        """
        if not successful_patterns:
            return

        debug(f"使用 {len(successful_patterns)} 条历史成功模式优化修复建议")

        # 分析成功模式中的问题类型频率
        pattern_issue_counts = {}
        for pattern in successful_patterns:
            if isinstance(pattern, dict):
                issue_types = pattern.get("issue_types", [])
                for issue_type in issue_types:
                    pattern_issue_counts[issue_type] = pattern_issue_counts.get(issue_type, 0) + 1

        # 对于高频问题，增加修复优先级
        high_freq_issues = {t: c for t, c in pattern_issue_counts.items() if c > 2}
        if high_freq_issues:
            debug(f"高频问题模式: {high_freq_issues}")

            # 为高频问题添加额外建议
            for source, params in repair_params.items():
                for issue_type in params.issue_types:
                    if issue_type in high_freq_issues:
                        if "global" not in params.suggestions:
                            params.suggestions["global"] = []
                        params.suggestions["global"].append(
                            f"根据历史经验，此问题频繁出现，建议优先修复（出现{high_freq_issues[issue_type]}次）"
                        )

    def _adjust_severity_with_history(self, repair_params: Dict, historical_results: List):
        """
        根据历史审计结果调整问题严重程度

        Args:
            repair_params: 当前修复参数
            historical_results: 历史审计结果列表
        """
        if not historical_results:
            return

        debug(f"使用 {len(historical_results)} 条历史审计结果调整严重程度")

        # 分析历史中哪些问题导致失败
        critical_issue_types = set()
        for result in historical_results[-20:]:  # 最近20条
            if result.get("status") in ["failed", "critical"]:
                violations = result.get("violations", [])
                for v in violations:
                    if isinstance(v, dict):
                        issue_type = v.get("issue_type", {}).get("value", "unknown")
                    else:
                        issue_type = getattr(v, "issue_type", "unknown")
                        if hasattr(issue_type, "value"):
                            issue_type = issue_type.value
                    critical_issue_types.add(issue_type)

        if critical_issue_types:
            debug(f"历史严重问题类型: {critical_issue_types}")

            # 提升严重问题的修复优先级
            for source, params in repair_params.items():
                for issue_type in params.issue_types:
                    if issue_type in critical_issue_types:
                        # 添加高优先级标记
                        if "global" not in params.suggestions:
                            params.suggestions["global"] = []
                        params.suggestions["global"].append(
                            f"此问题历史中曾导致失败，建议优先修复"
                        )

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
                    # 确保 issue 是 BasicViolation 对象
                    if isinstance(issue, dict):
                        # 如果是字典，转换为 BasicViolation 对象
                        try:
                            basic_issue = BasicViolation(
                                rule_code=issue.get("rule_code", ""),
                                rule_name=issue.get("rule_name", ""),
                                issue_type=IssueType(issue.get("issue_type", IssueType.OTHER.value)),
                                source_node=PipelineNode(issue.get("source_node", node.value)),
                                description=issue.get("description", ""),
                                severity=SeverityLevel(issue.get("severity", SeverityLevel.WARNING.value)),
                                fragment_id=issue.get("fragment_id"),
                                suggestion=issue.get("suggestion")
                            )
                            # 设置来源节点
                            if not hasattr(basic_issue, 'source_node') or not basic_issue.source_node:
                                basic_issue.source_node = node
                            merged.violations.append(basic_issue)
                        except Exception as e:
                            error(f"转换问题为 BasicViolation 失败: {e}")
                            print_log_exception()
                            continue
                    else:
                        # 已经是对象，直接使用
                        if not hasattr(issue, 'source_node') or not issue.source_node:
                            issue.source_node = node
                        merged.violations.append(issue)

                info(f"合并阶段 {node.value} 的问题: {len(issues)}个")

        if total_stage_issues > 0:
            debug(f"总共合并各阶段问题: {total_stage_issues}个")
            # 重新计算分数
            merged.score = self._calculate_weighted_score(merged.violations)

        return merged

    def _calculate_weighted_score(self, violations: List) -> float:
        """
        根据问题计算加权分数

        Args:
            violations: BasicViolation 对象列表或字典列表
        """
        base_score = 100.0

        for violation in violations:
            try:
                # 处理字典类型
                if isinstance(violation, dict):
                    severity = violation.get("severity")
                    # 如果 severity 是字典，可能包含 value 属性
                    if hasattr(severity, 'value'):
                        severity = severity.value
                    elif isinstance(severity, dict):
                        severity = severity.get("value", "warning")
                    else:
                        severity = str(severity) if severity else "warning"
                else:
                    # 处理 BasicViolation 对象
                    severity = violation.severity
                    if hasattr(severity, 'value'):
                        severity = severity.value
                    elif hasattr(severity, '__str__'):
                        severity = str(severity)

                # 获取权重
                penalty = self.severity_weights.get(severity, 5)
                base_score -= penalty

            except Exception as e:
                debug(f"计算分数时出错: {e}, violation类型: {type(violation)}")
                base_score -= 5  # 默认扣5分

        return max(0.0, min(100.0, base_score))

    def _get_type_summary(self, issues: List[BasicViolation]) -> Dict[str, int]:
        """获取问题类型摘要"""
        summary = {}
        for issue in issues:
            if isinstance(issue, dict):
                issue_type = issue.get("issue_type")
                if isinstance(issue_type, dict):
                    type_str = issue_type.get("value", "unknown")
                elif isinstance(issue_type, str):
                    type_str = issue_type
                else:
                    type_str = "unknown"
            else:
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
            # 判断 issue 是字典还是对象
            if isinstance(issue, dict):
                severity_value = issue.get("severity")
                # 处理 severity 可能是字典或字符串的情况
                if isinstance(severity_value, dict):
                    severity_str = severity_value.get("value", "warning")
                elif isinstance(severity_value, str):
                    severity_str = severity_value
                else:
                    severity_str = "warning"
            else:
                # 对象类型
                severity_value = issue.severity
                if hasattr(severity_value, 'value'):
                    severity_str = severity_value.value
                else:
                    severity_str = str(severity_value) if severity_value else "warning"

            summary[severity_str] = summary.get(severity_str, 0) + 1
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

    def _get_issue_type(self, violation) -> IssueType:
        """获取问题类型"""
        if isinstance(violation, dict):
            issue_type = violation.get("issue_type")
            if isinstance(issue_type, dict):
                return IssueType(issue_type.get("value", "other"))
            if isinstance(issue_type, str):
                try:
                    return IssueType(issue_type)
                except ValueError:
                    return IssueType.OTHER
            return IssueType.OTHER
        else:
            return violation.issue_type

    def _get_severity(self, violation) -> SeverityLevel:
        """获取严重程度"""
        if isinstance(violation, dict):
            severity = violation.get("severity")
            if isinstance(severity, dict):
                return SeverityLevel(severity.get("value", "warning"))
            if isinstance(severity, str):
                try:
                    return SeverityLevel(severity)
                except ValueError:
                    return SeverityLevel.WARNING
            return SeverityLevel.WARNING
        else:
            return violation.severity

    def _get_source_node(self, violation) -> PipelineNode:
        """获取来源节点"""
        if isinstance(violation, dict):
            source = violation.get("source_node")
            if source:
                if isinstance(source, str):
                    try:
                        return PipelineNode(source)
                    except ValueError:
                        pass
                return PipelineNode.CONVERT_PROMPT
            return PipelineNode.CONVERT_PROMPT
        else:
            source = getattr(violation, 'source_node', None)
            if source:
                return source
            return self.issue_source_mapping.get(violation.issue_type, PipelineNode.CONVERT_PROMPT)