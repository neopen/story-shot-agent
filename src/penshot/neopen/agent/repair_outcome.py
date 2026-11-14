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

from typing import Any, Dict, Iterable, List, Optional, Sequence

from penshot.logger import error

REPAIR_STATUS_NO_ISSUES = "no_issues"
REPAIR_STATUS_REPAIRED = "repaired"
REPAIR_STATUS_PARTIAL = "partial"
REPAIR_STATUS_NO_ACTION = "no_action_taken"


def _manual_entry(stage: str, issue: Any) -> Dict[str, Any]:
    """把一条未修复问题转换为可序列化的人工处理项"""
    return {
        "stage": stage,
        "issue_code": str(getattr(issue, "issue_code", "") or ""),
        "fragment_id": str(getattr(issue, "fragment_id", "") or ""),
        "reason": str(
            getattr(issue, "suggestion", "")
            or getattr(issue, "issue_desc", "")
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
    - 有问题且零动作 → ERROR 日志 + ``no_action_taken``，并把全部问题
      记为人工处理项（问题存在却未被修复，必须显式暴露）；
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
        code = str(getattr(issue, "issue_code", "") or "")
        issue_type = getattr(issue, "issue_type", None)
        type_value = str(getattr(issue_type, "value", issue_type) or "")
        return code in covered_codes or type_value in covered_types

    if issue_list and not actions:
        status = REPAIR_STATUS_NO_ACTION
        entries = [_manual_entry(stage, issue) for issue in issue_list]
        error(
            f"{stage}修复未执行任何操作：发现{len(issue_list)}个问题，0个修复操作，"
            f"已标记 {REPAIR_STATUS_NO_ACTION}"
        )
    else:
        forced_ids = {id(issue) for issue in (manual_issues or ())}
        entries = [_manual_entry(stage, issue) for issue in (manual_issues or ())]
        if auto_codes is not None or auto_types is not None:
            entries.extend(
                _manual_entry(stage, issue)
                for issue in issue_list
                if id(issue) not in forced_ids and not is_auto(issue)
            )
        if not issue_list:
            status = REPAIR_STATUS_NO_ISSUES
        elif entries:
            status = REPAIR_STATUS_PARTIAL
        else:
            status = REPAIR_STATUS_REPAIRED

    metadata["repair_status"] = status
    if entries:
        existing: List[Dict[str, Any]] = list(metadata.get("requires_manual_fix") or [])
        existing.extend(entries)
        metadata["requires_manual_fix"] = existing
    return status
