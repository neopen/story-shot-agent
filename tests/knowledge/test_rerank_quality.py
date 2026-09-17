"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_rerank_quality.py
@Description: 
@Author: NeoPen
@Time: 2026/5/20 22:13
"""
from penshot.config.config import settings
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.shot_config import ShotConfig


def test_evaluate_rerank_quality():
    """评估重排序是否提高了检索质量"""

    queries = [
        "林然的服装描述",
        "灰色羊毛毯的颜色",
        "旧相册的外观",
        "陈默的声音特征",
        "客厅的环境氛围",
    ]

    results = []

    for query in queries:
        print(f"\n查询: {query}")
        print("-" * 40)

        # 1. 初始化知识库
        config = ShotConfig()
        embeddings = config.get_embed_by_config()

        kb = ScriptKnowledgeBase(
            embeddings=embeddings,
            script_id="SN1780745829485283341820",
            storage_dir=settings.get_data_paths().get("data_embedding")
        )

        # 2. 设置当前剧本（替换为你的实际 script_id）
        script_id = "SN1780745829485283341820"  # 从日志中获取
        kb.set_current_script(script_id)

        # 无重排序
        result_no = kb.query(query, script_id, use_rerank=False, similarity_top_k=10)
        # 有重排序
        result_yes = kb.query(query, script_id, use_rerank=True, similarity_top_k=10)

        # 获取前3个结果
        top3_no = [r['text'][:50] for r in result_no.get('results', [])[:3]]
        top3_yes = [r['text'][:50] for r in result_yes.get('results', [])[:3]]

        print(f"  无重排序 Top3: {top3_no}")
        print(f"  有重排序 Top3: {top3_yes}")

        # 判断重排序是否改变了结果顺序
        if top3_no != top3_yes:
            print("  ✅ 重排序有效：结果顺序已改变")
        else:
            print("  ⚠️ 重排序无效：结果顺序相同")

        results.append({
            "query": query,
            "changed": top3_no != top3_yes,
            "no_rerank": top3_no,
            "with_rerank": top3_yes
        })

    # 统计
    changed_count = sum(1 for r in results if r["changed"])
    print(f"\n{'=' * 60}")
    print(f"重排序效果统计: {changed_count}/{len(queries)} 个查询结果发生了变化")

    return results
