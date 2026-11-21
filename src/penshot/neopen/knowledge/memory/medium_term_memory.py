"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: medium_term_memory.py
@Description: 中期记忆 - 基于LangChain的摘要记忆
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/4/1
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import PromptTemplate

from penshot.logger import debug, info, error, warning
from penshot.neopen.knowledge.memory.base_memory_layer import BaseMemoryLayer
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig


class MediumTermMemory(BaseMemoryLayer):
    """中期记忆 - 基于LangChain的摘要记忆，支持文件持久化"""

    backend_type = "medium_term"

    # 默认摘要提示词
    DEFAULT_SUMMARY_PROMPT = PromptTemplate(
        input_variables=["summary", "new_lines"],
        template="""逐步总结对话内容，将之前的总结与新的对话内容融合。

            当前总结:
            {summary}
            
            新的对话内容:
            {new_lines}
            
            请生成更新后的总结（保持简洁，突出重点）:"""
    )

    def __init__(self, llm: BaseLanguageModel, config: MemoryConfig, script_id: str):
        super().__init__(config, script_id)
        self.llm = llm

        # 会话历史存储
        self._session_histories: Dict[str, InMemoryChatMessageHistory] = {}

        # 设置 max_token_limit
        self.max_token_limit = config.medium_term_max_tokens

        # 阶段摘要缓存
        self._stage_summaries: Dict[str, str] = {}

        # 从磁盘恢复的摘要（会话历史为空时回退使用）
        self._restored_summary: str = ""

        # 文件持久化路径
        self.persist_path = None
        if config.term_persist_path:
            self.persist_path = Path(config.term_persist_path) / script_id
            self.persist_path.mkdir(parents=True, exist_ok=True)
            self._load_from_file()  # 启动时加载

        debug(f"初始化中期记忆: script={script_id}, max_tokens={config.medium_term_max_tokens}, "
              f"persist={self.persist_path is not None}")

    def _get_session_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """获取或创建会话历史"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    def _summarize(self, summary: str, new_lines: str) -> str:
        """把新内容并入既有摘要，返回更新后的摘要"""
        # 检查内容长度，如果超过限制则先截断
        if len(new_lines) > self.max_token_limit * 4:
            new_lines = new_lines[:self.max_token_limit * 4]

        # 使用提示词生成更新后的摘要
        prompt = self.config.medium_term_summary_prompt or self.DEFAULT_SUMMARY_PROMPT.template
        formatted_prompt = prompt.format(summary=summary, new_lines=new_lines)

        response = self.llm.invoke(formatted_prompt)
        new_summary = response.content if hasattr(response, 'content') else str(response)

        # 如果摘要过长，进行截断
        if len(new_summary) > self.max_token_limit * 2:
            new_summary = new_summary[:self.max_token_limit * 2] + "..."

        return new_summary

    def add(self, stage_name: str, content: str, metadata: Optional[Dict] = None):
        """添加阶段内容"""
        # 检查内容长度，如果超过限制则先截断
        if len(content) > self.max_token_limit * 4:
            content = content[:self.max_token_limit * 4]

        # 先读取既有摘要，再写入本次历史，否则会读到刚加入的内容
        current_summary = self.get_summary()

        # 按 stage_name 作为 key 同步写入 KV，保证 MemoryManager.get 可按 key 命中
        self._key_values[stage_name] = content

        # 会话历史中最后一条消息即最新摘要
        history = self._get_session_history(f"stage_{stage_name}")
        new_summary = self._summarize(current_summary, content)
        history.add_user_message(content)
        history.add_ai_message(new_summary)

        # 缓存阶段摘要
        if metadata and metadata.get("keep_full"):
            self._stage_summaries[stage_name] = content

        # 持久化到文件
        self._persist()

        debug(f"添加阶段内容: {stage_name}, 长度={len(content)}")

    def get_summary(self) -> str:
        """获取整体摘要"""
        # 从会话历史中获取最新的摘要
        for session_id, history in self._session_histories.items():
            messages = history.messages
            if messages:
                last_message = messages[-1]
                summary = last_message.content if hasattr(last_message, 'content') else str(last_message)
                # 如果摘要过长，进行截断
                if len(summary) > self.max_token_limit * 2:
                    summary = summary[:self.max_token_limit * 2] + "..."
                return summary
        # 新进程尚未写入会话历史时，回退到磁盘恢复的摘要
        return self._restored_summary

    def get_stage_summary(self, stage_name: str) -> Optional[str]:
        """获取特定阶段摘要"""
        return self._stage_summaries.get(stage_name)

    def _clear_backend(self) -> None:
        """清空摘要与会话历史"""
        self._session_histories.clear()
        self._stage_summaries.clear()
        self._restored_summary = ""
        debug("清空中期记忆")

    def _delete_kv_file(self) -> None:
        if self.persist_path:
            self._delete_file(self._summary_file())

    def _summary_file(self) -> Path:
        """中期记忆持久化文件（读写必须使用同一路径）"""
        return self.persist_path / "medium_summary.json"

    def _persist(self):
        """基类持久化钩子：摘要与 KV 写入同一文件"""
        self._persist_to_file()

    def _persist_to_file(self):
        """持久化到文件"""
        if not self.persist_path:
            return

        try:
            summary = self.get_summary()
            data = {
                "script_id": self.script_id,
                "summary": summary,
                "stage_summaries": self._stage_summaries,
                "key_values": self._key_values,
                "updated_at": datetime.now().isoformat(),
                "max_tokens": self.max_token_limit
            }
            with open(self._summary_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            error(f"持久化摘要失败: {e}")

    def _load_from_file(self):
        """从文件加载"""
        if not self.persist_path:
            return

        try:
            summary_file = self._summary_file()
            if not summary_file.exists():
                return

            with open(summary_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 恢复阶段摘要与按 key 的记忆
            self._stage_summaries = data.get("stage_summaries", {})
            key_values = data.get("key_values", {})
            if isinstance(key_values, dict):
                self._key_values = key_values
            self._restored_summary = data.get("summary", "") or ""

            info(f"加载摘要文件: {summary_file}, 阶段数={len(self._stage_summaries)}, "
                 f"KV={len(self._key_values)}")
        except Exception as e:
            warning(f"加载摘要文件失败: {e}")

    def export_summary(self) -> Dict[str, Any]:
        """导出摘要（用于调试或迁移）"""
        return {
            "script_id": self.script_id,
            "summary": self.get_summary(),
            "stage_summaries": self._stage_summaries,
            "stats": self.get_stats()
        }

    def _extra_stats(self) -> Dict[str, Any]:
        summary = self.get_summary()
        return {
            "summary_length": len(summary),
            "max_tokens": self.max_token_limit,
            "stages_count": len(self._stage_summaries),
            "summary_preview": summary[:100] if summary else "",
            "persisted": self.persist_path is not None,
            "persist_path": str(self.persist_path) if self.persist_path else None
        }
