"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: llama_index_router.py
@Description: 知识访问路由器 - 统一LlamaIndex与现有记忆层的访问接口
@Author: NeoPen
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any

from penshot.logger import info, warning, error
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.knowledge.llamaIndex.llama_index_retriever import DocumentRetriever
from penshot.neopen.knowledge.memory.memory_manager import MemoryManager
from penshot.neopen.knowledge.memory.memory_models import MemoryLevel


class KnowledgeSource(Enum):
    """知识来源类型"""
    VECTOR_INDEX = "vector_index"  # LlamaIndex 向量检索
    SEMANTIC_MEMORY = "semantic_memory"  # 现有记忆层
    STRUCTURED = "structured"  # 结构化数据（剧本解析结果）
    HYBRID = "hybrid"  # 混合检索


@dataclass
class KnowledgeQuery:
    """知识查询对象"""
    query_text: str  # 查询文本
    source: KnowledgeSource = KnowledgeSource.HYBRID
    top_k: int = 5  # 返回结果数量
    filter_script_id: Optional[str] = None  # 按剧本ID过滤
    filter_scene_id: Optional[str] = None  # 按场景ID过滤
    similarity_threshold: float = 0.6  # 相似度阈值
    include_metadata: bool = True  # 是否包含元数据


@dataclass
class KnowledgeResult:
    """知识查询结果"""
    results: List[Dict[str, Any]]
    source: KnowledgeSource
    query_time_ms: float
    total_matches: int
    query_text: str


