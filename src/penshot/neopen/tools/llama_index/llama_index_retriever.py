"""
@FileName: llama_index_retriever.py
@Description: LlamaIndex 文档检索模块，提供高效的文档检索功能，支持多种检索策略
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/12/18
"""

from typing import List, Dict, Optional, Any

from llama_index.core import VectorStoreIndex
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.schema import NodeWithScore

from penshot.logger import debug, info, error
from .llama_index_tool import get_retriever_from_index


class DocumentRetriever:
    """
    文档检索器类
    提供多种文档检索方法
    """
    
    def __init__(self,
                 index: VectorStoreIndex,
                 similarity_top_k: int = 3,
                 search_type: str = "similarity",
                 similarity_threshold: Optional[float] = None,
                 **kwargs):
        """
        初始化文档检索器
        
        Args:
            index: 向量存储索引
            similarity_top_k: 返回的最相似文档数量
            search_type: 搜索类型，支持 "similarity", "mmr"
            similarity_threshold: 相似度阈值，低于此值的结果将被过滤
            **kwargs: 额外参数
        """
        self.index = index
        self.similarity_top_k = similarity_top_k
        self.search_type = search_type
        self.similarity_threshold = similarity_threshold
        self.retriever = None
        self.query_engine = None
        
        # 初始化检索器
        self._init_retriever(**kwargs)
    
    def _init_retriever(self, **kwargs):
        """
        初始化检索器
        """
        try:
            # 获取基础检索器
            self.retriever = get_retriever_from_index(
                self.index,
                similarity_top_k=self.similarity_top_k,
                search_type=self.search_type,
                **kwargs
            )
            
            # 如果设置了相似度阈值，添加后处理器
            if self.similarity_threshold is not None:
                postprocessors = [
                    SimilarityPostprocessor(similarity_cutoff=self.similarity_threshold)
                ]
                self.query_engine = RetrieverQueryEngine(
                    retriever=self.retriever,
                    node_postprocessors=postprocessors
                )
            else:
                self.query_engine = RetrieverQueryEngine(retriever=self.retriever)
                
            debug(f"检索器初始化完成: type={self.search_type}, top_k={self.similarity_top_k}")
            
        except Exception as e:
            error(f"初始化检索器失败: {str(e)}")
            raise
    
    def retrieve(self, query: str, **kwargs) -> List[NodeWithScore]:
        """
        检索与查询相关的文档节点
        
        Args:
            query: 查询文本
            **kwargs: 额外的检索参数
            
        Returns:
            NodeWithScore对象列表，包含节点和相关分数
        """
        try:
            debug(f"执行检索查询: {query[:50]}...")
            
            # 使用检索器执行检索
            nodes = self.retriever.retrieve(query, **kwargs)
            
            # 如果设置了相似度阈值，过滤结果
            if self.similarity_threshold is not None:
                filtered_nodes = [
                    node for node in nodes 
                    if node.score >= self.similarity_threshold
                ]
                debug(f"检索到{len(nodes)}个节点，过滤后剩余{len(filtered_nodes)}个")
                return filtered_nodes
            
            debug(f"成功检索到{len(nodes)}个相关节点")
            return nodes
            
        except Exception as e:
            error(f"检索失败: {str(e)}")
            return []
    
    def query(self, query: str, **kwargs) -> str:
        """
        使用查询引擎执行查询并获取回答
        
        Args:
            query: 查询文本
            **kwargs: 额外的查询参数
            
        Returns:
            查询结果文本
        """
        try:
            debug(f"执行问答查询: {query[:50]}...")
            
            response = self.query_engine.query(query, **kwargs)
            result = str(response)
            
            debug(f"查询成功完成")
            return result
            
        except Exception as e:
            error(f"查询失败: {str(e)}")
            return f"查询失败: {str(e)}"
    
    def retrieve_documents(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        检索文档并返回结构化结果
        
        Args:
            query: 查询文本
            **kwargs: 额外参数
            
        Returns:
            包含文档信息的字典列表
        """
        nodes = self.retrieve(query, **kwargs)
        
        results = []
        for node in nodes:
            result = {
                "text": node.node.get_content(),
                "score": float(node.score),
                "metadata": node.node.metadata or {},
                "node_id": node.node.node_id
            }
            results.append(result)
        
        return results
    
    def batch_retrieve(self, queries: List[str], **kwargs) -> List[List[Dict[str, Any]]]:
        """
        批量执行检索
        
        Args:
            queries: 查询文本列表
            **kwargs: 额外参数
            
        Returns:
            每个查询对应的检索结果列表
        """
        results = []
        
        for query in queries:
            query_results = self.retrieve_documents(query, **kwargs)
            results.append(query_results)
        
        info(f"批量检索完成，处理了{len(queries)}个查询")
        return results
    
    def hybrid_search(self, query: str, vector_weight: float = 0.7, **kwargs) -> List[Dict[str, Any]]:
        """
        混合搜索（向量搜索 + 关键词搜索）
        注意：此功能需要索引支持混合搜索
        
        Args:
            query: 查询文本
            vector_weight: 向量搜索权重，关键词搜索权重为 1 - vector_weight
            **kwargs: 额外参数
            
        Returns:
            检索结果列表
        """
        try:
            debug(f"执行混合搜索: {query[:50]}..., vector_weight={vector_weight}")
            
            # 检查是否支持混合搜索
            if hasattr(self.retriever, 'hybrid_search'):
                # 如果检索器直接支持混合搜索
                nodes = self.retriever.hybrid_search(
                    query,
                    vector_weight=vector_weight,
                    **kwargs
                )
            else:
                # 否则，执行向量搜索并自行调整
                # 这里简化处理，只执行向量搜索
                debug("当前检索器不直接支持混合搜索，使用向量搜索作为替代")
                nodes = self.retrieve(query, **kwargs)
            
            # 转换为结构化结果
            results = []
            for node in nodes:
                result = {
                    "text": node.node.get_content(),
                    "score": float(node.score),
                    "metadata": node.node.metadata or {},
                    "node_id": node.node.node_id
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            error(f"混合搜索失败: {str(e)}")
            # 失败时回退到普通检索
            return self.retrieve_documents(query, **kwargs)
    
    def update_config(self, **kwargs):
        """
        更新检索器配置
        
        Args:
            **kwargs: 要更新的配置参数
        """
        try:
            # 更新配置参数
            if "similarity_top_k" in kwargs:
                self.similarity_top_k = kwargs["similarity_top_k"]
            if "search_type" in kwargs:
                self.search_type = kwargs["search_type"]
            if "similarity_threshold" in kwargs:
                self.similarity_threshold = kwargs["similarity_threshold"]
            
            # 重新初始化检索器
            self._init_retriever()
            
            info(f"检索器配置已更新: {kwargs}")
            
        except Exception as e:
            error(f"更新检索器配置失败: {str(e)}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取检索器统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = {
                "search_type": self.search_type,
                "similarity_top_k": self.similarity_top_k,
                "similarity_threshold": self.similarity_threshold,
                "index_type": type(self.index).__name__
            }
            
            # 尝试获取索引中的节点数量
            try:
                if hasattr(self.index, 'storage_context') and hasattr(self.index.storage_context, 'vector_store'):
                    stats["vector_store_type"] = type(self.index.storage_context.vector_store).__name__
            except:
                pass
            
            return stats
            
        except Exception as e:
            error(f"获取统计信息失败: {str(e)}")
            return {"error": str(e)}


def create_hybrid_retriever(
    vector_index: VectorStoreIndex,
    keyword_index: Optional[Any] = None,
    vector_weight: float = 0.7,
    similarity_top_k: int = 3,
    **kwargs
) -> DocumentRetriever:
    """
    创建混合检索器
    
    Args:
        vector_index: 向量索引
        keyword_index: 关键词索引（可选）
        vector_weight: 向量搜索权重
        similarity_top_k: 返回的最相似文档数量
        **kwargs: 额外参数
        
    Returns:
        DocumentRetriever实例
    """
    # 目前简化实现，直接返回DocumentRetriever实例
    # 未来可以扩展支持真正的混合索引
    retriever = DocumentRetriever(
        index=vector_index,
        similarity_top_k=similarity_top_k,
        search_type="similarity",
        **kwargs
    )
    
    info("创建了混合检索器（基于向量搜索）")
    return retriever