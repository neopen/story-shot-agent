---
kind: external_dependency
name: LangChain 框架与 LLM/Embedding 客户端抽象
slug: langchain
category: external_dependency
category_hints:
    - framework_behavior
    - sdk_real_api
scope:
    - '**'
---

### LangChain 框架
- 作为 LLM 和 Embedding 的统一抽象层，通过 `BaseLanguageModel` 和 `Embeddings` 接口屏蔽不同厂商差异
- 通过 `client_factory` 按 provider（OpenAI/Qwen/DeepSeek/Ollama）动态创建具体客户端实例
- 消息格式统一为 LangChain 的 `SystemMessage/HumanMessage/AIMessage` 对象
- 注意：项目使用 langchain v1.x API，与旧版 v0.x 不兼容