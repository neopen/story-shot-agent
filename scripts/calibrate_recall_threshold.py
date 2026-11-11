"""
@FileName: calibrate_recall_threshold.py
@Description: 0.4.4 召回阈值只读校准脚本（M0 门禁）
@Author: HiPeng
@Time: 2026/11/9

用途：
    在缺陷样本上重建一致性契约，用 11 条锚点查询对「迁移前 116 条历史模板」
    的内存索引做 top-1 检索，输出分数分布与推荐阈值，供 T-0003 落常量。

只读约束：
    - 不写 data/embedding/prompt_templates/ 下任何文件；
    - 索引仅在内存中构建（VectorStoreIndex.from_documents），不 persist；
    - 不调用 LLM、不调用 reranker。

退出码：
    0 校准成功；
    2 查询数不足 / 嵌入模型不可用 / 维度与既有索引不一致 / 索引构建失败；
    3 基线数量或 legacy 数量与预期不符（迁移状态异常）。
"""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter

from penshot.config.config import settings
from penshot.neopen.agent.continuity_guardian.anchor_recall import (
    build_fragment_anchor_query,
)
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.script_parser_agent import build_contract_from_parsed
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.constants.rag import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    PROMPT_TEMPLATE_METADATA_TYPE,
)
from penshot.neopen.knowledge.embedding_adapter import to_llama_index_embedding
from penshot.neopen.knowledge.metadata_policy import PROMPT_TEMPLATE_METADATA_POLICY
from penshot.neopen.client.client_factory import get_default_embedding

EXIT_OK = 0
EXIT_INSUFFICIENT = 2
EXIT_BASELINE_MISMATCH = 3

DEFAULT_TASK_DIR = "data/output/SN2183078837410690460926/TSK21830726110914081668"
DEFAULT_BASE_DIR = "data/embedding/prompt_templates"
DEFAULT_SCRIPT_ID = "SN2183078837410690460926"
DEFAULT_REPORT_DIR = "data/output/calibration"
EXCLUDE_DATE = "2026-11-09"
EXPECTED_BASELINE = 116
EXPECTED_EXCLUDED = 11
EXPECTED_LEGACY = 0
EXPECTED_QUERIES = 11
THRESHOLD_FLOOR = 0.45
CURRENT_THRESHOLD = 0.7


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="0.4.4 召回阈值只读校准（M0）："
        "用缺陷样本重建契约，在迁移前基线上实测锚点查询 top-1 分数"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_TASK_DIR,
        help=f"缺陷样本的任务产物目录（默认：{DEFAULT_TASK_DIR}）",
    )
    parser.add_argument(
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help=f"提示词模板基础目录（默认：{DEFAULT_BASE_DIR}）",
    )
    parser.add_argument(
        "--script-id",
        default=DEFAULT_SCRIPT_ID,
        help=f"剧本ID，决定模板缓存位置（默认：{DEFAULT_SCRIPT_ID}）",
    )
    parser.add_argument(
        "--top-k", type=int, default=1, help="每次查询的检索数量（默认：1）"
    )
    parser.add_argument(
        "--report",
        default=os.path.join(DEFAULT_REPORT_DIR, "recall_threshold_<ts>.json"),
        help="报告输出路径；<ts> 会替换为运行时间戳",
    )
    parser.add_argument(
        "--exclude-date",
        default=EXCLUDE_DATE,
        help=f"剔除的本轮新增日期前缀（默认：{EXCLUDE_DATE}）",
    )
    parser.add_argument(
        "--expected-baseline",
        type=int,
        default=EXPECTED_BASELINE,
        help=f"迁移前基线模板数（默认：{EXPECTED_BASELINE}）",
    )
    parser.add_argument(
        "--expected-legacy",
        type=int,
        default=EXPECTED_LEGACY,
        help=f"基线中 legacy 模板数（默认：{EXPECTED_LEGACY}）",
    )
    return parser.parse_args(argv)


