"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: knowledge_manager.py
@Description:  统一知识管理入口
@Author: NeoPen
@Time: 2026/5/21 15:04
"""

from typing import Optional, Dict, Any, List

from penshot.logger import info, debug
from penshot.neopen.knowledge.llamaIndex.llama_index_knowledge import ScriptKnowledgeBase
from penshot.neopen.knowledge.template.prompt_template_knowledge import PromptTemplateKB


class KnowledgeManager:
    """
    统一知识管理器
    整合提示词模板知识库和剧本知识库
    """

    def __init__(self, embeddings, script_id: str):
        """
        初始化知识管理器

        Args:
            embeddings: 嵌入模型
            script_id: 剧本ID（用于数据隔离）
        """
        self.script_id = script_id
        self.embeddings = embeddings

        # 延迟初始化
        self._prompt_kb = None
        self._script_kb = None

        info(f"知识管理器初始化: script_id={script_id}")

    @property
    def prompt_kb(self):
        """懒加载提示词模板知识库"""
        if self._prompt_kb is None:
            self._prompt_kb = PromptTemplateKB(
                embeddings=self.embeddings,
                script_id=self.script_id
            )
        return self._prompt_kb

    @property
    def script_kb(self):
        """懒加载剧本知识库"""
        if self._script_kb is None:
            self._script_kb = ScriptKnowledgeBase(
                embeddings=self.embeddings,
                script_id=self.script_id
            )
        return self._script_kb

    def add_successful_prompt(self, prompt_text: str, metadata: Dict[str, Any]):
        """添加成功的提示词模板"""
        self.prompt_kb.add_template(prompt_text, metadata)
        debug(f"已添加成功提示词: {metadata.get('fragment_id', 'unknown')}")

    def search_similar_prompts(self, query: str, top_k: int = 3) -> List[Dict]:
        """搜索相似提示词"""
        return self.prompt_kb.search_similar(query, top_k=top_k)

    def add_script(self, parsed_script, script_id: str = None):
        """添加剧本到知识库"""
        return self.script_kb.add_parsed_script(parsed_script, script_id or self.script_id)

    def query_script(self, query_text: str, top_k: int = 5) -> Dict[str, Any]:
        """查询剧本知识库"""
        return self.script_kb.query(
            query_text=query_text,
            script_id=self.script_id,
            similarity_top_k=top_k,
            use_rerank=True
        )

    def query_character(self, character_name: str) -> Optional[Dict]:
        """查询角色信息"""
        return self.script_kb.query_character(character_name, self.script_id)

    def query_scene(self, scene_id: str) -> Optional[Dict]:
        """查询场景信息"""
        return self.script_kb.query_scene(scene_id, self.script_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "script_id": self.script_id,
            "prompt_kb": self.prompt_kb.get_statistics() if self._prompt_kb else {"template_count": 0},
            "script_kb": self.script_kb.get_statistics(self.script_id) if self._script_kb else {}
        }


def create_knowledge_manager(embeddings, script_id: str) -> KnowledgeManager:
    """创建知识管理器实例"""
    return KnowledgeManager(embeddings, script_id)
