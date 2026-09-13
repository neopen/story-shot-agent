"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: prompt_template_knowledge.py
@Description: 专门的提示词模板知识库
@Author: NeoPen
@Time: 2026/4/23 22:45
"""
from pathlib import Path
from typing import List, Dict, Any, Optional

from llama_index.core import VectorStoreIndex, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage import StorageContext

from penshot.config.config import settings
from penshot.logger import debug, info, error, warning


class PromptTemplateKB:
    """提示词模板知识库 - 专门存储成功的提示词模板"""

    def __init__(self, embeddings, script_id: str, storage_dir: Optional[str] = None):
        """
        初始化提示词模板知识库

        Args:
            embeddings: 嵌入模型
            script_id: 剧本ID（用于数据隔离）
            storage_dir: 存储目录（可选）
        """
        self.embeddings = embeddings
        self.script_id = script_id
        if storage_dir is None:
            base_dir = settings.get_data_paths().get("data_embedding", "data/embedding")
            self.storage_dir = Path(base_dir) / "prompt_templates" / script_id
        else:
            self.storage_dir = Path(storage_dir) / script_id

        self.index = None
        self.templates = []  # 模板缓存

        # 节点解析器配置
        self.node_parser = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=20
        )

        # 确保目录存在
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 尝试加载已有索引
        self._load_index()

        info(f"提示词模板知识库初始化完成: script_id={script_id}, storage={self.storage_dir}")

    def _load_index(self):
        """加载已有索引"""
        import os
        try:
            vector_store_path = os.path.join(self.storage_dir, "prompt_vector_store.json")
            if os.path.exists(vector_store_path):
                from llama_index.core.vector_stores import SimpleVectorStore
                vector_store = SimpleVectorStore.from_persist_path(vector_store_path)
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store,
                    storage_context=storage_context,
                    embed_model=self.embeddings
                )
                info(f"已加载提示词模板索引: {vector_store_path}")
        except Exception as e:
            warning(f"加载提示词模板索引失败: {e}")

    def _save_index(self):
        """保存索引"""
        if self.storage_dir and self.index:
            import os
            os.makedirs(self.storage_dir, exist_ok=True)
            try:
                vector_store_path = os.path.join(self.storage_dir, "prompt_vector_store.json")
                self.index.storage_context.vector_store.persist(persist_path=vector_store_path)
                debug(f"已保存提示词模板索引: {vector_store_path}")
            except Exception as e:
                warning(f"保存提示词模板索引失败: {e}")


    def add_template(self, prompt_text: str, metadata: Dict[str, Any]):
        """
        添加成功提示词模板

        Args:
            prompt_text: 提示词文本
            metadata: 元数据（fragment_id, scene, style等）
        """
        try:
            doc = Document(
                text=prompt_text,
                metadata={
                    "type": "prompt_template",
                    "prompt": prompt_text,
                    "timestamp": metadata.get("timestamp", ""),
                    "fragment_id": metadata.get("fragment_id", ""),
                    "scene": metadata.get("scene", ""),
                    "style": metadata.get("style", ""),
                    "quality_score": metadata.get("quality_score", 0),
                    **metadata
                }
            )

            if not self.index:
                # 首次创建索引
                self.index = VectorStoreIndex.from_documents(
                    [doc],
                    embed_model=self.embeddings,
                    transformations=[self.node_parser]
                )
                info(f"创建提示词模板索引，首个模板长度: {len(prompt_text)}")
            else:
                # 向现有索引添加文档
                nodes = self.node_parser.get_nodes_from_documents([doc])
                self.index.insert_nodes(nodes)
                debug(f"添加提示词模板，ID: {metadata.get('fragment_id', 'unknown')}")

            # 缓存模板
            self.templates.append(metadata)

            # 保存索引
            self._save_index()

        except Exception as e:
            error(f"添加提示词模板失败: {e}")

    def add_templates_batch(self, templates: List[tuple]):
        """
        批量添加提示词模板

        Args:
            templates: [(prompt_text, metadata), ...] 列表
        """
        for prompt_text, metadata in templates:
            self.add_template(prompt_text, metadata)

        info(f"批量添加完成，共 {len(templates)} 个模板")

    def search_similar(self, query_text: str, top_k: int = 3,
                       min_score: float = 0.6) -> List[Dict]:
        """
        搜索相似提示词模板

        Args:
            query_text: 查询文本
            top_k: 返回数量
            min_score: 最低相似度分数

        Returns:
            相似模板列表
        """
        if not self.index:
            debug("提示词模板索引未初始化，返回空结果")
            return []

        try:
            # 创建检索器
            retriever = self.index.as_retriever(
                similarity_top_k=top_k,
                retriever_mode="similarity"
            )

            # 执行检索
            nodes = retriever.retrieve(query_text)

            # 格式化结果
            results = []
            for node in nodes:
                score = node.score if hasattr(node, 'score') else 0

                # 分数过滤
                if score < min_score:
                    continue

                # 只返回提示词类型的文档
                if node.node.metadata.get("type") != "prompt_template":
                    continue

                results.append({
                    "prompt": node.node.text,
                    "score": score,
                    "metadata": node.node.metadata,
                    "node_id": node.node.node_id
                })

            debug(f"搜索相似提示词: '{query_text[:50]}...', 找到 {len(results)} 个结果")
            return results[:top_k]

        except Exception as e:
            error(f"搜索相似提示词失败: {e}")
            return []

    def get_best_match(self, query_text: str, min_score: float = 0.7) -> Optional[str]:
        """
        获取最佳匹配的提示词模板

        Args:
            query_text: 查询文本
            min_score: 最低相似度分数

        Returns:
            最佳匹配的提示词，或 None
        """
        results = self.search_similar(query_text, top_k=1, min_score=min_score)
        if results:
            return results[0]["prompt"]
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "template_count": len(self.templates),
            "has_index": self.index is not None,
            "storage_dir": self.storage_dir
        }

    def clear(self):
        """清空知识库"""
        self.index = None
        self.templates = []
        info("提示词模板知识库已清空")
