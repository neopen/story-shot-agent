"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: prompt_template_manager.py
@Description: 提示词模板管理器 - 负责成功提示词模板的存储、检索和应用，支持剧本ID数据隔离
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/05/05
"""

import hashlib
import json
import os
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from llama_index.core import VectorStoreIndex, Document, load_index_from_storage
from llama_index.core.indices.base import BaseIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage import StorageContext

from penshot.logger import debug, info, error, warning
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
from penshot.neopen.knowledge.memory.memory_models import MemoryLevel


class PromptTemplateManager:
    """
    提示词模板管理器

    职责：
    1. 存储成功的提示词模板到向量数据库（支持按剧本ID隔离）
    2. 检索相似提示词模板（支持跨剧本和剧本内检索）
    3. 应用模板增强当前提示词
    4. 与记忆层同步

    数据隔离策略：
    - 每个剧本有独立的索引存储目录
    - 支持跨剧本检索（全局模板）和剧本内检索
    - 缓存区分剧本ID
    """

    def __init__(
            self,
            embedding_model,
            script_id,
            storage_dir: str = "data/embedding",
            memory_manager: Optional[MemoryManager] = None,
            chunk_size: int = 512,
            chunk_overlap: int = 20,
            min_similarity_score: float = 0.5,
            top_k: int = 3,
            max_cache_size: int = 200,
            max_metadata_length: int = 256
    ):
        """
        初始化提示词模板管理器

        Args:
            embedding_model: 嵌入模型
            memory_manager: 记忆管理器（用于加载历史成功模板）
            storage_dir: 基础存储目录
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
            min_similarity_score: 最低相似度分数
            top_k: 检索返回数量
            max_cache_size: 最大缓存数量
            max_metadata_length: 元数据最大长度（避免块大小警告）
        """
        self.embedding_model = embedding_model
        self.memory_manager = memory_manager
        self.base_storage_dir = storage_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_similarity_score = min_similarity_score
        self.top_k = top_k
        self.max_cache_size = max_cache_size
        self.max_metadata_length = max_metadata_length

        # 当前剧本ID（用于数据隔离）
        self._current_script_id: str = script_id

        # 按剧本ID管理的索引和缓存
        self._indices: Dict[str, Optional[BaseIndex]] = {}
        self._caches: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_loaded: Set[str] = set()

        # 节点解析器
        self.node_parser = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        # 递归保护栈
        self._processing_stack: Set[str] = set()

        # 剧本知识库（用于连续性检查等）
        self.script_kb = None
        self._init_script_kb()

        debug(f"提示词模板管理器初始化完成，存储目录: {self.base_storage_dir}")

    def set_current_script(self, script_id: str) -> None:
        """
        设置当前剧本ID，用于数据隔离

        Args:
            script_id: 剧本ID
        """
        if not script_id:
            warning("尝试设置空的剧本ID，已忽略")
            return

        self._current_script_id = script_id

        # 确保该剧本的缓存已加载
        if script_id not in self._cache_loaded:
            self._load_cache_for_script(script_id)
            self._load_index_for_script(script_id)

        info(f"切换到剧本: {script_id}, 模板数: {len(self._caches.get(script_id, []))}")

    def _get_script_storage_dir(self, script_id: str) -> str:
        """
        获取指定剧本的存储目录

        Args:
            script_id: 剧本ID

        Returns:
            存储目录路径
        """
        # 使用剧本ID的哈希作为子目录名，避免特殊字符问题
        # safe_name = hashlib.md5(script_id.encode('utf-8')).hexdigest()[:16]
        # script_dir = os.path.join(self.base_storage_dir, "prompt_templates", safe_name)
        script_dir = os.path.join(self.base_storage_dir, "prompt_templates", script_id)
        os.makedirs(script_dir, exist_ok=True)
        return script_dir

    def _get_cache_path(self, script_id: str) -> str:
        """
        获取缓存文件路径

        Args:
            script_id: 剧本ID

        Returns:
            缓存文件路径
        """
        script_dir = self._get_script_storage_dir(script_id)
        return os.path.join(script_dir, "templates_cache.json")

    def _get_index_dir(self, script_id: str) -> str:
        """
        获取索引目录路径

        Args:
            script_id: 剧本ID

        Returns:
            索引目录路径
        """
        script_dir = self._get_script_storage_dir(script_id)
        return os.path.join(script_dir, "index_store")

    def _load_cache_for_script(self, script_id: str) -> None:
        """
        加载指定剧本的缓存

        Args:
            script_id: 剧本ID
        """
        if script_id in self._cache_loaded:
            return

        cache_path = self._get_cache_path(script_id)

        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if isinstance(cache_data, list):
                        self._caches[script_id] = cache_data
                    else:
                        self._caches[script_id] = []
                    info(f"已加载剧本 {script_id} 的缓存，共 {len(self._caches[script_id])} 个模板")
            except Exception as e:
                warning(f"加载缓存失败: {cache_path}, {e}")
                self._caches[script_id] = []
        else:
            self._caches[script_id] = []

        self._cache_loaded.add(script_id)

    def _save_cache_for_script(self, script_id: str) -> None:
        """
        保存指定剧本的缓存

        Args:
            script_id: 剧本ID
        """
        if script_id not in self._caches:
            return

        cache_path = self._get_cache_path(script_id)

        try:
            if len(self._caches[script_id]) > self.max_cache_size:
                self._caches[script_id] = self._caches[script_id][-self.max_cache_size:]

            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._caches[script_id], f, ensure_ascii=False, indent=2)
            debug(f"已保存剧本 {script_id} 的缓存")
        except Exception as e:
            warning(f"保存缓存失败: {cache_path}, {e}")

    def _load_index_for_script(self, script_id: str) -> None:
        """
        加载指定剧本的索引

        注意：load_index_from_storage 的正确签名是：
        def load_index_from_storage(
            storage_context: StorageContext,
            index_id: Optional[str] = None,
            **kwargs: Any,
        ) -> BaseIndex

        Args:
            script_id: 剧本ID
        """
        index_dir = self._get_index_dir(script_id)

        if os.path.exists(index_dir):
            try:
                # 检查目录是否包含有效的索引文件
                vector_store_path = os.path.join(index_dir, "vector_store.json")
                if not os.path.exists(vector_store_path):
                    debug(f"索引目录缺少 vector_store.json，将创建新索引: {index_dir}")
                    self._indices[script_id] = None
                    return

                # 创建存储上下文
                storage_context = StorageContext.from_defaults(persist_dir=index_dir)

                # 使用正确的签名加载索引
                # load_index_from_storage 接受 storage_context 作为第一个参数
                # index_id 参数用于指定特定的索引ID（如有多个索引）
                self._indices[script_id] = load_index_from_storage(
                    storage_context=storage_context,
                    index_id=None  # 使用默认索引ID
                )
                info(f"已加载剧本 {script_id} 的索引")
            except Exception as e:
                warning(f"加载索引失败: {index_dir}, {e}")
                self._indices[script_id] = None
        else:
            self._indices[script_id] = None
            debug(f"索引目录不存在，将创建新索引: {index_dir}")

    def _save_index_for_script(self, script_id: str) -> None:
        """
        保存指定剧本的索引

        Args:
            script_id: 剧本ID
        """
        index = self._indices.get(script_id)
        if not index:
            return

        index_dir = self._get_index_dir(script_id)

        try:
            os.makedirs(index_dir, exist_ok=True)
            index.storage_context.persist(persist_dir=index_dir)
            debug(f"已保存剧本 {script_id} 的索引")
        except Exception as e:
            warning(f"保存索引失败: {index_dir}, {e}")

    def _create_index_for_script(self, script_id: str, documents: List[Document]) -> bool:
        """
        为剧本创建新索引

        Args:
            script_id: 剧本ID
            documents: 文档列表

        Returns:
            是否创建成功
        """
        if not documents:
            self._indices[script_id] = None
            return False

        try:
            # 创建索引时需要指定 embed_model
            self._indices[script_id] = VectorStoreIndex.from_documents(
                documents,
                embed_model=self.embedding_model,
                transformations=[self.node_parser]
            )
            self._save_index_for_script(script_id)
            info(f"为剧本 {script_id} 创建索引，共 {len(documents)} 个模板")
            return True
        except Exception as e:
            error(f"创建索引失败: {script_id}, {e}")
            self._indices[script_id] = None
            return False

    def _rebuild_index_for_script(self, script_id: str) -> bool:
        """
        从缓存重建剧本的索引

        Args:
            script_id: 剧本ID

        Returns:
            是否重建成功
        """
        cache = self._caches.get(script_id, [])
        if not cache:
            debug(f"剧本 {script_id} 无缓存数据，跳过索引重建")
            self._indices[script_id] = None
            return False

        try:
            documents = []
            for item in cache:
                prompt_text = item.get("prompt", "")
                if not prompt_text:
                    continue

                metadata = item.get("metadata", {})
                doc = Document(
                    text=prompt_text,
                    metadata={
                        "type": "prompt_template",
                        "prompt": prompt_text,
                        "hash": self._generate_template_hash(prompt_text),
                        "script_id": script_id,
                        "timestamp": item.get("added_at", datetime.now().isoformat()),
                        "quality_score": metadata.get("quality_score", 0),
                        "fragment_id": metadata.get("fragment_id", ""),
                        "scene": metadata.get("scene", ""),
                        "style": metadata.get("style", ""),
                        **metadata
                    }
                )
                documents.append(doc)

            if documents:
                return self._create_index_for_script(script_id, documents)
            else:
                self._indices[script_id] = None
                return False

        except Exception as e:
            error(f"重建索引失败: {script_id}, {e}")
            self._indices[script_id] = None
            return False

    def _get_current_index(self) -> Optional[BaseIndex]:
        """
        获取当前剧本的索引

        Returns:
            索引实例
        """
        if not self._current_script_id:
            warning("未设置当前剧本ID，无法获取索引")
            return None

        return self._indices.get(self._current_script_id)

    def _get_current_cache(self) -> List[Dict[str, Any]]:
        """
        获取当前剧本的缓存

        Returns:
            缓存列表
        """
        if not self._current_script_id:
            return []

        return self._caches.get(self._current_script_id, [])

    def _truncate_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        截断过长的元数据，避免块大小警告

        Args:
            metadata: 原始元数据

        Returns:
            截断后的元数据
        """
        truncated = {}

        for key, value in metadata.items():
            if isinstance(value, str) and len(value) > self.max_metadata_length:
                truncated[key] = value[:self.max_metadata_length - 3] + "..."
                warning(f"元数据字段 '{key}' 过长，已截断")
            elif isinstance(value, dict):
                truncated[key] = self._truncate_metadata(value)
            else:
                truncated[key] = value

        return truncated

    def _generate_template_hash(self, prompt_text: str) -> str:
        """
        生成模板哈希值用于去重

        Args:
            prompt_text: 提示词文本

        Returns:
            哈希值
        """
        # 标准化：去除空白差异
        normalized = ' '.join(prompt_text.strip().split())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]

    def _init_script_kb(self) -> None:
        """初始化剧本知识库"""
        try:
            storage_dir = os.path.join(self.base_storage_dir, "script_kb") if self.base_storage_dir else None
            self.script_kb = ScriptKnowledgeBase(
                embeddings=self.embedding_model,
                storage_dir=storage_dir,
                script_id=self._current_script_id,
                chunk_size=512,
                chunk_overlap=20
            )
            info("剧本知识库初始化完成")
        except Exception as e:
            warning(f"剧本知识库初始化失败: {e}")
            self.script_kb = None

    def add_script(self, script_text: str, script_id: str) -> None:
        """
        添加剧本到知识库

        Args:
            script_text: 剧本文本
            script_id: 剧本ID
        """
        if self.script_kb:
            try:
                self.script_kb.add_script_text(script_text, script_id)
                info(f"已添加剧本到知识库: {script_id}")
            except Exception as e:
                warning(f"添加剧本到知识库失败: {e}")

    def add_parsed_script(self, parsed_script, script_id: Optional[str] = None) -> Dict[str, Any]:
        """
        添加已解析的剧本到知识库

        Args:
            parsed_script: 已解析的剧本对象
            script_id: 剧本ID

        Returns:
            添加结果
        """
        if self.script_kb:
            return self.script_kb.add_parsed_script(parsed_script, script_id)
        return {"status": "failed", "error": "知识库未初始化"}

    def is_script_kb_available(self) -> bool:
        """
        检查剧本知识库是否可用

        Returns:
            是否可用
        """
        if not self.script_kb:
            return False
        try:
            stats = self.script_kb.get_statistics()
            return stats.get("script_count", 0) > 0
        except Exception:
            return False

    def search_similar_scene(self, query_text: str, script_id: str, top_k: int = 3) -> List[Dict]:
        """
        搜索相似场景（用于连续性检查）

        Args:
            query_text: 查询文本
            top_k: 返回数量

        Returns:
            相似场景列表
        """
        if not self.script_kb:
            return []

        try:
            result = self.script_kb.query(
                query_text=query_text,
                script_id=script_id,
                search_type="similarity",
                similarity_top_k=top_k,
                use_rerank=True
            )
            return result.get("results", [])
        except Exception as e:
            warning(f"搜索相似场景失败: {e}")
            return []

    def _is_duplicate(self, script_id: str, prompt_text: str) -> bool:
        """
        检查模板是否已存在

        Args:
            script_id: 剧本ID
            prompt_text: 提示词文本

        Returns:
            是否存在
        """
        cache = self._caches.get(script_id, [])
        prompt_hash = self._generate_template_hash(prompt_text)

        for item in cache:
            if item.get("hash") == prompt_hash:
                return True
            if item.get("prompt") == prompt_text:
                return True

        return False

    def add_template(
            self,
            prompt_text: str,
            metadata: Dict[str, Any],
            script_id: str,
            save_to_memory: bool = True
    ) -> bool:
        """
        添加成功提示词模板

        Args:
            prompt_text: 提示词文本
            metadata: 元数据（fragment_id, scene, style, quality_score等）
            script_id: 剧本ID（默认使用当前剧本）
            save_to_memory: 是否同时保存到记忆层

        Returns:
            是否添加成功
        """
        target_script_id = script_id or self._current_script_id

        if not target_script_id:
            warning("未指定剧本ID且未设置当前剧本，无法添加模板")
            return False

        # 防止递归
        stack_key = f"add_template_{target_script_id}_{hash(prompt_text[:100])}"
        if stack_key in self._processing_stack:
            warning(f"检测到递归调用，跳过添加模板")
            return False

        self._processing_stack.add(stack_key)

        try:
            # 限制提示词长度
            if len(prompt_text) > 2000:
                prompt_text = prompt_text[:1997] + "..."
                warning(f"提示词过长，已截断")

            # 去重检查
            if self._is_duplicate(target_script_id, prompt_text):
                debug("提示词模板已存在，跳过添加")
                return False

            # 截断过长的元数据
            truncated_metadata = self._truncate_metadata(metadata)

            # 生成哈希
            template_hash = self._generate_template_hash(prompt_text)

            # 创建文档
            doc_metadata = {
                "type": "prompt_template",
                "prompt": prompt_text,
                "hash": template_hash,
                "script_id": target_script_id,
                "timestamp": datetime.now().isoformat(),
                "quality_score": truncated_metadata.get("quality_score", 0),
                "fragment_id": truncated_metadata.get("fragment_id", ""),
                "scene": truncated_metadata.get("scene", ""),
                "style": truncated_metadata.get("style", ""),
                "shot_type": truncated_metadata.get("shot_type", ""),
                "duration": truncated_metadata.get("duration", 0),
                **truncated_metadata
            }

            doc = Document(
                text=prompt_text,
                metadata=doc_metadata
            )

            # 确保该剧本的索引和缓存已加载
            if target_script_id not in self._cache_loaded:
                self._load_cache_for_script(target_script_id)
                self._load_index_for_script(target_script_id)

            # 添加到索引
            current_index = self._indices.get(target_script_id)
            if not current_index:
                # 创建新索引
                success = self._create_index_for_script(target_script_id, [doc])
                if not success:
                    error(f"创建索引失败，无法添加模板")
                    return False
            else:
                # 插入到现有索引
                nodes = self.node_parser.get_nodes_from_documents([doc])
                current_index.insert_nodes(nodes)
                self._save_index_for_script(target_script_id)

            # 添加到缓存
            if target_script_id not in self._caches:
                self._caches[target_script_id] = []

            self._caches[target_script_id].append({
                "prompt": prompt_text,
                "hash": template_hash,
                "metadata": truncated_metadata,
                "added_at": datetime.now().isoformat()
            })

            # 保存缓存
            self._save_cache_for_script(target_script_id)

            # 保存到记忆层（全局，不隔离）
            if save_to_memory and self.memory_manager:
                self._save_to_memory(prompt_text, truncated_metadata)

            debug(f"添加提示词模板成功，剧本: {target_script_id}, 当前总数: {len(self._caches[target_script_id])}")
            return True

        except Exception as e:
            error(f"添加提示词模板失败: {e}")
            return False

        finally:
            self._processing_stack.discard(stack_key)

    def _save_to_memory(self, prompt_text: str, metadata: Dict[str, Any]) -> None:
        """
        保存模板到全局记忆层（跨剧本共享）

        Args:
            prompt_text: 提示词文本
            metadata: 元数据
        """
        if not self.memory_manager:
            return

        try:
            existing = self.memory_manager.get(
                "successful_prompt_patterns",
                level=MemoryLevel.LONG_TERM,
                default=[]
            )

            if not isinstance(existing, list):
                existing = []

            # 去重
            template_hash = self._generate_template_hash(prompt_text)
            exists = False
            for item in existing:
                if isinstance(item, dict) and item.get("hash") == template_hash:
                    exists = True
                    break

            if not exists:
                new_template = {
                    "hash": template_hash,
                    "prompt": prompt_text,
                    "metadata": metadata,
                    "timestamp": datetime.now().isoformat()
                }
                existing.append(new_template)

                # 保持最近200条
                if len(existing) > 200:
                    existing = existing[-200:]

                self.memory_manager.add(
                    "successful_prompt_patterns",
                    existing,
                    level=MemoryLevel.LONG_TERM,
                    metadata={"_serialized": True}
                )
                debug("已同步到全局记忆层")

        except Exception as e:
            warning(f"保存到记忆层失败: {e}")

    def search_similar(
            self,
            query_text: str,
            script_id: Optional[str] = None,
            top_k: Optional[int] = None,
            min_score: Optional[float] = None,
            include_global: bool = True
    ) -> List[Dict[str, Any]]:
        """
        搜索相似提示词模板

        Args:
            query_text: 查询文本
            script_id: 剧本ID（不指定则使用当前剧本）
            top_k: 返回数量
            min_score: 最低相似度分数
            include_global: 是否包含全局模板（其他剧本）

        Returns:
            相似模板列表
        """
        target_script_id = script_id or self._current_script_id

        if not target_script_id:
            debug("未指定剧本ID且未设置当前剧本，无法搜索")
            return []

        # 确保缓存已加载
        if target_script_id not in self._cache_loaded:
            self._load_cache_for_script(target_script_id)
            self._load_index_for_script(target_script_id)

        current_index = self._indices.get(target_script_id)
        if not current_index:
            debug(f"剧本 {target_script_id} 的索引未初始化")
            return []

        cache = self._caches.get(target_script_id, [])
        if len(cache) == 0:
            debug(f"剧本 {target_script_id} 的模板库为空")
            return []

        try:
            top_k = top_k or self.top_k
            min_score = min_score or self.min_similarity_score

            retriever = current_index.as_retriever(
                similarity_top_k=top_k,
                retriever_mode="similarity"
            )

            nodes = retriever.retrieve(query_text)

            results = []
            for node in nodes:
                score = getattr(node, 'score', 0)

                if score < min_score:
                    continue

                if node.node.metadata.get("type") != "prompt_template":
                    continue

                results.append({
                    "prompt": node.node.text,
                    "score": score,
                    "metadata": node.node.metadata,
                    "node_id": node.node.node_id,
                    "script_id": node.node.metadata.get("script_id", target_script_id)
                })

            debug(f"搜索相似提示词: '{query_text[:50]}...', 找到 {len(results)} 个结果")
            return results[:top_k]

        except Exception as e:
            error(f"搜索相似提示词失败: {e}")
            return []

    def get_best_match(
            self,
            query_text: str,
            script_id: Optional[str] = None,
            min_score: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取最佳匹配的提示词模板

        Args:
            query_text: 查询文本
            script_id: 剧本ID
            min_score: 最低相似度分数

        Returns:
            最佳匹配模板，或 None
        """
        results = self.search_similar(query_text, script_id=script_id, top_k=1, min_score=min_score)
        return results[0] if results else None

    def enhance_prompt(
            self,
            original_prompt: str,
            script_id: Optional[str] = None,
            enhancement_mode: str = "append"
    ) -> str:
        """
        使用知识库增强提示词

        Args:
            original_prompt: 原始提示词
            script_id: 剧本ID
            enhancement_mode: 增强模式 (append, replace, hybrid, none)

        Returns:
            增强后的提示词
        """
        if enhancement_mode == "none":
            return original_prompt

        best_match = self.get_best_match(original_prompt, script_id=script_id)

        if not best_match:
            return original_prompt

        template = best_match["prompt"]

        if enhancement_mode == "append":
            return f"{original_prompt}\n\n参考优秀模板:\n{template}"

        elif enhancement_mode == "replace":
            return self._merge_prompts(original_prompt, template)

        else:
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
        return f"{template}\n\n根据当前片段调整:\n{original}"

    def save_successful_prompt(
            self,
            fragment_id: str,
            prompt_text: str,
            quality_score: float,
            script_id: str,
            additional_metadata: Optional[Dict] = None
    ) -> bool:
        """
        保存成功的提示词（在质量审查通过后调用）

        Args:
            fragment_id: 片段ID
            prompt_text: 提示词文本
            quality_score: 质量分数
            script_id: 剧本ID
            additional_metadata: 额外元数据

        Returns:
            是否保存成功
        """
        metadata = {
            "fragment_id": fragment_id,
            "quality_score": quality_score,
            "source": "quality_audit_passed"
        }

        if additional_metadata:
            metadata.update(additional_metadata)

        return self.add_template(prompt_text, metadata, script_id=script_id)

    def get_statistics(self, script_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取统计信息

        Args:
            script_id: 剧本ID（不指定则返回全局统计）

        Returns:
            统计信息字典
        """
        if script_id:
            cache = self._caches.get(script_id, [])
            has_index = self._indices.get(script_id) is not None
            return {
                "script_id": script_id,
                "template_count": len(cache),
                "has_index": has_index,
                "storage_dir": self._get_script_storage_dir(script_id),
                "min_similarity_score": self.min_similarity_score,
                "top_k": self.top_k,
                "max_cache_size": self.max_cache_size
            }
        else:
            return {
                "total_scripts": len(self._caches),
                "scripts": {
                    sid: {
                        "template_count": len(cache),
                        "has_index": self._indices.get(sid) is not None
                    }
                    for sid, cache in self._caches.items()
                },
                "current_script": self._current_script_id,
                "global_settings": {
                    "min_similarity_score": self.min_similarity_score,
                    "top_k": self.top_k,
                    "max_cache_size": self.max_cache_size,
                    "max_metadata_length": self.max_metadata_length
                }
            }

    def is_available(self, script_id: Optional[str] = None) -> bool:
        """
        检查知识库是否可用（有模板数据）

        Args:
            script_id: 剧本ID

        Returns:
            是否可用
        """
        target_id = script_id or self._current_script_id
        if not target_id:
            return False

        cache = self._caches.get(target_id, [])
        return self._indices.get(target_id) is not None and len(cache) > 0

    def clear_for_script(self, script_id: str) -> bool:
        """
        清空指定剧本的知识库

        Args:
            script_id: 剧本ID

        Returns:
            是否清空成功
        """
        try:
            # 清空索引
            self._indices[script_id] = None

            # 清空缓存
            self._caches[script_id] = []

            # 删除存储目录
            script_dir = self._get_script_storage_dir(script_id)
            if os.path.exists(script_dir):
                shutil.rmtree(script_dir)
                info(f"已删除剧本 {script_id} 的存储目录")

            # 重置加载标记
            self._cache_loaded.discard(script_id)

            info(f"已清空剧本 {script_id} 的知识库")
            return True

        except Exception as e:
            error(f"清空剧本 {script_id} 知识库失败: {e}")
            return False

    def clear_all(self) -> bool:
        """
        清空所有剧本的知识库

        Returns:
            是否清空成功
        """
        try:
            for script_id in list(self._caches.keys()):
                self.clear_for_script(script_id)

            self._indices.clear()
            self._caches.clear()
            self._cache_loaded.clear()
            self._current_script_id = None

            info("已清空所有知识库")
            return True

        except Exception as e:
            error(f"清空所有知识库失败: {e}")
            return False