class KnowledgeRouter:
    """
    知识访问路由器
    
    职责：
    1. 统一 LlamaIndex 与现有记忆层的访问接口
    2. 根据查询类型自动选择最优检索策略
    3. 融合多源检索结果
    """

    def __init__(
            self,
            script_knowledge_base: Optional[ScriptKnowledgeBase] = None,
            memory_manager: Optional[MemoryManager] = None,
            default_top_k: int = 5,
            enable_hybrid: bool = True
    ):
        """
        初始化知识路由器
        
        Args:
            script_knowledge_base: LlamaIndex 知识库实例
            memory_manager: 现有记忆管理器实例
            default_top_k: 默认返回结果数量
            enable_hybrid: 是否启用混合检索
        """
        self.script_kb = script_knowledge_base
        self.memory = memory_manager
        self.default_top_k = default_top_k
        self.enable_hybrid = enable_hybrid

        # 检索器缓存
        self._retrievers: Dict[str, DocumentRetriever] = {}

        # 查询统计
        self.query_stats = {
            "total_queries": 0,
            "by_source": {s.value: 0 for s in KnowledgeSource},
            "avg_time_ms": 0.0
        }

        info("知识路由器初始化完成")

    async def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        """
        执行知识查询（自动路由到最优来源）
        
        Args:
            query: 知识查询对象
            
        Returns:
            知识查询结果
        """
        import time
        start_time = time.time()

        self.query_stats["total_queries"] += 1

        try:
            # 根据查询类型选择检索策略
            if query.source == KnowledgeSource.VECTOR_INDEX:
                results = await self._vector_search(query)
            elif query.source == KnowledgeSource.SEMANTIC_MEMORY:
                results = await self._memory_search(query)
            elif query.source == KnowledgeSource.STRUCTURED:
                results = await self._structured_search(query)
            else:  # HYBRID
                results = await self._hybrid_search(query)

            elapsed_ms = (time.time() - start_time) * 1000

            # 更新统计
            self.query_stats["by_source"][query.source.value] += 1
            self.query_stats["avg_time_ms"] = (
                    self.query_stats["avg_time_ms"] * 0.9 + elapsed_ms * 0.1
            )

            return KnowledgeResult(
                results=results,
                source=query.source,
                query_time_ms=elapsed_ms,
                total_matches=len(results),
                query_text=query.query_text
            )

        except Exception as e:
            error(f"知识查询失败: {str(e)}")
            return KnowledgeResult(
                results=[],
                source=query.source,
                query_time_ms=(time.time() - start_time) * 1000,
                total_matches=0,
                query_text=query.query_text
            )

    async def _vector_search(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """向量检索（LlamaIndex）- 修复版"""
        if not self.script_kb:
            warning("向量知识库未初始化")
            return []

        # 确定目标剧本ID
        target_script_id = query.filter_script_id or self.script_kb.get_current_script()
        if not target_script_id:
            warning("未指定剧本ID，无法进行向量检索")
            return []

        try:
            # 创建检索器（如果尚未创建）
            self.script_kb.create_retriever_for_script(
                script_id=target_script_id,
                search_type="similarity",
                similarity_top_k=query.top_k,
                use_rerank=True
            )

            retriever = self.script_kb.get_retriever(target_script_id)
            if not retriever or not hasattr(retriever, 'retrieve'):
                warning(f"检索器未就绪: {target_script_id}")
                return []

            # 执行检索
            nodes = retriever.retrieve(query.query_text)

            # 格式化结果
            formatted_results = []
            for i, node in enumerate(nodes):
                # 获取元数据
                if hasattr(node, 'node'):
                    metadata = dict(node.node.metadata) if node.node.metadata else {}
                    text = node.node.text if hasattr(node.node, 'text') else str(node.node)
                    score = node.score if hasattr(node, 'score') else 0.0
                else:
                    metadata = {}
                    text = str(node)
                    score = 0.0

                # 过滤：确保返回当前剧本的结果
                if metadata.get("script_id") != target_script_id:
                    continue

                # 相似度阈值过滤
                if score < query.similarity_threshold:
                    continue

                formatted_results.append({
                    "content": text,
                    "score": score,
                    "source": "vector_index",
                    "metadata": metadata,
                    "rank": i + 1
                })

            # 按分数排序
            formatted_results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # 限制返回数量
            result_count = min(len(formatted_results), query.top_k)
            info(f"向量检索完成: 共{len(formatted_results)}个结果，返回{result_count}个")

            return formatted_results[:result_count]

        except Exception as e:
            error(f"向量检索失败: {str(e)}")
            return []

    async def _memory_search(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """记忆层检索（现有记忆系统）"""
        if not self.memory:
            warning("记忆管理器未初始化")
            return []

        results = []

        try:
            # 从短期记忆检索
            short_term = self.memory.get(
                query.query_text,
                level=MemoryLevel.SHORT_TERM,
                default=None
            )
            if short_term:
                results.append({
                    "content": str(short_term),
                    "score": 0.9,
                    "source": "short_term_memory",
                    "metadata": {"level": "short_term"}
                })

            # 从中期记忆检索统计信息
            stats = self.memory.get(
                "stats_parse_script",
                level=MemoryLevel.MEDIUM_TERM,
                default={}
            )
            if stats and isinstance(stats, dict):
                results.append({
                    "content": f"历史解析统计: {stats}",
                    "score": 0.7,
                    "source": "medium_term_memory",
                    "metadata": stats
                })

            # 从长期记忆检索常见问题模式
            common_issues = self.memory.get(
                "common_parse_issues",
                level=MemoryLevel.LONG_TERM,
                default=[]
            )
            if common_issues and isinstance(common_issues, list):
                results.append({
                    "content": f"常见问题模式: {len(common_issues)}条",
                    "score": 0.6,
                    "source": "long_term_memory",
                    "metadata": {"issues": common_issues[:3]}
                })

            # 限制返回数量
            return results[:query.top_k]

        except Exception as e:
            error(f"记忆检索失败: {str(e)}")
            return []

    async def _structured_search(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """结构化数据检索（剧本解析结果）"""
        results = []

        try:
            if not self.script_kb:
                return results

            # 尝试按场景编号查询
            if query.filter_scene_id and query.filter_scene_id.isdigit():
                scene = self.script_kb.query_scene(query.filter_scene_id)
                if scene:
                    results.append({
                        "content": f"场景{scene.get('number')}: {scene.get('description', '')}",
                        "score": 1.0,
                        "source": "structured_scene",
                        "metadata": scene
                    })

            # 尝试按角色名称查询
            # 从查询文本中提取可能的角色名（简单实现）
            for char_name in self._extract_character_names(query.query_text):
                character = self.script_kb.query_character(char_name)
                if character:
                    results.append({
                        "content": f"角色{char_name}: {character.get('description', '')}",
                        "score": 0.9,
                        "source": "structured_character",
                        "metadata": character
                    })

            return results[:query.top_k]

        except Exception as e:
            error(f"结构化检索失败: {str(e)}")
            return []

    async def _hybrid_search(self, query: KnowledgeQuery) -> List[Dict[str, Any]]:
        """混合检索 - 融合多源结果并去重排序"""
        # 并行执行多源检索（简化版，实际可用 asyncio.gather）
        vector_results = await self._vector_search(query)
        memory_results = await self._memory_search(query)
        structured_results = await self._structured_search(query)

        # 合并结果
        all_results = vector_results + memory_results + structured_results

        # 按分数排序并去重（基于内容相似度）
        unique_results = {}
        for r in sorted(all_results, key=lambda x: x.get("score", 0), reverse=True):
            # 简单去重：检查内容的前100字符
            content_key = r.get("content", "")[:100]
            if content_key not in unique_results:
                unique_results[content_key] = r

        # 返回 top_k
        return list(unique_results.values())[:query.top_k]

    def _extract_character_names(self, text: str) -> List[str]:
        """从文本中提取角色名（简化实现）"""
        # 这里可以集成 NER 或使用正则表达式
        # 简单实现：假设角色名通常是中文2-4字且出现在特定上下文中
        import re
        # 匹配可能的中文人名（2-4个中文字符）
        chinese_names = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        return list(set(chinese_names))[:5]

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        return {
            "total_queries": self.query_stats["total_queries"],
            "by_source": self.query_stats["by_source"],
            "avg_time_ms": round(self.query_stats["avg_time_ms"], 2),
            "retrievers_cached": len(self._retrievers)
        }


# ========== 工作流集成 ==========

async def enhance_continuity_check_with_knowledge(
        state: WorkflowState,
        knowledge_router: KnowledgeRouter
) -> WorkflowState:
    """
    增强连续性检查 - 使用知识库检索相似场景进行一致性校验
    
    Args:
        state: 工作流状态
        knowledge_router: 知识路由器
        
    Returns:
        增强后的状态
    """
    try:
        if not state.continuity_issues:
            return state

        # 对每个连续性问题的描述进行知识检索
        enhanced_issues = []

        for issue in state.continuity_issues:
            issue_desc = getattr(issue, 'description', str(issue))

            # 检索相似问题的历史解决方案
            query = KnowledgeQuery(
                query_text=f"连续性问题: {issue_desc}",
                source=KnowledgeSource.HYBRID,
                top_k=3,
                similarity_threshold=0.5
            )

            result = await knowledge_router.query(query)

            if result.results:
                # 将检索到的历史解决方案附加到问题对象
                if hasattr(issue, 'historical_solutions'):
                    issue.historical_solutions = result.results

            enhanced_issues.append(issue)
            info(f"连续性检查已增强，检索到{len(result.results) if result.results else 0}条历史解决方案")

        state.continuity_issues = enhanced_issues

    except Exception as e:
        error(f"增强连续性检查失败: {str(e)}")

    return state


async def enhance_prompt_generation_with_knowledge(
        fragment_text: str,
        knowledge_router: KnowledgeRouter
) -> Optional[str]:
    """
    增强提示词生成 - 检索相似片段的成功提示词模板
    
    Args:
        fragment_text: 片段文本描述
        knowledge_router: 知识路由器
        
    Returns:
        优化后的提示词或 None
    """
    try:
        query = KnowledgeQuery(
            query_text=fragment_text,
            source=KnowledgeSource.HYBRID,
            top_k=3,
            similarity_threshold=0.6
        )

        result = await knowledge_router.query(query)

        if result.results:
            # 提取最高分结果的提示词模板
            best_match = result.results[0]
            if "prompt_template" in best_match.get("metadata", {}):
                return best_match["metadata"]["prompt_template"]

            # 或基于相似内容生成建议
            return f"参考相似片段:\n{best_match.get('content', '')[:500]}"

        return None

    except Exception as e:
        error(f"增强提示词生成失败: {str(e)}")
        return None


def enhance_prompt_generation_sync(
        fragment_text: str,
        knowledge_router: KnowledgeRouter
) -> Optional[str]:
    """
    同步版本的提示词增强（供工作流节点调用）

    由于 LangGraph 工作流节点是同步的，需要使用此包装器
    """
    import asyncio

    # 检查是否已在事件循环中运行
    try:
        loop = asyncio.get_running_loop()
        # 如果在事件循环中，使用线程池执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                enhance_prompt_generation_with_knowledge(fragment_text, knowledge_router)
            )
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，直接创建新循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                enhance_prompt_generation_with_knowledge(fragment_text, knowledge_router)
            )
        finally:
            loop.close()


def enhance_continuity_check_sync(
        state: WorkflowState,
        knowledge_router: KnowledgeRouter
):
    """
    同步版本的连续性检查增强（供工作流节点调用）
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 在事件循环中，需要特殊处理
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                enhance_continuity_check_with_knowledge(state, knowledge_router)
            )
            return future.result()
    else:
        # 没有事件循环，直接运行
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    enhance_continuity_check_with_knowledge(state, knowledge_router)
                )
            finally:
                loop.close()
        else:
            return asyncio.run(
                enhance_continuity_check_with_knowledge(state, knowledge_router)
            )


# ========== 工厂函数 ==========

def create_knowledge_router(
        embeddings,
        memory_manager: Optional[MemoryManager] = None,
        auto_load_scripts: bool = True
) -> KnowledgeRouter:
    """
    创建知识路由器实例
    
    Args:
        embeddings: 嵌入模型
        memory_manager: 记忆管理器实例
        auto_load_scripts: 是否自动加载已有剧本
        
    Returns:
        知识路由器实例
    """
    # 创建 LlamaIndex 知识库
    script_kb = ScriptKnowledgeBase(
        embeddings=embeddings,
        chunk_size=512,
        chunk_overlap=20
    )

    # 创建路由器
    router = KnowledgeRouter(
        script_knowledge_base=script_kb,
        memory_manager=memory_manager,
        default_top_k=5,
        enable_hybrid=True
    )

    info("知识路由器创建完成")
    return router
