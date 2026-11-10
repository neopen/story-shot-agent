"""
@FileName: recall_status.py
@Description: 提示词模板召回状态判定纯策略（无 I/O、无 llama-index 依赖）
@Author: HiPeng
@Time: 2026/11/9

本模块只负责把「事实 + 分数 + 命中数」映射为 FR-041 规定的状态字符串，
并按 FR-040 汇总 anchor_recall 元数据；不含 I/O 与 llama-index 依赖，
便于用确定性断言锁定阈值与统计口径。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

STATUS_HIT = "hit"
STATUS_HIT_GLOBAL = "hit_global"
STATUS_FIRST_RUN_NO_HISTORY = "first_run_no_history"
STATUS_FIRST_RUN_GLOBAL_HIT = "first_run_global_hit"
STATUS_EMPTY_TEMPLATES = "empty_templates"
STATUS_INDEX_UNAVAILABLE = "index_unavailable"
STATUS_INDEX_LOAD_FAILED = "index_load_failed"
STATUS_CACHE_INDEX_MISMATCH = "cache_index_mismatch"
STATUS_EMBEDDINGS_UNAVAILABLE = "embeddings_unavailable"
STATUS_ALL_BELOW_THRESHOLD = "all_below_threshold"
STATUS_RETRIEVAL_ERROR = "retrieval_error"


@dataclass
class RecallFacts:
    """召回判定所需的只读事实快照

    Attributes:
        template_count: 当前剧本缓存模板总数（含 legacy）
        active_template_count: 可参与召回的活跃模板数
        legacy_templates: 被排除的 legacy 模板数
        has_index: 是否存在可用索引
        index_docs: 索引中的文档数
        index_load_failed: 索引加载是否失败
        cache_index_mismatch: 缓存与索引数量是否不一致
        embeddings_available: 嵌入模型是否可用
        retrieval_error: 检索异常信息（非空即异常）
        global_scripts: 跨剧本候选来源（script_id -> 模板目录路径）
    """

    template_count: int = 0
    active_template_count: int = 0
    legacy_templates: int = 0
    has_index: bool = False
    index_docs: int = 0
    index_load_failed: bool = False
    cache_index_mismatch: bool = False
    embeddings_available: bool = True
    retrieval_error: str = ""
    global_scripts: Dict[str, str] = field(default_factory=dict)


def count_hits(scores: Sequence[float], threshold: float) -> int:
    """统计达到阈值的分数个数（边界取 `>=`，与检索过滤口径一致）"""
    return sum(1 for score in scores if float(score) >= threshold)


def summarize_scores(scores: Sequence[float], top_k: int) -> Dict[str, Any]:
    """生成可直接并入 `anchor_recall` 的分数摘要"""
    values = [float(score) for score in scores]
    return {
        "count": len(values),
        "min_score": min(values) if values else 0.0,
        "max_score": max(values) if values else 0.0,
        "top_k": top_k,
    }


def derive_status(
    facts: RecallFacts,
    scores: Sequence[float],
    local_hits: int,
    global_hits: int,
    include_global: bool,
) -> str:
    """按 FR-041/043 的优先级推导召回状态

    Args:
        facts: 召回事实快照
        scores: 实际检索到的分数（本地 + 跨剧本）
        local_hits: 同剧本命中数
        global_hits: 跨剧本命中数
        include_global: 是否启用跨剧本召回

    Returns:
        FR-041 规定的状态字符串
    """
    if facts.retrieval_error:
        return STATUS_RETRIEVAL_ERROR

    if not facts.embeddings_available:
        return STATUS_EMBEDDINGS_UNAVAILABLE

    # 活跃模板为 0 时区分“有历史但全被排除”与“真正首次运行”
    if facts.active_template_count == 0:
        if facts.template_count > 0:
            return STATUS_EMPTY_TEMPLATES
        if include_global and global_hits > 0:
            return STATUS_FIRST_RUN_GLOBAL_HIT
        return STATUS_FIRST_RUN_NO_HISTORY

    if facts.index_load_failed and not facts.has_index:
        return STATUS_INDEX_LOAD_FAILED

    if not facts.has_index:
        return STATUS_INDEX_UNAVAILABLE

    if local_hits > 0:
        return STATUS_HIT

    if include_global and global_hits > 0:
        return STATUS_HIT_GLOBAL

    if facts.cache_index_mismatch:
        return STATUS_CACHE_INDEX_MISMATCH

    # 无命中且无其它异常：统一归为阈值未达标，保持状态枚举闭合
    return STATUS_ALL_BELOW_THRESHOLD


# 多查询聚合优先级：先反映可用召回结果，再按失败严重度排序
_AGGREGATE_PRIORITY = (
    STATUS_HIT,
    STATUS_FIRST_RUN_GLOBAL_HIT,
    STATUS_HIT_GLOBAL,
    STATUS_RETRIEVAL_ERROR,
    STATUS_EMBEDDINGS_UNAVAILABLE,
    STATUS_INDEX_LOAD_FAILED,
    STATUS_INDEX_UNAVAILABLE,
    STATUS_EMPTY_TEMPLATES,
    STATUS_CACHE_INDEX_MISMATCH,
    STATUS_ALL_BELOW_THRESHOLD,
    STATUS_FIRST_RUN_NO_HISTORY,
)


def aggregate_status(statuses: Sequence[str], has_history: bool = False) -> str:
    """把逐片段查询的状态聚合为单个 `anchor_recall.status`（FR-040/041）

    有命中时优先反映命中，个别来源异常不掩盖可用召回；无命中时取最严重的
    失败原因；一次查询都没执行时按知识库是否有历史回退，保持枚举闭合。
    完全不具备召回前置条件（无契约/无片段/无模板管理器）时状态为空串，
    因为 FR-041 的枚举全部描述检索结果，不能用来表示“未尝试召回”。

    Args:
        statuses: 每次实际查询返回的状态
        has_history: 知识库是否存在历史模板或可用索引（含跨剧本）

    Returns:
        FR-041 闭合枚举中的状态字符串；知识库不可观测时为 ``""``
    """
    observed = set(statuses)
    for status in _AGGREGATE_PRIORITY:
        if status in observed:
            return status
    return STATUS_ALL_BELOW_THRESHOLD if has_history else ""


def build_anchor_recall(
    fragments: int,
    queries: int,
    queries_skipped: int,
    hits: int,
    injected: int,
    diagnostics: Sequence[Dict[str, Any]],
    top_k: int,
    kb: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按 FR-040 汇总 `metadata.anchor_recall`（纯函数，不做 I/O）

    所有计数来自调用方实际执行的查询构造与检索结果，分数取各次查询的
    实测极值，知识库快照取最后一次诊断（含索引重建后的真实数量）。

    Args:
        fragments: 片段总数
        queries: 成功构造出锚点查询的片段数
        queries_skipped: 因无锚点被跳过的片段数
        hits: 去重后召回到的提示词条数
        injected: 实际注入转换上下文的条数
        diagnostics: 每次查询的检索诊断（`search_similar_detailed` 第二返回值）
        top_k: 单次检索名额
        kb: 无可用诊断时的知识库快照回退

    Returns:
        anchor_recall 字典
    """
    snapshots = [item for item in diagnostics if isinstance(item, dict)]
    kb_snapshot: Dict[str, Any] = dict(kb or {})
    for item in snapshots:
        if item.get("kb"):
            kb_snapshot = dict(item["kb"])

    # 一次检索都没执行时不产出任何召回结论，避免伪造“首次运行/无模板/低于阈值”
    if not snapshots:
        return {
            "fragments": fragments,
            "queries": queries,
            "queries_skipped": queries_skipped,
            "attempted": 0,
            "hits": hits,
            "injected": injected,
            "status": "",
            "kb": kb_snapshot,
            "min_score": 0.0,
            "max_score": 0.0,
            "top_k": top_k,
            "error": "",
        }

    retrieved = [item for item in snapshots if int(item.get("retrieved", 0) or 0) > 0]
    has_history = bool(
        kb_snapshot.get("template_count", 0)
        or kb_snapshot.get("has_index")
        or kb_snapshot.get("global_template_count", 0)
    )
    statuses = [str(item["status"]) for item in snapshots if item.get("status")]

    anchor_recall: Dict[str, Any] = {
        "fragments": fragments,
        "queries": queries,
        "queries_skipped": queries_skipped,
        "attempted": sum(int(item.get("attempted", 0) or 0) for item in snapshots),
        "hits": hits,
        "injected": injected,
        "status": aggregate_status(statuses, has_history),
        "kb": kb_snapshot,
        "min_score": min(
            (float(item.get("min_score", 0.0) or 0.0) for item in retrieved),
            default=0.0,
        ),
        "max_score": max(
            (float(item.get("max_score", 0.0) or 0.0) for item in retrieved),
            default=0.0,
        ),
        "top_k": top_k,
        "error": next(
            (str(item["error"]) for item in snapshots if item.get("error")), ""
        ),
    }

    repair = next(
        (
            item["last_repair"]
            for item in reversed(snapshots)
            if item.get("last_repair")
        ),
        None,
    )
    if repair:
        anchor_recall["rebuilt"] = {
            "before": (repair.get("before") or {}).get("index_docs", 0),
            "after": (repair.get("after") or {}).get("index_docs", 0),
        }
    return anchor_recall
