"""
@FileName: recall_status.py
@Description: 提示词模板召回状态判定纯策略（无 I/O、无 llama-index 依赖）
@Author: HiPeng
@Time: 2026/11/9

本模块只负责把「事实 + 分数 + 命中数」映射为 FR-041 规定的状态字符串，
便于 M0 用确定性断言锁定阈值行为；索引与检索的落地在 M5 接入。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Sequence

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
        global_scripts: 跨剧本候选来源（script_id -> 目录名）
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
