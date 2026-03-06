"""
@FileName: llama_index_knowledge.py
@Description: 剧本知识库管理模块，提供基于LlamaIndex的结构化剧本知识库管理功能
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter, SentenceWindowNodeParser
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import Document
from llama_index.core.vector_stores import SimpleVectorStore

from hengshot.logger import debug, info, error, warning
from hengshot.hengline.tools.script_parser_tool import parse_script_to_documents, parse_script_file_to_documents


class ScriptKnowledgeBase:
    """
    剧本知识库管理类
    负责剧本的解析、索引创建、检索优化等功能
    """

    def __init__(self,
                 embedding_model: Optional[BaseEmbedding] = None,
                 storage_dir: Optional[str] = None,
                 chunk_size: int = 512,
                 chunk_overlap: int = 20):
        """
        初始化剧本知识库
        
        Args:
            embedding_model: 嵌入模型
            storage_dir: 存储目录
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
        """
        self.embedding_model = embedding_model
        self.storage_dir = storage_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # 知识库组件
        self.index = None
        self.retriever = None
        self.storage_context = None
        self.vector_store = None

        # 解析结果缓存
        self.parsed_results = {}
        self.document_cache = {}

        # 初始化存储
        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)
            self._load_storage()

        debug("剧本知识库初始化完成")

    def add_script_text(self, script_text: str, script_id: str = None) -> Dict[str, Any]:
        """
        添加剧本文本到知识库
        
        Args:
            script_text: 剧本文本
            script_id: 剧本唯一标识
            
        Returns:
            添加结果信息
        """
        try:
            if script_id is None:
                script_id = f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            debug(f"添加剧本文本: {script_id}")

            # 解析剧本
            parsed_result, documents = parse_script_to_documents(script_text)

            # 缓存解析结果
            self.parsed_results[script_id] = parsed_result
            self.document_cache[script_id] = documents

            # 添加到索引
            self._add_documents_to_index(documents, script_id)

            # 保存存储
            if self.storage_dir:
                self._save_storage()
                self._save_parsed_result(script_id, parsed_result)

            info(f"成功添加剧本: {script_id}, 包含{len(documents)}个文档")

            return {
                "status": "success",
                "script_id": script_id,
                "scene_count": parsed_result["stats"]["scene_count"],
                "character_count": parsed_result["stats"]["character_count"],
                "document_count": len(documents)
            }

        except Exception as e:
            error(f"添加剧本文本失败: {str(e)}")
            raise

    def add_script_file(self, file_path: str, script_id: str = None) -> Dict[str, Any]:
        """
        添加剧本文件到知识库
        
        Args:
            file_path: 剧本文件路径
            script_id: 剧本唯一标识
            
        Returns:
            添加结果信息
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"剧本文件不存在: {file_path}")

            if script_id is None:
                # 从文件名生成ID
                base_name = os.path.basename(file_path)
                script_id = f"script_{os.path.splitext(base_name)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            debug(f"添加剧本文件: {file_path} as {script_id}")

            # 解析剧本
            parsed_result, documents = parse_script_file_to_documents(file_path)

            # 缓存解析结果
            self.parsed_results[script_id] = parsed_result
            self.document_cache[script_id] = documents

            # 添加到索引
            self._add_documents_to_index(documents, script_id)

            # 保存存储
            if self.storage_dir:
                self._save_storage()
                self._save_parsed_result(script_id, parsed_result)

            info(f"成功添加剧本文件: {file_path}, 包含{len(documents)}个文档")

            return {
                "status": "success",
                "script_id": script_id,
                "file_path": file_path,
                "scene_count": parsed_result["stats"]["scene_count"],
                "character_count": parsed_result["stats"]["character_count"],
                "document_count": len(documents)
            }

        except Exception as e:
            error(f"添加剧本文件失败: {str(e)}")
            raise

    def add_script_directory(self, directory_path: str, recursive: bool = True) -> Dict[str, Any]:
        """
        添加目录中的所有剧本文件到知识库
        
        Args:
            directory_path: 目录路径
            recursive: 是否递归处理子目录
            
        Returns:
            添加结果信息
        """
        try:
            if not os.path.exists(directory_path):
                raise FileNotFoundError(f"目录不存在: {directory_path}")

            debug(f"添加剧本目录: {directory_path}, 递归: {recursive}")

            # 支持的文件扩展名
            script_extensions = ['.txt', '.pdf', '.docx', '.doc', '.rtf', '.md']

            added_scripts = []
            total_scenes = 0
            total_characters = 0
            total_documents = 0

            # 遍历目录
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    # 检查文件扩展名
                    ext = os.path.splitext(file)[1].lower()
                    if ext in script_extensions:
                        file_path = os.path.join(root, file)
                        try:
                            # 添加剧本文件
                            result = self.add_script_file(file_path)
                            added_scripts.append(result)
                            total_scenes += result["scene_count"]
                            total_characters += result["character_count"]
                            total_documents += result["document_count"]
                        except Exception as e:
                            warning(f"处理文件失败: {file_path}, 错误: {str(e)}")
                            continue

                # 如果不递归，只处理当前目录
                if not recursive:
                    break

            info(f"成功添加目录中的剧本: {len(added_scripts)}个文件, 共{total_scenes}个场景, {total_characters}个角色, {total_documents}个文档")

            return {
                "status": "success",
                "directory_path": directory_path,
                "added_scripts": added_scripts,
                "script_count": len(added_scripts),
                "total_scenes": total_scenes,
                "total_characters": total_characters,
                "total_documents": total_documents
            }

        except Exception as e:
            error(f"添加剧本目录失败: {str(e)}")
            raise

    def create_retriever(self, search_type: str = "similarity", similarity_top_k: int = 5,
                         use_rerank: bool = False, rerank_model: str = "BAAI/bge-reranker-large") -> BaseRetriever:
        """
        创建检索器
        
        Args:
            search_type: 搜索类型 (similarity, mmr)
            similarity_top_k: 相似性检索的文档数量
            use_rerank: 是否使用重排序
            rerank_model: 重排序模型名称
            
        Returns:
            检索器实例
        """
        try:
            if not self.index:
                raise ValueError("索引未创建，请先添加剧本")

            # 创建基础检索器
            if search_type == "mmr":
                retriever = self.index.as_retriever(
                    retriever_mode="mmr",
                    similarity_top_k=similarity_top_k,
                    mmr_threshold=0.8
                )
            else:
                retriever = self.index.as_retriever(
                    retriever_mode="similarity",
                    similarity_top_k=similarity_top_k
                )

            # 添加重排序
            if use_rerank:
                rerank = SentenceTransformerRerank(
                    model=rerank_model,
                    top_n=min(3, similarity_top_k)
                )
                retriever = self.index.as_retriever(
                    retriever_mode=search_type,
                    similarity_top_k=similarity_top_k,
                    node_postprocessors=[rerank]
                )

            self.retriever = retriever
            debug(f"创建检索器成功: 类型={search_type}, top_k={similarity_top_k}, 重排序={use_rerank}")
            return retriever

        except Exception as e:
            error(f"创建检索器失败: {str(e)}")
            raise

    def query(self, query_text: str, search_type: str = "similarity", similarity_top_k: int = 5,
              use_rerank: bool = False, rerank_model: str = "BAAI/bge-reranker-large") -> Dict[str, Any]:
        """
        查询知识库
        
        Args:
            query_text: 查询文本
            search_type: 搜索类型
            similarity_top_k: 相似性检索的文档数量
            use_rerank: 是否使用重排序
            rerank_model: 重排序模型名称
            
        Returns:
            查询结果
        """
        try:
            if not self.index:
                raise ValueError("索引未创建，请先添加剧本")

            debug(f"执行查询: {query_text}")

            # 如果没有检索器或参数变化，创建新的检索器
            if not self.retriever or not self._check_retriever_params(search_type, similarity_top_k, use_rerank):
                self.create_retriever(search_type, similarity_top_k, use_rerank, rerank_model)

            # 执行检索
            nodes = self.retriever.retrieve(query_text)

            # 格式化结果
            results = []
            for i, node in enumerate(nodes):
                result = {
                    "id": str(node.node.node_id),
                    "score": node.score,
                    "text": node.node.text,
                    "metadata": dict(node.node.metadata),
                    "rank": i + 1
                }
                results.append(result)

            info(f"查询完成: '{query_text}'，返回{len(results)}个结果")

            return {
                "query": query_text,
                "results": results,
                "total_results": len(results),
                "search_type": search_type,
                "similarity_top_k": similarity_top_k,
                "use_rerank": use_rerank
            }

        except Exception as e:
            error(f"查询失败: {str(e)}")
            raise

    def query_scene(self, scene_number: int) -> Optional[Dict[str, Any]]:
        """
        根据场景编号查询场景信息
        
        Args:
            scene_number: 场景编号
            
        Returns:
            场景信息字典
        """
        try:
            for script_id, parsed_result in self.parsed_results.items():
                for scene in parsed_result.get("scenes", []):
                    if scene.get("number") == scene_number:
                        return scene

            debug(f"未找到场景编号: {scene_number}")
            return None

        except Exception as e:
            error(f"查询场景失败: {str(e)}")
            raise

    def query_character(self, character_name: str) -> Optional[Dict[str, Any]]:
        """
        根据角色名称查询角色信息
        
        Args:
            character_name: 角色名称
            
        Returns:
            角色信息字典
        """
        try:
            for script_id, parsed_result in self.parsed_results.items():
                if character_name in parsed_result.get("characters", {}):
                    return parsed_result["characters"][character_name]

            debug(f"未找到角色: {character_name}")
            return None

        except Exception as e:
            error(f"查询角色失败: {str(e)}")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            统计信息字典
        """
        total_scenes = 0
        total_characters = 0
        total_documents = 0
        script_count = len(self.parsed_results)

        for parsed_result in self.parsed_results.values():
            total_scenes += parsed_result.get("stats", {}).get("scene_count", 0)
            total_characters += parsed_result.get("stats", {}).get("character_count", 0)

        # 计算总文档数
        for documents in self.document_cache.values():
            total_documents += len(documents)

        statistics = {
            "script_count": script_count,
            "scene_count": total_scenes,
            "character_count": total_characters,
            "document_count": total_documents,
            "parsed_scripts": list(self.parsed_results.keys()),
            "embedding_model": str(self.embedding_model) if self.embedding_model else None,
            "storage_dir": self.storage_dir,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap
        }

        return statistics

    def clear(self):
        """
        清空知识库
        """
        try:
            self.index = None
            self.retriever = None
            self.vector_store = None
            self.storage_context = None
            self.parsed_results = {}
            self.document_cache = {}

            # 清空存储目录
            if self.storage_dir:
                for file in os.listdir(self.storage_dir):
                    file_path = os.path.join(self.storage_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)

            debug("知识库已清空")

        except Exception as e:
            error(f"清空知识库失败: {str(e)}")
            raise

    def _add_documents_to_index(self, documents: List[Document], script_id: str):
        """
        添加文档到索引
        
        Args:
            documents: 文档列表
            script_id: 剧本ID
        """
        try:
            # 为文档添加剧本ID元数据
            for doc in documents:
                doc.metadata["script_id"] = script_id
                doc.metadata["added_at"] = datetime.now().isoformat()

            # 创建节点解析器
            if self.chunk_size > 1000:
                # 对于长文本使用句子窗口解析器
                node_parser = SentenceWindowNodeParser(
                    window_size=3,
                    window_metadata_key="window",
                    original_text_metadata_key="original_text"
                )
            else:
                # 使用标准句子解析器
                node_parser = SentenceSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap
                )

            # 如果索引不存在，创建新索引
            if not self.index:
                if not self.vector_store:
                    self.vector_store = SimpleVectorStore()
                    self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)

                self.index = VectorStoreIndex.from_documents(
                    documents,
                    storage_context=self.storage_context,
                    transformations=[node_parser],
                    embed_model=self.embedding_model,
                    show_progress=True
                )
            else:
                # 向现有索引添加文档
                nodes = node_parser.get_nodes_from_documents(documents)
                self.index.insert_nodes(nodes)

            debug(f"已添加{len(documents)}个文档到索引，剧本ID: {script_id}")

        except Exception as e:
            error(f"添加文档到索引失败: {str(e)}")
            raise

    def _load_storage(self):
        """
        加载存储的索引和解析结果
        """
        try:
            # 加载向量存储
            vector_store_path = os.path.join(self.storage_dir, "vector_store.json")
            if os.path.exists(vector_store_path):
                self.vector_store = SimpleVectorStore.from_persist_path(vector_store_path)
                self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
                self.index = VectorStoreIndex.from_vector_store(
                    self.vector_store,
                    storage_context=self.storage_context,
                    embed_model=self.embedding_model
                )
                debug("已加载向量存储")

            # 加载解析结果
            parsed_dir = os.path.join(self.storage_dir, "parsed_results")
            if os.path.exists(parsed_dir):
                for file in os.listdir(parsed_dir):
                    if file.endswith(".json"):
                        script_id = os.path.splitext(file)[0]
                        file_path = os.path.join(parsed_dir, file)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            self.parsed_results[script_id] = json.load(f)
                debug(f"已加载{len(self.parsed_results)}个解析结果")

        except Exception as e:
            warning(f"加载存储失败: {str(e)}")

    def _save_storage(self):
        """
        保存索引和解析结果
        """
        try:
            if self.vector_store and self.storage_dir:
                vector_store_path = os.path.join(self.storage_dir, "vector_store.json")
                self.vector_store.persist(persist_path=vector_store_path)
                debug("已保存向量存储")
        except Exception as e:
            warning(f"保存存储失败: {str(e)}")

    def _save_parsed_result(self, script_id: str, parsed_result: Dict[str, Any]):
        """
        保存解析结果
        
        Args:
            script_id: 剧本ID
            parsed_result: 解析结果
        """
        try:
            if self.storage_dir:
                parsed_dir = os.path.join(self.storage_dir, "parsed_results")
                os.makedirs(parsed_dir, exist_ok=True)

                file_path = os.path.join(parsed_dir, f"{script_id}.json")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_result, f, ensure_ascii=False, indent=2)

                debug(f"已保存解析结果: {script_id}")
        except Exception as e:
            warning(f"保存解析结果失败: {str(e)}")

    def _check_retriever_params(self, search_type: str, similarity_top_k: int, use_rerank: bool) -> bool:
        """
        检查检索器参数是否匹配
        
        Args:
            search_type: 搜索类型
            similarity_top_k: 相似性检索的文档数量
            use_rerank: 是否使用重排序
            
        Returns:
            参数是否匹配
        """
        # 简单检查，实际项目中可以更详细地检查检索器的配置
        return hasattr(self.retriever, '_retriever_mode') and self.retriever._retriever_mode == search_type


def create_script_knowledge_base(embedding_model=None, storage_dir=None) -> ScriptKnowledgeBase:
    """
    创建剧本知识库实例
    
    Args:
        embedding_model: 嵌入模型
        storage_dir: 存储目录
        
    Returns:
        剧本知识库实例
    """
    return ScriptKnowledgeBase(embedding_model=embedding_model, storage_dir=storage_dir)