def _load_json(path: str) -> Any:
    """读取 UTF-8 JSON；失败时抛出带路径的异常"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _template_hash(prompt_text: str) -> str:
    """与 PromptTemplateManager 一致的去重哈希（空白归一后 md5 前 16 位）"""
    normalized = " ".join(prompt_text.strip().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def _is_legacy(entry: Dict[str, Any]) -> bool:
    """判定缓存条目是否已标记为 legacy（兼容顶层与 metadata 两种写法）"""
    if entry.get("legacy") is True:
        return True
    metadata = entry.get("metadata") or {}
    if metadata.get("legacy") is True:
        return True
    return metadata.get("schema_version") == "legacy"


def _split_baseline(
    cache: List[Dict[str, Any]], exclude_date: str
) -> Tuple[List[Dict[str, Any]], int]:
    """拆出迁移前基线，返回 (基线条目, 被剔除的本轮条数)"""
    baseline: List[Dict[str, Any]] = []
    excluded = 0
    for entry in cache:
        added_at = str(entry.get("added_at") or "")
        if exclude_date and added_at[:10] == exclude_date:
            excluded += 1
            continue
        baseline.append(entry)
    return baseline, excluded


def _build_documents(baseline: List[Dict[str, Any]], script_id: str) -> List[Document]:
    """按 PromptTemplateManager._rebuild_index_for_script 的口径构造文档"""
    documents: List[Document] = []
    for item in baseline:
        prompt_text = item.get("prompt", "")
        if not prompt_text:
            continue
        metadata = item.get("metadata") or {}
        doc_metadata = {
            **PROMPT_TEMPLATE_METADATA_POLICY.sanitize(metadata),
            "hash": _template_hash(prompt_text),
            "script_id": script_id,
            "timestamp": item.get("added_at") or datetime.now().isoformat(),
        }
        documents.append(Document(text=prompt_text, metadata=doc_metadata))
    return documents


def _persisted_index_facts(index_dir: str) -> Tuple[Optional[int], Optional[int]]:
    """读取已持久化索引的 (向量维度, 文档数)；不存在时返回 (None, None)"""
    for filename in ("default__vector_store.json", "vector_store.json"):
        path = os.path.join(index_dir, filename)
        if not os.path.exists(path):
            continue
        try:
            data = _load_json(path)
        except Exception:
            continue
        embedding_dict = data.get("embedding_dict") or {}
        if not embedding_dict:
            return None, 0
        first_vector = next(iter(embedding_dict.values()))
        return len(first_vector), len(embedding_dict)
    return None, None


def _build_queries(task_dir: str, script_id: str) -> Tuple[List[Dict[str, str]], int]:
    """反序列化阶段产物并构建锚点查询，返回 (查询列表, 跳过数)"""
    parsed = ParsedScript.model_validate(
        _load_json(os.path.join(task_dir, "script_parser_result.json"))
    )
    shot_sequence = ShotSequence.model_validate(
        _load_json(os.path.join(task_dir, "shot_segmenter_result.json"))
    )
    fragment_sequence = FragmentSequence.model_validate(
        _load_json(os.path.join(task_dir, "video_splitter_result.json"))
    )
    contract = build_contract_from_parsed(parsed, script_id=script_id)

    queries: List[Dict[str, str]] = []
    skipped = 0
    for fragment in fragment_sequence.fragments:
        query = build_fragment_anchor_query(fragment, shot_sequence, contract)
        if not query:
            skipped += 1
            continue
        queries.append({"fragment_id": fragment.id, "query": query})
    return queries, skipped


def _probe_embedding(embed_model: Any) -> List[float]:
    """对嵌入模型做一次真实调用，返回探针向量（同时验证可用性）"""
    if embed_model is None:
        raise RuntimeError("嵌入模型初始化失败")
    return embed_model.get_text_embedding("calibration probe")


def _retrieve_top1(
    index: VectorStoreIndex, query: str, top_k: int
) -> Tuple[Optional[float], Optional[str], Dict[str, Any]]:
    """对单条查询取 top-1 分数与模板来源信息"""
    retriever = index.as_retriever(
        similarity_top_k=max(1, top_k), retriever_mode="similarity"
    )
    nodes = retriever.retrieve(query)
    for node in nodes:
        metadata = node.node.metadata or {}
        if metadata.get("type") != PROMPT_TEMPLATE_METADATA_TYPE:
            continue
        return (
            float(node.score if node.score is not None else 0.0),
            metadata.get("hash"),
            {"script_id": metadata.get("script_id"), "node_id": node.node.node_id},
        )
    if nodes:
        node = nodes[0]
        return (
            float(node.score if node.score is not None else 0.0),
            (node.node.metadata or {}).get("hash"),
            {
                "script_id": (node.node.metadata or {}).get("script_id"),
                "node_id": node.node.node_id,
            },
        )
    return None, None, {}


def _resolve_report_path(report_arg: str) -> str:
    """替换 <ts> 占位符并创建父目录"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_arg.replace("<ts>", stamp)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    return path


