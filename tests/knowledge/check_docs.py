"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: check_docs.py
@Description: 查看实际存储的文档内容
@Author: NeoPen
@Time: 2026/5/21 16:31
"""
import asyncio
from pathlib import Path
from llama_index.core import StorageContext


async def check_docs():
    script_id = "SN1780745829485283341820"
    script_dir = Path("../../data/embedding/script_kb") / script_id

    storage_context = StorageContext.from_defaults(persist_dir=str(script_dir))

    print("=" * 60)
    print("存储的文档内容")
    print("=" * 60)

    for doc_id, doc in storage_context.docstore.docs.items():
        print(f"\n文档 ID: {doc_id}")
        print(f"类型: {doc.metadata.get('type', 'unknown')}")
        if doc.metadata.get('type') == 'character':
            print(f"角色名: {doc.metadata.get('character_name', 'unknown')}")
        elif doc.metadata.get('type') == 'scene':
            print(f"场景: {doc.metadata.get('location', 'unknown')}")
        print(f"文本内容预览: {doc.text[:200]}...")
        print("-" * 40)


if __name__ == "__main__":
    asyncio.run(check_docs())