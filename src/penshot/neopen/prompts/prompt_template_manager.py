"""
@FileName: prompt_template_manager.py
@Description: 提示词模板管理器 - 负责成功提示词模板的存储、检索和应用
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/04/23
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from llama_index.core import VectorStoreIndex, Document, load_index_from_storage
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage import StorageContext

from penshot.config.config import settings
from penshot.logger import debug, info, error, warning
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
from penshot.neopen.knowledge.memory.memory_models import MemoryLevel


class PromptTemplateManager:
    """
    提示词模板管理器

    职责：
    1. 存储成功的提示词模板到向量数据库
    2. 检索相似提示词模板
    3. 应用模板增强当前提示词
    4. 与记忆层同步
    """

    def __init__(
            self,
            embedding_model,
            memory_manager: Optional[MemoryManager] = None,
            storage_dir: Optional[str] = settings.get_data_paths().get('data_embedding'),
            chunk_size: int = 512,
            chunk_overlap: int = 20,
            min_similarity_score: float = 0.5,
            top_k: int = 3
    ):
        """
        初始化提示词模板管理器

        Args:
            embedding_model: 嵌入模型
            memory_manager: 记忆管理器（用于加载历史成功模板）
            storage_dir: 存储目录
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
            min_similarity_score: 最低相似度分数
            top_k: 检索返回数量
        """
        self.embedding_model = embedding_model
        self.memory_manager = memory_manager
        self.storage_dir = storage_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_similarity_score = min_similarity_score
        self.top_k = top_k

        # 索引相关
        self.index = None
        self._templates_cache: List[Dict] = []

        # 节点解析器
        self.node_parser = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        # 初始化
        self._init()

        # 剧本知识库（用于连续性检查等）
        self.script_kb = None
        self._init_script_kb()

    def _init(self):
        """初始化管理器"""
        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)

        # 先加载缓存
        self._load_cache()

        # 尝试加载索引
        self._load_index()

        # 如果缓存有数据但索引不存在，从缓存重建索引
        if self._templates_cache and not self.index:
            self._rebuild_index_from_cache()
            self._save_index()  # 保存重建的索引

        # 如果缓存为空但索引存在，从索引重建缓存
        if not self._templates_cache and self.index:
            self._rebuild_cache_from_index()

        # 从记忆层加载历史模板（如果仍然没有数据）
        if not self._templates_cache:
            self._load_from_memory()

        info(f"提示词模板管理器初始化完成，当前模板数: {len(self._templates_cache)}")

    def _rebuild_index_from_cache(self):
        """从缓存重建索引"""
        if not self._templates_cache:
            return

        try:
            documents = []
            for item in self._templates_cache:
                doc = Document(
                    text=item["prompt"],
                    metadata={
                        "type": "prompt_template",
                        "prompt": item["prompt"],
                        "timestamp": item.get("added_at", datetime.now().isoformat()),
                        **item.get("metadata", {})
                    }
                )
                documents.append(doc)

            self.index = VectorStoreIndex.from_documents(
                documents,
                embed_model=self.embedding_model,
                transformations=[self.node_parser]
            )
            info(f"从缓存重建索引，共 {len(documents)} 个模板")
        except Exception as e:
            error(f"重建索引失败: {e}")


    def _save_index(self):
        """保存索引（包含文档存储）"""
        if not self.storage_dir or not self.index:
            return

        try:
            # 保存完整的存储上下文（包含文档存储和向量存储）
            persist_dir = os.path.join(self.storage_dir, "index_store")
            os.makedirs(persist_dir, exist_ok=True)

            # 使用 persist 方法保存整个存储上下文
            self.index.storage_context.persist(persist_dir=persist_dir)
            debug(f"已保存完整索引到: {persist_dir}")
        except Exception as e:
            warning(f"保存索引失败: {e}")

    def _load_index(self):
        """加载已有索引（完整加载）"""
        if not self.storage_dir:
            return

        try:
            persist_dir = os.path.join(self.storage_dir, "index_store")
            if os.path.exists(persist_dir):
                # 从持久化目录加载
                storage_context = StorageContext.from_defaults(persist_dir=persist_dir)

                # 使用 load_index_from_storage 加载索引
                # 重要：必须传入 embed_model，否则会使用默认的 MockEmbedding [citation:7]
                self.index = load_index_from_storage(
                    storage_context=storage_context,
                    embed_model=self.embedding_model
                )
                info(f"已加载完整索引: {persist_dir}")

                # 重建缓存
                self._rebuild_cache_from_index()
            else:
                debug(f"索引目录不存在，将创建新索引: {persist_dir}")
        except Exception as e:
            warning(f"加载索引失败: {e}")

    def _rebuild_cache_from_index(self):
        """从索引重建缓存（当缓存文件丢失但索引存在时使用）"""
        if not self.index:
            return

        try:
            # 更可靠的方式：直接从 docstore 获取文档
            docstore = self.index.storage_context.docstore

            # 获取所有文档ID
            all_doc_ids = list(docstore.docs.keys())

            self._templates_cache = []
            for doc_id in all_doc_ids:
                doc = docstore.get_document(doc_id)
                if doc.metadata.get("type") == "prompt_template":
                    self._templates_cache.append({
                        "prompt": doc.text,
                        "metadata": doc.metadata,
                        "added_at": doc.metadata.get("timestamp", datetime.now().isoformat())
                    })

            # 保存重建的缓存
            self._save_cache()

            info(f"从索引重建缓存，共 {len(self._templates_cache)} 个模板")
        except Exception as e:
            warning(f"重建缓存失败: {e}")


    def _save_cache(self):
        """保存缓存到文件"""
        if not self.storage_dir:
            return

        try:
            import json
            cache_path = os.path.join(self.storage_dir, "vector_store_cache.json")
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._templates_cache, f, ensure_ascii=False, indent=2)
            debug(f"已保存缓存: {cache_path}")
        except Exception as e:
            warning(f"保存缓存失败: {e}")

    def _load_cache(self):
        """从文件加载缓存"""
        if not self.storage_dir:
            return

        try:
            import json
            cache_path = os.path.join(self.storage_dir, "vector_store_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self._templates_cache = json.load(f)
                info(f"已加载缓存，共 {len(self._templates_cache)} 个模板")
        except Exception as e:
            warning(f"加载缓存失败: {e}")


    def _load_from_memory(self):
        """从记忆层加载历史成功模板（启动时恢复）"""
        if not self.memory_manager:
            return

        try:
            # 从长期记忆获取成功提示词模式
            successful_prompts = self.memory_manager.get(
                "successful_prompt_patterns",
                level=MemoryLevel.LONG_TERM,
                default=[]
            )

            if isinstance(successful_prompts, list):
                loaded_count = 0
                for template_data in successful_prompts:
                    if isinstance(template_data, dict):
                        prompt_text = template_data.get("prompt", "")
                        metadata = template_data.get("metadata", {})
                        if prompt_text:
                            # 直接添加到缓存和索引，不需要再保存到记忆层（避免循环）
                            self._add_template_direct(prompt_text, metadata)
                            loaded_count += 1

                info(f"从记忆层加载了 {loaded_count} 个历史提示词模板")

        except Exception as e:
            warning(f"从记忆层加载模板失败: {e}")

    def _add_template_direct(self, prompt_text: str, metadata: Dict[str, Any]):
        """
        直接添加模板到索引（不触发记忆层保存，用于启动时加载）
        """
        try:
            # 去重检查
            for existing in self._templates_cache:
                if existing.get("prompt") == prompt_text:
                    return

            doc = Document(
                text=prompt_text,
                metadata={
                    "type": "prompt_template",
                    "prompt": prompt_text,
                    "timestamp": metadata.get("timestamp", datetime.now().isoformat()),
                    "quality_score": metadata.get("quality_score", 0),
                    "fragment_id": metadata.get("fragment_id", ""),
                    "scene": metadata.get("scene", ""),
                    "style": metadata.get("style", ""),
                    **metadata
                }
            )

            if not self.index:
                self.index = VectorStoreIndex.from_documents(
                    [doc],
                    embed_model=self.embedding_model,
                    transformations=[self.node_parser]
                )
            else:
                nodes = self.node_parser.get_nodes_from_documents([doc])
                self.index.insert_nodes(nodes)

            self._templates_cache.append({
                "prompt": prompt_text,
                "metadata": metadata,
                "added_at": metadata.get("timestamp", datetime.now().isoformat())
            })

        except Exception as e:
            warning(f"直接添加模板失败: {e}")


    def _init_script_kb(self):
        """初始化剧本知识库"""
        try:
            storage_dir = os.path.join(self.storage_dir, "script_kb") if self.storage_dir else None
            self.script_kb = ScriptKnowledgeBase(
                embeddings=self.embedding_model,
                storage_dir=storage_dir,
                chunk_size=512,
                chunk_overlap=20
            )
            info("剧本知识库初始化完成")
        except Exception as e:
            warning(f"剧本知识库初始化失败: {e}")
            self.script_kb = None

    def add_script(self, script_text: str, script_id: str):
        """添加剧本到知识库"""
        if self.script_kb:
            try:
                self.script_kb.add_script_text(script_text, script_id)
                info(f"已添加剧本到知识库: {script_id}")
            except Exception as e:
                warning(f"添加剧本到知识库失败: {e}")

    def add_parsed_script(self, parsed_script, script_id=None):
        """添加已解析的剧本到知识库"""
        return self.script_kb.add_parsed_script(parsed_script, script_id)

    def is_script_kb_available(self) -> bool:
        """检查剧本知识库是否可用"""
        if not self.script_kb:
            return False
        try:
            stats = self.script_kb.get_statistics()
            return stats.get("script_count", 0) > 0
        except:
            return False

    def search_similar_scene(self, query_text: str, top_k: int = 3) -> List[Dict]:
        """搜索相似场景（用于连续性检查）"""
        if not self.script_kb:
            return []

        try:
            result = self.script_kb.query(
                query_text=query_text,
                search_type="similarity",
                similarity_top_k=top_k,
                use_rerank=True
            )
            return result.get("results", [])
        except Exception as e:
            warning(f"搜索相似场景失败: {e}")
            return []


    def add_template(
            self,
            prompt_text: str,
            metadata: Dict[str, Any],
            save_to_memory: bool = True
    ) -> bool:
        """
        添加成功提示词模板

        Args:
            prompt_text: 提示词文本
            metadata: 元数据（fragment_id, scene, style, quality_score等）
            save_to_memory: 是否同时保存到记忆层

        Returns:
            是否添加成功
        """
        try:
            # 去重检查
            for existing in self._templates_cache:
                if existing.get("prompt") == prompt_text:
                    debug("提示词模板已存在，跳过添加")
                    return False

            # 创建文档
            doc = Document(
                text=prompt_text,
                metadata={
                    "type": "prompt_template",
                    "prompt": prompt_text,
                    "timestamp": datetime.now().isoformat(),
                    "quality_score": metadata.get("quality_score", 0),
                    "fragment_id": metadata.get("fragment_id", ""),
                    "scene": metadata.get("scene", ""),
                    "style": metadata.get("style", ""),
                    "shot_type": metadata.get("shot_type", ""),
                    "duration": metadata.get("duration", 0),
                    **metadata
                }
            )

            # 添加到索引
            if not self.index:
                self.index = VectorStoreIndex.from_documents(
                    [doc],
                    embed_model=self.embedding_model,
                    transformations=[self.node_parser]
                )
                info(f"创建提示词模板索引")
            else:
                nodes = self.node_parser.get_nodes_from_documents([doc])
                self.index.insert_nodes(nodes)

            # 缓存
            self._templates_cache.append({
                "prompt": prompt_text,
                "metadata": metadata,
                "added_at": datetime.now().isoformat()
            })

            # 保存到磁盘
            self._save_index()
            self._save_cache()

            # 保存到记忆层
            if save_to_memory and self.memory_manager:
                self._save_to_memory(prompt_text, metadata)

            info(f"添加提示词模板成功，当前总数: {len(self._templates_cache)}")
            return True

        except Exception as e:
            error(f"添加提示词模板失败: {e}")
            return False

    def _save_to_memory(self, prompt_text: str, metadata: Dict[str, Any]):
        """保存模板到记忆层"""
        try:
            # 获取现有模板列表
            existing = self.memory_manager.get(
                "successful_prompt_patterns",
                level=MemoryLevel.LONG_TERM,
                default=[]
            )

            if not isinstance(existing, list):
                existing = []

            # 去重
            new_template = {
                "prompt": prompt_text,
                "metadata": metadata,
                "timestamp": datetime.now().isoformat()
            }

            # 检查是否已存在
            exists = False
            for item in existing:
                if isinstance(item, dict) and item.get("prompt") == prompt_text:
                    exists = True
                    break

            if not exists:
                existing.append(new_template)
                # 保持最近100条
                if len(existing) > 100:
                    existing = existing[-100:]

                self.memory_manager.add(
                    "successful_prompt_patterns",
                    existing,
                    level=MemoryLevel.LONG_TERM,
                    metadata={"_serialized": True}
                )
                debug("已同步到记忆层")
        except Exception as e:
            warning(f"保存到记忆层失败: {e}")

    def search_similar(
            self,
            query_text: str,
            top_k: Optional[int] = None,
            min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
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
            debug("提示词模板索引未初始化")
            return []

        if len(self._templates_cache) == 0:
            debug("提示词模板库为空")
            return []

        try:
            top_k = top_k or self.top_k
            min_score = min_score or self.min_similarity_score

            retriever = self.index.as_retriever(
                similarity_top_k=top_k,
                retriever_mode="similarity"
            )

            nodes = retriever.retrieve(query_text)

            results = []
            for node in nodes:
                score = node.score if hasattr(node, 'score') else 0

                if score < min_score:
                    continue

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

    def get_best_match(
            self,
            query_text: str,
            min_score: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取最佳匹配的提示词模板

        Args:
            query_text: 查询文本
            min_score: 最低相似度分数

        Returns:
            最佳匹配模板，或 None
        """
        results = self.search_similar(query_text, top_k=1, min_score=min_score)
        return results[0] if results else None

    def enhance_prompt(
            self,
            original_prompt: str,
            enhancement_mode: str = "append"
    ) -> str:
        """
        使用知识库增强提示词

        Args:
            original_prompt: 原始提示词
            enhancement_mode: 增强模式 (append, replace, hybrid)

        Returns:
            增强后的提示词
        """
        best_match = self.get_best_match(original_prompt)

        if not best_match:
            return original_prompt

        template = best_match["prompt"]
        score = best_match["score"]

        if enhancement_mode == "append":
            # 追加模式：保留原提示词，追加参考模板
            return f"{original_prompt}\n\n参考优秀模板:\n{template}"

        elif enhancement_mode == "replace":
            # 替换模式：用模板替换（保留关键信息）
            return self._merge_prompts(original_prompt, template)

        else:  # hybrid
            # 混合模式：智能融合
            return self._merge_prompts(original_prompt, template)

    def _merge_prompts(self, original: str, template: str) -> str:
        """
        智能融合两个提示词

        Args:
            original: 原始提示词
            template: 模板提示词

        Returns:
            融合后的提示词
        """
        # 提取原始提示词中的关键元素（场景、角色、动作等）
        # 这里实现简单的拼接，可以根据需要定制

        # 简单实现：提取模板中的结构，填充原始内容
        return f"{template}\n\n根据当前片段调整:\n{original}"

    def save_successful_prompt(
            self,
            fragment_id: str,
            prompt_text: str,
            quality_score: float,
            additional_metadata: Optional[Dict] = None
    ):
        """
        保存成功的提示词（在质量审查通过后调用）

        Args:
            fragment_id: 片段ID
            prompt_text: 提示词文本
            quality_score: 质量分数
            additional_metadata: 额外元数据
        """
        metadata = {
            "fragment_id": fragment_id,
            "quality_score": quality_score,
            "source": "quality_audit_passed"
        }

        if additional_metadata:
            metadata.update(additional_metadata)

        self.add_template(prompt_text, metadata)
        info(f"保存成功提示词: {fragment_id}, 质量分数: {quality_score}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "template_count": len(self._templates_cache),
            "has_index": self.index is not None,
            "storage_dir": self.storage_dir,
            "min_similarity_score": self.min_similarity_score,
            "top_k": self.top_k
        }

    def is_available(self) -> bool:
        """检查知识库是否可用（有模板数据）"""
        return self.index is not None and len(self._templates_cache) > 0

    def clear(self):
        """清空知识库"""
        self.index = None
        self._templates_cache = []

        if self.storage_dir:
            vector_store_path = os.path.join(self.storage_dir, "prompt_vector_store.json")
            if os.path.exists(vector_store_path):
                os.remove(vector_store_path)

            # ========== 删除缓存文件 ==========
            cache_path = os.path.join(self.storage_dir, "vector_store_cache.json")
            if os.path.exists(cache_path):
                os.remove(cache_path)

        info("提示词模板知识库已清空")