def _print_summary(report: Dict[str, Any]) -> None:
    """在终端打印分数分布表"""
    print("\n===== 召回阈值校准结果 =====")
    print(
        f"基线模板: {report['baseline']['template_count']} "
        f"(剔除本轮 {report['baseline']['excluded_current_run']}, "
        f"legacy {report['baseline']['legacy_count']})"
    )
    print(
        f"嵌入模型: {report['embedding']['model_name']} "
        f"dim={report['embedding']['dimensions']} "
        f"(既有索引 dim={report['embedding']['persisted_dimension']}, "
        f"现状文档数={report['baseline']['index_docs_before']})"
    )
    print(
        f"查询数: {report['queries']['count']}（跳过 {report['queries']['skipped']}）"
    )
    print(f"{'fragment':<12}{'score':>10}  query")
    for item in report["queries"]["items"]:
        score = item.get("score")
        score_text = f"{score:.4f}" if isinstance(score, float) else "None"
        print(f"{item['fragment_id']:<12}{score_text:>10}  {item['query'][:60]}")
    print(
        f"min={report['scores']['min']:.4f} "
        f"P50={report['scores']['p50']:.4f} "
        f"max={report['scores']['max']:.4f}"
    )
    print(
        f"推荐阈值={report['threshold']['recommended']:.2f} "
        f"（当前 {CURRENT_THRESHOLD:.2f}，"
        f"新阈值命中 {report['threshold']['hits']}/{report['queries']['count']}）"
    )
    print(f"报告已写入: {report['report_path']}")


