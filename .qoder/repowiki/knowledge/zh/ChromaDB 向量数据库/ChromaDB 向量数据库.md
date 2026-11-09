---
kind: external_dependency
name: ChromaDB 向量数据库
slug: chromadb
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### ChromaDB 向量存储
- 作为默认向量数据库后端，配置在 `settings.yaml` 的 `vector_store.chroma` 段
- 持久化目录：`./data/vector_store`，集合名：`script_embeddings`，距离度量：cosine
- 用于长期记忆存储和跨任务知识召回
- 配合 llama-index 进行文档加载和检索