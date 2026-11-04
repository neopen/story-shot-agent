"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: continuity_report.py
@Description: 连续性检查报告 - 汇总每轮检查、修复动作与修复前后对比
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/3
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .continuity_guardian_models import ContinuityCheckResult

# 单个报告最多保留的轮次/问题/修复条目数，避免报告无限膨胀
MAX_REPORT_ROUNDS = 20
MAX_ROUND_ISSUES = 50
MAX_ROUND_REPAIRS = 20
MAX_CONTRACT_VIOLATIONS = 20


def _text(value: Any) -> str:
    """安全读取文本（非字符串返回空串）"""
    return value.strip() if isinstance(value, str) else ""


def enum_value(value: Any) -> str:
    """把枚举或普通值统一转换为字符串"""
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def issue_to_dict(issue: Any) -> Dict[str, Any]:
    """把 ContinuityIssue（或等价字典）转换为报告所需的结构化字典"""
    if isinstance(issue, dict):
        raw = dict(issue)
    elif hasattr(issue, "model_dump"):
        raw = issue.model_dump()
    else:
        raw = {"description": str(issue)}

    result: Dict[str, Any] = {
        "id": raw.get("id"),
        "type": enum_value(raw.get("type")) or "unknown",
        "severity": enum_value(raw.get("severity")) or "moderate",
        "description": _text(raw.get("description")),
        "fragment_id": raw.get("fragment_id"),
        "shot_id": raw.get("shot_id"),
        "scene_id": raw.get("scene_id"),
        "position": raw.get("position"),
        "suggestion": raw.get("suggestion"),
        "auto_fixable": raw.get("auto_fixable"),
        "source_stage": enum_value(raw.get("source_stage")) or None,
        "timestamp": raw.get("timestamp"),
    }
    return {key: value for key, value in result.items() if value is not None}


def issue_signature(issue: Any) -> str:
    """生成跨轮次可比对的问题签名（类型 + 位置）

    连续性问题的 id 每轮都会重新生成，无法直接用于判断“是否已修复”，
    因此使用类型与位置信息作为稳定签名。
    """
    data = issue_to_dict(issue)
    return "|".join(
        [
            data.get("type", "unknown"),
            _text(data.get("fragment_id")),
            _text(data.get("shot_id")),
            _text(data.get("scene_id")),
        ]
    )


