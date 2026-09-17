"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_fixed_index.py
@Description:
@Author: NeoPen
@Time: 2026/5/21 16:22
"""
# test_fixed_index.py
import asyncio
from pathlib import Path

from llama_index.core import StorageContext, VectorStoreIndex

from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.shot_config import ShotConfig


async def test_fixed():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"

    print("=" * 60)
    print("测试修复后的索引加载")
    print("=" * 60)

    # 方法1：直接使用 LlamaIndex
    script_dir = Path("../../data/embedding/script_kb") / script_id
    storage_context = StorageContext.from_defaults(persist_dir=str(script_dir))
    index = VectorStoreIndex(
        nodes=[],
        storage_context=storage_context,
        embed_model=embeddings
    )

    # 不设阈值
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve("林然")

    print(f"\n直接使用 LlamaIndex 检索器 (无阈值): {len(nodes)} 条")
    for n in nodes:
        print(f"  score={n.score:.4f}: {n.node.text[:60]}...")

    # 方法2：通过 ScriptKnowledgeBase
    kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        script_id=script_id
    )

    # 强制重新创建检索器
    if script_id in kb._retrievers:
        del kb._retrievers[script_id]

    result = kb.query(
        query_text="林然",
        script_id=script_id,
        similarity_top_k=5,
        use_rerank=False
    )

    print(f"\n通过 ScriptKnowledgeBase 查询: {len(result.get('results', []))} 条")
    for r in result.get('results', []):
        print(f"  score={r['score']:.4f}: {r['text'][:60]}...")


def test_direct_query():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"

    print("=" * 60)
    print("测试直接向量查询")
    print("=" * 60)

    kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        script_id=script_id
    )

    # 测试查询
    queries = ["林然", "羊毛毯", "场景"]

    for query in queries:
        print(f"\n查询: '{query}'")
        result = kb.query(
            query_text=query,
            script_id=script_id,
            similarity_top_k=5,
            use_rerank=False
        )

        print(f"  结果数: {len(result.get('results', []))}")
        for r in result.get('results', []):
            print(f"    score={r['score']:.4f}: {r['text'][:60]}...")


if __name__ == "__main__":
    asyncio.run(test_fixed())