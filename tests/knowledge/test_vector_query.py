"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: test_vector_query.py
@Description: 查询相似度分数
@Author: NeoPen
@Time: 2026/5/21 16:34
"""
import numpy as np
from pathlib import Path
from llama_index.core import StorageContext
from penshot.neopen.shot_config import ShotConfig


def test_vector_query():
    config = ShotConfig()
    embeddings = config.get_embed_by_config()
    script_id = "SN1780745829485283341820"
    script_dir = Path("../../data/embedding/script_kb") / script_id

    print("=" * 60)
    print("直接向量查询")
    print("=" * 60)

    # 加载存储
    storage_context = StorageContext.from_defaults(persist_dir=str(script_dir))
    vector_store = storage_context.vector_store

    # 获取查询向量（使用同步方法）
    query = "林然"
    query_embedding = embeddings.embed_query(query)

    print(f"查询向量维度: {len(query_embedding)}")
    print(f"向量存储中的向量数: {len(vector_store._data.embedding_dict)}")

    # 计算与每个文档的余弦相似度
    print(f"\n手动计算余弦相似度:")
    results = []
    for doc_id, embedding in vector_store._data.embedding_dict.items():
        # 计算余弦相似度
        dot = np.dot(query_embedding, embedding)
        norm_q = np.linalg.norm(query_embedding)
        norm_d = np.linalg.norm(embedding)
        similarity = dot / (norm_q * norm_d) if norm_q > 0 and norm_d > 0 else 0

        # 获取文档元数据
        doc = storage_context.docstore.docs.get(doc_id)
        doc_type = doc.metadata.get('type', 'unknown') if doc and hasattr(doc, 'metadata') else 'unknown'

        # 获取角色名或场景信息
        name = ""
        if doc_type == 'character' and doc:
            name = doc.metadata.get('character_name', '')
        elif doc_type == 'scene' and doc:
            name = doc.metadata.get('location', '')

        results.append({
            'doc_id': doc_id[:8],
            'type': doc_type,
            'name': name,
            'similarity': similarity
        })
        print(f"  doc_id={doc_id[:8]}..., type={doc_type}, name={name}, similarity={similarity:.4f}")

    # 按相似度排序
    results.sort(key=lambda x: x['similarity'], reverse=True)
    print(f"\n排序后 TOP 3:")
    for r in results[:3]:
        print(f"  {r['type']}: {r['name']}, similarity={r['similarity']:.4f}")


if __name__ == "__main__":
    test_vector_query()