def main(argv: Optional[List[str]] = None) -> int:
    """执行只读校准，返回进程退出码"""
    args = _parse_args(argv)
    task_dir = args.output_dir
    script_dir = os.path.join(args.base_dir, args.script_id)

    # 1. 基线：模板缓存（迁移前 116 条）
    cache = _load_json(os.path.join(script_dir, "templates_cache.json"))
    if not isinstance(cache, list):
        print(f"[ERROR] 缓存格式异常（期望 list）: {script_dir}")
        return EXIT_BASELINE_MISMATCH

    baseline, excluded_current_run = _split_baseline(cache, args.exclude_date)
    legacy_count = sum(1 for entry in baseline if _is_legacy(entry))
    template_count = len(baseline)
    if template_count != args.expected_baseline or legacy_count != args.expected_legacy:
        print(
            "[ERROR] 基线断言失败："
            f"template_count={template_count}（期望 {args.expected_baseline}）, "
            f"legacy_count={legacy_count}（期望 {args.expected_legacy}）"
        )
        return EXIT_BASELINE_MISMATCH

    # 2. 契约 + 锚点查询（不触发 LLM）
    try:
        queries, skipped = _build_queries(task_dir, args.script_id)
    except Exception as exc:
        print(f"[ERROR] 阶段产物反序列化或契约重建失败: {exc}")
        return EXIT_BASELINE_MISMATCH

    if len(queries) < EXPECTED_QUERIES:
        print(
            f"[ERROR] 锚点查询不足：{len(queries)} < {EXPECTED_QUERIES}，不产出阈值建议"
        )
        return EXIT_INSUFFICIENT

    # 3. 嵌入模型可用性与维度一致性（R1）
    model_name = settings.get_embedding_config().model_name
    try:
        embed_model = to_llama_index_embedding(get_default_embedding())
        probe_vector = _probe_embedding(embed_model)
    except Exception as exc:
        print(f"[ERROR] 嵌入模型不可用（model={model_name}）: {exc}")
        return EXIT_INSUFFICIENT

    dimensions = len(probe_vector)
    persisted_dimension, index_docs_before = _persisted_index_facts(
        os.path.join(script_dir, "index_store")
    )
    if persisted_dimension is not None and persisted_dimension != dimensions:
        print(
            "[ERROR] 嵌入维度与既有索引不一致："
            f"current={dimensions}, persisted={persisted_dimension}（R1）"
        )
        return EXIT_INSUFFICIENT

    # 4. 内存索引（不落盘）
    try:
        documents = _build_documents(baseline, args.script_id)
        index = VectorStoreIndex.from_documents(
            documents,
            embed_model=embed_model,
            transformations=[
                SentenceSplitter(
                    chunk_size=DEFAULT_CHUNK_SIZE,
                    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
                )
            ],
            show_progress=False,
        )
    except Exception as exc:
        print(f"[ERROR] 内存索引构建失败: {exc}")
        return EXIT_INSUFFICIENT

    # 5. 逐条查询并统计
    score_items: List[Dict[str, Any]] = []
    scores: List[float] = []
    for item in queries:
        try:
            score, matched_hash, source = _retrieve_top1(
                index, item["query"], args.top_k
            )
        except Exception as exc:
            print(f"[ERROR] 检索失败（{item['fragment_id']}）: {exc}")
            return EXIT_INSUFFICIENT
        if score is None:
            continue
        scores.append(score)
        score_items.append(
            {
                "fragment_id": item["fragment_id"],
                "query": item["query"],
                "score": round(score, 6),
                "matched_hash": matched_hash,
                **source,
            }
        )

    if not scores:
        print("[ERROR] 全部查询无检索结果，无法校准")
        return EXIT_INSUFFICIENT

    p50 = statistics.median(scores)
    recommended = max(THRESHOLD_FLOOR, math.floor(p50 * 20) / 20)
    hits = sum(1 for score in scores if score >= recommended)
    hits_at_current = sum(1 for score in scores if score >= CURRENT_THRESHOLD)

    report: Dict[str, Any] = {
        "report_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "purpose": "0.4.4 M0 召回阈值校准（只读，内存索引）",
        "sample": {
            "task_dir": os.path.abspath(task_dir),
            "script_id": args.script_id,
        },
        "embedding": {
            "model_name": model_name,
            "dimensions": dimensions,
            "persisted_dimension": persisted_dimension,
            "consistent": persisted_dimension in (None, dimensions),
        },
        "baseline": {
            "source_cache": os.path.abspath(
                os.path.join(script_dir, "templates_cache.json")
            ),
            "cache_total": len(cache),
            "exclude_date": args.exclude_date,
            "excluded_current_run": excluded_current_run,
            "template_count": template_count,
            "legacy_count": legacy_count,
            "index_mode": "in_memory_no_persist",
            "index_docs_before": index_docs_before,
        },
        "queries": {
            "count": len(queries),
            "skipped": skipped,
            "items": score_items,
        },
        "scores": {
            "values": [round(score, 6) for score in scores],
            "min": round(min(scores), 6),
            "p50": round(p50, 6),
            "max": round(max(scores), 6),
        },
        "threshold": {
            "formula": "max(0.45, floor(P50 * 20) / 20)",
            "recommended": round(recommended, 2),
            "hits": hits,
            "current": CURRENT_THRESHOLD,
            "hits_at_current": hits_at_current,
        },
        "warnings": [],
    }
    if excluded_current_run != EXPECTED_EXCLUDED:
        report["warnings"].append(
            f"剔除本轮条数 {excluded_current_run} != {EXPECTED_EXCLUDED}"
        )
    if p50 < THRESHOLD_FLOOR:
        report["warnings"].append("P50 < 0.45，阈值固定 0.45，不改写下调")

    report_path = _resolve_report_path(args.report)
    report["report_path"] = report_path
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    _print_summary(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
