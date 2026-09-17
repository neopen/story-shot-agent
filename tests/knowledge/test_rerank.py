"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_rerank.py
@Description: 
@Author: NeoPen
@Time: 2026/5/20 22:12
"""

import asyncio
from pathlib import Path

from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.shot_config import ShotConfig


async def test_rerank():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"

    print("=" * 60)
    print("初始化知识库...")
    print("=" * 60)

    kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        script_id=script_id
    )
    kb.set_current_script(script_id)

    # 检查索引是否加载成功
    print(f"\n索引状态: script_id={script_id}")
    print(f"  _indices contains: {script_id in kb._indices}")
    if script_id in kb._indices:
        print(f"  index is None: {kb._indices[script_id] is None}")

    # 如果索引为 None，尝试重建
    if script_id in kb._indices and kb._indices[script_id] is None:
        print("\n⚠️ 索引为 None，尝试从已有文档重建...")
        if script_id in kb.document_cache and kb.document_cache[script_id]:
            print(f"  找到 {len(kb.document_cache[script_id])} 个缓存文档，重建索引...")
            kb._add_documents_to_index(kb.document_cache[script_id], script_id)
        else:
            print("  没有缓存文档，需要重新添加剧本")

    query = "灰色羊毛毯 林然"

    print("\n" + "=" * 60)
    print("测试查询")
    print("=" * 60)

    # 执行查询
    result = kb.query(
        query_text=query,
        script_id=script_id,
        similarity_top_k=5,
        use_rerank=True
    )

    print(f"\n查询结果: {len(result.get('results', []))} 条")
    for i, r in enumerate(result.get("results", [])):
        print(f"  {i + 1}. score={r['score']:.4f}: {r['text'][:100]}...")
        print(f"      类型: {r['metadata'].get('type', 'unknown')}")

    # 检查文件结构
    print("\n" + "=" * 60)
    print("文件结构检查")
    print("=" * 60)

    storage_dir = Path("../../data/embedding/script_kb") / script_id
    if storage_dir.exists():
        for f in storage_dir.iterdir():
            size = f.stat().st_size if f.is_file() else 0
            print(f"  {f.name} ({size} bytes)")
    else:
        print(f"  目录不存在: {storage_dir}")


if __name__ == "__main__":
    asyncio.run(test_rerank())