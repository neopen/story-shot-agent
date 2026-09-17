"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: diagnose_index.py
@Description: 检查索引
@Author: NeoPen
@Time: 2026/5/21 16:18
"""
import asyncio
from pathlib import Path
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.shot_config import ShotConfig


async def diagnose():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"

    print("=" * 60)
    print("诊断知识库索引")
    print("=" * 60)

    kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        script_id=script_id
    )

    # 1. 检查文件结构
    script_dir = Path("../../data/embedding/script_kb") / script_id
    print(f"\n1. 文件结构 ({script_dir}):")
    if script_dir.exists():
        for f in script_dir.iterdir():
            if f.is_file():
                size = f.stat().st_size
                print(f"   {f.name} ({size} bytes)")
    else:
        print(f"   目录不存在!")

    # 2. 检查索引加载
    print(f"\n2. 索引状态:")
    index = kb._indices.get(script_id)
    print(f"   index is None: {index is None}")

    if index is not None:
        # 尝试获取节点数量
        try:
            if hasattr(index, 'docstore') and index.docstore:
                docs = index.docstore.docs
                print(f"   docstore 节点数: {len(docs)}")
                for doc_id, doc in list(docs.items())[:3]:
                    print(f"     - {doc_id}: {doc.text[:50]}...")
        except Exception as e:
            print(f"   无法获取节点: {e}")

        # 检查 vector_store
        try:
            if hasattr(index, '_vector_store') and index._vector_store:
                vs = index._vector_store
                if hasattr(vs, '_data'):
                    vec_count = len(vs._data.embedding_dict)
                    print(f"   vector_store 向量数: {vec_count}")
        except Exception as e:
            print(f"   无法获取向量数: {e}")

    # 3. 尝试手动重建索引
    print(f"\n3. 尝试重建索引...")
    if script_id in kb.document_cache and kb.document_cache[script_id]:
        print(f"   找到 {len(kb.document_cache[script_id])} 个缓存文档")
    else:
        print(f"   没有缓存文档，需要从存储重建...")

        # 尝试从 docstore 重建
        docstore_path = script_dir / "docstore.json"
        if docstore_path.exists():
            print(f"   发现 docstore.json，尝试重建索引...")
            # 这里可以添加重建逻辑

    # 4. 测试查询
    print(f"\n4. 测试直接查询 storage_context...")
    try:
        from llama_index.core import StorageContext
        storage_context = StorageContext.from_defaults(persist_dir=str(script_dir))

        if storage_context.vector_store:
            vs = storage_context.vector_store
            if hasattr(vs, '_data'):
                vec_count = len(vs._data.embedding_dict)
                print(f"   storage_context 向量数: {vec_count}")

        if storage_context.docstore:
            docs = storage_context.docstore.docs
            print(f"   storage_context 文档数: {len(docs)}")
    except Exception as e:
        print(f"   加载失败: {e}")


if __name__ == "__main__":
    asyncio.run(diagnose())