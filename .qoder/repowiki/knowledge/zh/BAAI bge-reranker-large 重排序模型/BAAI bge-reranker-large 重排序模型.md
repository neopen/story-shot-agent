---
kind: external_dependency
name: BAAI bge-reranker-large 重排序模型
slug: bge-reranker-large
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### BAAI bge-reranker-large 本地重排序模型
- 开源重排序模型，用于提升 RAG 检索质量
- 本地部署路径：`data/models/bge-reranker-large/`，包含 ONNX 格式优化版本
- 可通过 `PENSHOT_RETRIEVER__RERANK_ENABLED` 开关控制启用
- 支持 HuggingFace 镜像加速下载（`HF_ENDPOINT=https://hf-mirror.com`）