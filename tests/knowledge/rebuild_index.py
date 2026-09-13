"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: rebuild_index.py
@Description: 手动重建索引
@Author: NeoPen
@Time: 2026/5/21 16:19
"""
import asyncio
from pathlib import Path

from llama_index.core import StorageContext, VectorStoreIndex

from penshot.neopen.shot_config import ShotConfig


async def rebuild():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"

    print("=" * 60)
    print("重建知识库索引")
    print("=" * 60)

    # 1. 直接使用 StorageContext 加载
    script_dir = Path("../../data/embedding/script_kb") / script_id
    storage_context = StorageContext.from_defaults(persist_dir=str(script_dir))

    print(f"\n加载的存储上下文:")
    if storage_context.vector_store:
        vs = storage_context.vector_store
        if hasattr(vs, '_data'):
            print(f"  向量数: {len(vs._data.embedding_dict)}")

    if storage_context.docstore:
        print(f"  文档数: {len(storage_context.docstore.docs)}")

    # 2. 创建索引
    print(f"\n创建 VectorStoreIndex...")
    index = VectorStoreIndex.from_vector_store(
        storage_context.vector_store,
        storage_context=storage_context,
        embed_model=embeddings
    )

    print(f"索引创建成功")

    # 3. 测试查询
    print(f"\n测试查询...")
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve("林然")

    print(f"查询结果数: {len(nodes)}")
    for i, node in enumerate(nodes):
        print(f"  {i + 1}. score={node.score:.4f}: {node.node.text[:80]}...")


if __name__ == "__main__":
    asyncio.run(rebuild())
