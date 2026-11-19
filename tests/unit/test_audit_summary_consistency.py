"""审计状态、评分与结论口径一致性

覆盖：检查项未通过但没有违规时，状态不得判 PASSED、评分不得满分、
结论不得输出“0 个警告问题”。
"""

from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
    AuditStatus,
    QualityAuditReport,
)
from penshot.neopen.agent.quality_auditor.rule_quality_auditor import RuleQualityAuditor
from penshot.neopen.agent.quality_auditor_agent import QualityAuditorAgent
from penshot.neopen.shot_config import ShotConfig


def _auditor() -> RuleQualityAuditor:
    return RuleQualityAuditor(ShotConfig())


def _checks(passed: int, failed: int):
    checks = [
        {"name": f"passed_{index}", "status": AuditStatus.PASSED}
        for index in range(passed)
    ]
    checks.extend(
        {"name": f"failed_{index}", "status": "failed"} for index in range(failed)
    )
    return checks


def _report(checks, violations=None) -> QualityAuditReport:
    return QualityAuditReport(checks=checks, violations=list(violations or []))


def test_base_audit_minor_issue_conclusion_mentions_failed_checks():
    """通过率不足时结论必须说明未通过的检查，而不是“0 个警告问题”"""
    report = _report(_checks(passed=8, failed=3))

    result = _auditor().post_process(report)

    assert result.status == AuditStatus.MINOR_ISSUES
    assert result.stats["failed_check_names"] == ["failed_0", "failed_1", "failed_2"]
    assert "3项检查未通过" in result.conclusion
    assert "0个警告问题" not in result.conclusion
    assert result.score == 73.0


def test_base_audit_passes_when_all_checks_pass():
    """全部检查通过且无违规时仍为 PASSED"""
    result = _auditor().post_process(_report(_checks(passed=5, failed=0)))

    assert result.status == AuditStatus.PASSED
    assert result.score == 100.0
    assert result.stats["failed_check_names"] == []


def test_wrapper_status_and_score_follow_failed_checks():
    """包装层不得用“无违规”覆盖检查失败：状态降级、分数按通过率计"""
    agent = QualityAuditorAgent(llm=None, config=ShotConfig(enable_llm=False))

    result = agent._post_process_report(_report(_checks(passed=8, failed=3)))

    assert result.status == AuditStatus.MINOR_ISSUES
    assert round(result.score, 1) == 72.7
    assert "3项检查未通过" in result.conclusion
    assert "0个警告问题" not in result.conclusion


def test_wrapper_passes_when_all_checks_pass():
    """包装层在全部检查通过且无违规时保持 PASSED"""
    agent = QualityAuditorAgent(llm=None, config=ShotConfig(enable_llm=False))

    result = agent._post_process_report(_report(_checks(passed=5, failed=0)))

    assert result.status == AuditStatus.PASSED
    assert result.score == 100.0