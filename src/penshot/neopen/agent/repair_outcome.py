"""
@FileName: repair_outcome.py
@Description: 修复结果统一记录：零修复必须显式报错并标记人工处理
@Author: HiPeng
@Time: 2026/11/14

修复器被调用但策略表为空时，旧实现只打印"执行了0个修复操作"并正常返回，
质量分数却在后续合并中上升，形成"识别到问题但什么都没修"的假修复。
本模块让每个修复器在出口处统一记录 ``repair_status`` 与
``requires_manual_fix``，供最终输出声明真实修复结果。
"""

import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from penshot.logger import error, warning

REPAIR_STATUS_NO_ISSUES = "no_issues"
REPAIR_STATUS_REPAIRED = "repaired"
REPAIR_STATUS_PARTIAL = "partial"
REPAIR_STATUS_NO_ACTION = "no_action_taken"
REPAIR_STATUS_MANUAL = "manual_required"

# 数值越大越需要暴露：同一轮多次记录时保留最严重状态，避免后者覆盖前者
REPAIR_STATUS_PRIORITY = {
    REPAIR_STATUS_NO_ISSUES: 0,
    REPAIR_STATUS_REPAIRED: 1,
    REPAIR_STATUS_PARTIAL: 2,
    REPAIR_STATUS_MANUAL: 3,
    REPAIR_STATUS_NO_ACTION: 4,
}


def select_repair_status(statuses: Iterable[str]) -> str:
    """按严重程度聚合修复状态

    优先级：``no_action_taken > manual_required > partial > repaired > no_issues``。
    空输入返回空字符串，表示本轮没有可用结论。
    """
    candidates = [str(status) for status in statuses if status]
    if not candidates:
        return ""
    return max(
        candidates, key=lambda status: REPAIR_STATUS_PRIORITY.get(status, -1)
    )


def _issue_field(issue: Any, *names: str) -> Any:
    """从对象或字典中读取问题字段，兼容两种问题表示"""
    for name in names:
        value = issue.get(name) if isinstance(issue, dict) else getattr(issue, name, None)
        if value:
            return value
    return None


def _enum_value(value: Any) -> str:
    """取枚举的 value，普通值原样转字符串"""
    return str(getattr(value, "value", value) or "")


def manual_fix_entry(stage: str, issue: Any) -> Dict[str, Any]:
    """把一条未修复问题转换为可序列化的人工处理项（兼容对象与字典）"""
    return {
        "stage": stage,
        "issue_code": str(_issue_field(issue, "issue_code", "code") or ""),
        "fragment_id": str(_issue_field(issue, "fragment_id") or ""),
        "reason": str(
            _issue_field(issue, "suggestion", "issue_desc", "description", "message")
            or "修复器无对应策略"
        ),
    }


def record_repair_outcome(
    metadata: Dict[str, Any],
    stage: str,
    issues: Sequence[Any],
    actions: Sequence[str],
    auto_codes: Optional[Iterable[str]] = None,
    auto_types: Optional[Iterable[str]] = None,
    manual_issues: Optional[Sequence[Any]] = None,
) -> str:
    """记录一次修复的真实结果

    判定规则：
    - 无问题 → ``no_issues``；
    - 有问题、零动作且没有自动策略命中 → ``manual_required``（问题本身
      只能人工处理，不属于修复器失效）；
    - 有问题、零动作但存在自动策略命中 → ERROR 日志 + ``no_action_taken``
      （修复器具备能力却什么都没做，必须暴露）；
    - 有动作且仍有未覆盖问题 → ``partial``；
    - 有动作且全部问题在策略覆盖范围内 → ``repaired``。

    Args:
        metadata: 承载修复结论的 metadata（原地写入）
        stage: 修复阶段名，用于日志与人工处理项定位
        issues: 本次传入的问题列表
        actions: 实际执行的修复动作描述
        auto_codes: 可自动修复的 issue_code 集合
        auto_types: 可自动修复的 issue_type 集合；与 ``auto_codes`` 任一命中即可
        manual_issues: 即使命中了自动集合也确认未修复的问题，强制转人工处理

    Returns:
        修复状态字符串
    """
    issue_list = list(issues)
    metadata.setdefault("repair_history", [])

    covered_codes: set[str] = set(auto_codes or ())
    covered_types: set[str] = set(auto_types or ())

    def is_auto(issue: Any) -> bool:
        code = str(_issue_field(issue, "issue_code", "code") or "")
        type_value = _enum_value(_issue_field(issue, "issue_type", "type"))
        return code in covered_codes or type_value in covered_types

    if issue_list and not actions:
        entries = [manual_fix_entry(stage, issue) for issue in issue_list]
        auto_hits = [issue for issue in issue_list if is_auto(issue)]
        if auto_hits:
            status = REPAIR_STATUS_NO_ACTION
            error(
                f"{stage}修复未执行任何操作：发现{len(issue_list)}个问题，"
                f"其中{len(auto_hits)}个属于可自动修复问题，已标记 "
                f"{REPAIR_STATUS_NO_ACTION}"
            )
        else:
            status = REPAIR_STATUS_MANUAL
            warning(
                f"{stage}修复无自动策略可用：发现{len(issue_list)}个问题，"
                f"已标记 {REPAIR_STATUS_MANUAL}"
            )
    else:
        forced_ids = {id(issue) for issue in (manual_issues or ())}
        entries = [manual_fix_entry(stage, issue) for issue in (manual_issues or ())]
        if auto_codes is not None or auto_types is not None:
            entries.extend(
                manual_fix_entry(stage, issue)
                for issue in issue_list
                if id(issue) not in forced_ids and not is_auto(issue)
            )
        if not issue_list:
            status = REPAIR_STATUS_NO_ISSUES
        elif entries:
            status = REPAIR_STATUS_PARTIAL
        else:
            status = REPAIR_STATUS_REPAIRED

    # 保留本轮状态序列；单值字段按优先级取值，后记录的状态不得覆盖更严重的结论
    metadata.setdefault("repair_status_history", []).append(
        {"stage": stage, "status": status, "timestamp": time.time()}
    )
    metadata["repair_status"] = select_repair_status(
        [str(metadata.get("repair_status") or ""), status]
    )
    if entries:
        existing: List[Dict[str, Any]] = list(metadata.get("requires_manual_fix") or [])
        existing.extend(entries)
        metadata["requires_manual_fix"] = existing
    return status