def summarize_issues(issues: Iterable[Any]) -> Dict[str, Dict[str, int]]:
    """按类型与严重程度统计问题数量"""
    items = list(issues or [])
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}

    for issue in items:
        data = issue_to_dict(issue)
        issue_type = data.get("type", "unknown")
        severity = data.get("severity", "moderate")
        by_type[issue_type] = by_type.get(issue_type, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    return {"by_type": by_type, "by_severity": by_severity}


def summarize_contract_violations(
    violations: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """汇总契约违规项（总数、按阶段、按类型与最近条目）"""
    items = [v for v in (violations or []) if isinstance(v, dict)]
    by_stage: Dict[str, int] = {}
    by_type: Dict[str, int] = {}

    for violation in items:
        stage = _text(violation.get("stage")) or "unknown"
        violation_type = _text(violation.get("type")) or "unknown"
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_type[violation_type] = by_type.get(violation_type, 0) + 1

    return {
        "total": len(items),
        "by_stage": by_stage,
        "by_type": by_type,
        "items": items[-MAX_CONTRACT_VIOLATIONS:],
    }


def build_repair_entries(
    repair_params: Optional[Dict[Any, Any]],
    violations_by_stage: Optional[Dict[Any, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """把各阶段的修复参数转换为报告条目

    Args:
        repair_params: {PipelineNode: QualityRepairParams}
        violations_by_stage: 契约违规项按阶段分组，用于标注该阶段契约修复数量
    """
    entries: List[Dict[str, Any]] = []
    if not repair_params:
        return entries

    pending_violations = dict(violations_by_stage or {})

    for stage, params in repair_params.items():
        if params is None:
            continue

        stage_name = enum_value(stage) or "unknown"
        stage_violations = (
            pending_violations.get(stage_name) or pending_violations.get(stage) or []
        )
        suggestions = {
            str(key): [str(item) for item in (value or [])]
            for key, value in (getattr(params, "suggestions", None) or {}).items()
        }

        entries.append(
            {
                "stage": stage_name,
                "issue_count": getattr(params, "issue_count", 0),
                "issue_types": [
                    enum_value(item)
                    for item in (getattr(params, "issue_types", None) or [])
                ],
                "fragments": list(getattr(params, "fragments", None) or []),
                "severity_summary": dict(
                    getattr(params, "severity_summary", None) or {}
                ),
                "suggestions": suggestions,
                "contract_violation_count": len(stage_violations),
            }
        )

    return entries


def build_round_record(
    check_result: ContinuityCheckResult,
    *,
    round_index: int,
    retry_count: int,
    max_retries: int,
    phase: str,
    issues_by_stage: Optional[Dict[str, int]] = None,
    repairs: Optional[List[Dict[str, Any]]] = None,
    repair_stages: Optional[List[str]] = None,
    contract_violations: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构建单轮连续性检查记录

    Args:
        check_result: 本轮连续性检查结果
        round_index: 轮次序号（从 1 开始）
        retry_count: 本轮开始前的连续性修复重试次数
        max_retries: 最大连续性修复重试次数
        phase: 本轮结论：passed | needs_repair | retry_exhausted
        issues_by_stage: 问题按来源阶段统计
        repairs: 本轮生成的修复动作
        repair_stages: 本轮触发的修复阶段
        contract_violations: 当前累计的契约违规项
    """
    issues = list(check_result.issues or [])
    type_summary = summarize_issues(issues)

    return {
        "round": round_index,
        "phase": phase,
        "passed": bool(check_result.passed and check_result.total_issues == 0),
        "total_issues": check_result.total_issues,
        "critical": check_result.critical_count,
        "major": check_result.major_count,
        "moderate": check_result.moderate_count,
        "minor": check_result.minor_count,
        "issues_by_type": type_summary["by_type"],
        "issues_by_severity": type_summary["by_severity"],
        "issues_by_stage": dict(issues_by_stage or {}),
        "issues": [issue_to_dict(issue) for issue in issues[:MAX_ROUND_ISSUES]],
        "repair_stages": sorted(set(repair_stages or [])),
        "repairs": list(repairs or [])[:MAX_ROUND_REPAIRS],
        "contract_violations": summarize_contract_violations(contract_violations),
        "retry_count": retry_count,
        "max_retries": max_retries,
        "timestamp": datetime.now().isoformat(),
    }


def build_continuity_report(
    *,
    task_id: str,
    script_id: str,
    rounds: Optional[Iterable[Dict[str, Any]]] = None,
    current_issues: Optional[Iterable[Any]] = None,
    repair_params: Optional[Dict[Any, Any]] = None,
    contract_violations: Optional[Iterable[Dict[str, Any]]] = None,
    continuity_passed: bool = False,
    retry_count: int = 0,
    max_retries: int = 3,
    needs_continuity_repair: bool = False,
) -> Dict[str, Any]:
    """构建完整的连续性报告

    报告同时覆盖：
    - 每轮检查的问题与严重程度
    - 每轮触发的修复阶段、修复建议与契约违规
    - 修复前后问题数量对比
    - 最终结论（通过 / 修复后通过 / 需人工处理）
    """
    round_items = [dict(item) for item in (rounds or []) if isinstance(item, dict)][
        -MAX_REPORT_ROUNDS:
    ]

    current = list(current_issues or [])
    current_summary = summarize_issues(current)
    last_round = round_items[-1] if round_items else None

    latest_issues = [issue_to_dict(issue) for issue in current[:MAX_ROUND_ISSUES]]
    if not latest_issues and last_round is not None:
        latest_issues = list(last_round.get("issues") or [])

    issues_by_type = current_summary["by_type"]
    issues_by_severity = current_summary["by_severity"]
    if not issues_by_type and last_round is not None:
        issues_by_type = dict(last_round.get("issues_by_type") or {})
        issues_by_severity = dict(last_round.get("issues_by_severity") or {})

    # 每轮修复动作（附带轮次信息）
    repair_actions: List[Dict[str, Any]] = []
    for item in round_items:
        for repair in item.get("repairs") or []:
            if not isinstance(repair, dict):
                continue
            action = dict(repair)
            action.setdefault("round", item.get("round"))
            action.setdefault("phase", item.get("phase"))
            repair_actions.append(action)

    # 当前仍挂在工作流上的修复参数（通常为最近一轮）
    latest_repair_params = build_repair_entries(repair_params)

    first_issue_round = next(
        (item for item in round_items if int(item.get("total_issues") or 0) > 0),
        None,
    )
    initial_issue_count = (
        int(first_issue_round.get("total_issues") or 0) if first_issue_round else 0
    )
    final_issue_count = (
        int(last_round.get("total_issues") or 0) if last_round else len(current)
    )
    resolved_issue_count = max(0, initial_issue_count - final_issue_count)

    initial_types = set((first_issue_round or {}).get("issues_by_type") or {})
    final_types = set((last_round or {}).get("issues_by_type") or {})
    resolved_types = sorted(initial_types - final_types)
    remaining_types = sorted(final_types)

    passed = bool(continuity_passed and not current)
    final_status = _derive_final_status(
        passed=passed,
        rounds=round_items,
        needs_continuity_repair=needs_continuity_repair,
    )

    return {
        "task_id": task_id,
        "script_id": script_id,
        "passed": passed,
        "continuity_passed": passed,
        "final_status": final_status,
        "total_continuity_issues": len(current)
        if current
        else (last_round or {}).get("total_issues", 0),
        "issues_by_type": issues_by_type,
        "issues_by_severity": issues_by_severity,
        "issues": latest_issues,
        "continuity_retry_count": max(
            [int(item.get("retry_count") or 0) for item in round_items] + [retry_count]
        ),
        "max_continuity_retries": max_retries,
        "needs_continuity_repair": bool(needs_continuity_repair),
        "round_count": len(round_items),
        "rounds": round_items,
        "repair_count": len(repair_actions),
        "repairs": repair_actions,
        "latest_repair_params": latest_repair_params,
        "contract_violations": summarize_contract_violations(contract_violations),
        "comparison": {
            "initial_issue_count": initial_issue_count,
            "final_issue_count": final_issue_count,
            "resolved_issue_count": resolved_issue_count,
            "issue_count_trend": [
                int(item.get("total_issues") or 0) for item in round_items
            ],
            "resolved_types": resolved_types,
            "remaining_types": remaining_types,
            "rounds_with_issues": sum(
                1 for item in round_items if int(item.get("total_issues") or 0) > 0
            ),
            "repair_rounds": sum(
                1 for item in round_items if item.get("phase") == "needs_repair"
            ),
        },
        "summary": {
            "passed": passed,
            "rounds": len(round_items),
            "issues_detected": sum(
                int(item.get("total_issues") or 0) for item in round_items
            ),
            "issues_remaining": final_issue_count,
            "issues_resolved": resolved_issue_count,
            "repairs": len(repair_actions),
            "contract_violations": len(list(contract_violations or [])),
        },
        "generated_at": datetime.now().isoformat(),
    }


def _derive_final_status(
    *,
    passed: bool,
    rounds: List[Dict[str, Any]],
    needs_continuity_repair: bool,
) -> str:
    """根据轮次记录推导最终状态"""
    if not rounds:
        return "not_checked"
    if needs_continuity_repair:
        return "needs_repair"
    if rounds[-1].get("phase") == "retry_exhausted":
        return "needs_human_review"
    if passed:
        had_issues = any(int(item.get("total_issues") or 0) > 0 for item in rounds)
        return "passed_after_repair" if had_issues else "passed"
    return "unresolved"


def build_repair_history(
    *,
    task_id: str,
    script_id: str,
    rounds: Optional[Iterable[Dict[str, Any]]] = None,
    repair_params: Optional[Dict[Any, Any]] = None,
) -> Dict[str, Any]:
    """构建修复历史报告（当前主要覆盖连续性驱动的修复动作）"""
    round_items = [dict(item) for item in (rounds or []) if isinstance(item, dict)][
        -MAX_REPORT_ROUNDS:
    ]

    actions: List[Dict[str, Any]] = []
    for item in round_items:
        for repair in item.get("repairs") or []:
            if not isinstance(repair, dict):
                continue
            action = dict(repair)
            action["round"] = item.get("round")
            action["phase"] = item.get("phase")
            action["source"] = "continuity"
            actions.append(action)

    by_stage: Dict[str, Dict[str, Any]] = {}
    for action in actions:
        stage = _text(action.get("stage")) or "unknown"
        bucket = by_stage.setdefault(stage, {"count": 0, "actions": []})
        bucket["count"] += 1
        bucket["actions"].append(action)

    latest_params = build_repair_entries(repair_params)
    for entry in latest_params:
        stage = _text(entry.get("stage")) or "unknown"
        bucket = by_stage.setdefault(stage, {"count": 0, "actions": []})
        bucket["latest_params"] = entry

    return {
        "task_id": task_id,
        "script_id": script_id,
        "repair_count": len(actions),
        "repairs": by_stage,
        "repair_actions": actions,
        "continuity_rounds": [
            {
                "round": item.get("round"),
                "phase": item.get("phase"),
                "total_issues": item.get("total_issues"),
                "repair_stages": item.get("repair_stages") or [],
            }
            for item in round_items
        ],
        "summary": {
            "repair_rounds": sum(
                1 for item in round_items if item.get("phase") == "needs_repair"
            ),
            "repair_actions": len(actions),
            "stages": sorted(by_stage.keys()),
        },
        "generated_at": datetime.now().isoformat(),
    }
