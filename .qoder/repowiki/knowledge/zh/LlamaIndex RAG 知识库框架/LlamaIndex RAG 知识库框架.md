---
kind: external_dependency
name: LlamaIndex RAG 知识库框架
slug: llama-index
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
---

### LlamaIndex 知识库系统
- 负责知识库的文档加载、索引构建、检索工具封装
- 知识库路径：`data/embedding/script_kb/` 和 `data/embedding/prompt_templates/`
- 支持多种嵌入模型后端，通过 LangChain Embeddings 接口适配