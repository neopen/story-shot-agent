"""
@FileName: ingestion_policy.py
@Description: 成功提示词入库统一策略（纯函数，无 I/O、无 llama-index 依赖）
@Author: HiPeng
@Time: 2026/11/10

两个入库点（quality_audit_node 与 WorkflowMemory）共用本策略，
保证 source 与真实审计状态一致（FR-045、AC-049），
并让首次运行的 cold_start_seed 例外只放宽分数门槛、不放宽严重缺陷。
"""

from dataclasses import dataclass
from typing import Iterable, Optional

# 入库来源：必须与真实审计状态一致，禁止把 minor_issues 标为 quality_audit_passed
SOURCE_QUALITY_AUDIT_PASSED = "quality_audit_passed"
SOURCE_QUALITY_AUDIT_SCORE = "quality_audit_score"
SOURCE_COLD_START_SEED = "cold_start_seed"

AUDIT_STATUS_PASSED = "passed"
AUDIT_STATUS_UNKNOWN = "unknown"

# 非 PASSED 结果的入库分数门槛（Spec 决策：不低于 90）
INGESTION_MIN_QUALITY_SCORE = 90.0

# 阻断入库的严重程度；cold_start_seed 例外同样适用
BLOCKING_SEVERITIES = frozenset({"major", "critical"})

REASON_PRE_AUDIT = "pre_audit"
REASON_SEVERE_VIOLATIONS = "severe_violations"
REASON_COLD_START = "cold_start"
REASON_AUDIT_PASSED = "audit_passed"
REASON_SCORE_THRESHOLD = "score_threshold"
REASON_BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class IngestionDecision:
    """一次审计结果的整批入库判定

    Attributes:
        allowed: 是否允许入库
        source: 入库来源标记；拒绝时为空串
        audit_status: 真实审计状态；无审计结果时为 unknown
        reason: 判定原因（闭合取值，便于日志与断言）
    """

    allowed: bool
    source: str
    audit_status: str
    reason: str


def _value(item: object) -> object:
    """取枚举的字符串值，兼容直接传入 str 枚举成员"""
    return getattr(item, "value", item)


def has_blocking_severity(severities: Iterable[str]) -> bool:
    """判断问题列表中是否含 major / critical"""
    return any(_value(item) in BLOCKING_SEVERITIES for item in severities)


def decide_ingestion(
    audit_status: Optional[str],
    quality_score: Optional[float],
    active_template_count: int,
    severities: Iterable[str] = (),
) -> IngestionDecision:
    """判定一批提示词是否入库，并给出诚实的 source 与 audit_status

    判定顺序：无审计结果 → 严重缺陷 → 首次运行放宽 → PASSED → 分数门槛。
    调用方按「一次审计」判定一次并应用于该批全部片段，
    避免首次运行入库第一条后因活跃数变为 1 而拒绝同批其余片段。

    Args:
        audit_status: 真实审计状态值；None 或空串表示尚未审计
        quality_score: 审计分数（0-100）；None 视为无分数证据
        active_template_count: 该剧本入库前的活跃模板数
        severities: 审计问题的严重程度列表

    Returns:
        整批入库判定
    """
    status = _value(audit_status) or ""
    if not status:
        # 审计前阶段不得入库：无真实审计状态就无法给出诚实的 source
        return IngestionDecision(False, "", AUDIT_STATUS_UNKNOWN, REASON_PRE_AUDIT)

    if has_blocking_severity(severities):
        return IngestionDecision(False, "", str(status), REASON_SEVERE_VIOLATIONS)

    if active_template_count <= 0:
        return IngestionDecision(
            True, SOURCE_COLD_START_SEED, str(status), REASON_COLD_START
        )

    if status == AUDIT_STATUS_PASSED:
        return IngestionDecision(
            True, SOURCE_QUALITY_AUDIT_PASSED, str(status), REASON_AUDIT_PASSED
        )

    score = float(quality_score) if quality_score is not None else 0.0
    if score >= INGESTION_MIN_QUALITY_SCORE:
        return IngestionDecision(
            True, SOURCE_QUALITY_AUDIT_SCORE, str(status), REASON_SCORE_THRESHOLD
        )

    return IngestionDecision(False, "", str(status), REASON_BELOW_THRESHOLD)
