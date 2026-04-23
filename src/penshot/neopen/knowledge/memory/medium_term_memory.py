"""
@FileName: medium_term_memory.py
@Description: 中期记忆 - 基于LangChain的摘要记忆
@Author: HiPeng
@Time: 2026/4/1
"""
import json
from pathlib import Path
from typing import Optional, Any, Dict
from datetime import datetime

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.language_models import BaseLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from penshot.logger import debug, info, error
from penshot.neopen.knowledge.memory.memory_models import MemoryConfig
from penshot.neopen.tools.result_storage_tool import create_result_storage


class MediumTermMemory:
    """中期记忆 - 基于LangChain的摘要记忆，支持文件持久化"""

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

    def __init__(self, llm: BaseLLM, config: MemoryConfig, script_id: str):
        self.llm = llm
        self.config = config
        self.script_id = script_id

        # 会话历史存储
        self._session_histories: Dict[str, ChatMessageHistory] = {}

        # 设置 max_token_limit
        self.max_token_limit = config.medium_term_max_tokens

        # 阶段摘要缓存
        self._stage_summaries: Dict[str, str] = {}

        # 文件持久化路径
        self.persist_path = None
        if config.medium_term_persist_path:
            self.persist_path = Path(config.medium_term_persist_path) / script_id
            self.persist_path.mkdir(parents=True, exist_ok=True)
            self._load_from_file()  # 启动时加载
            self.storage = create_result_storage(base_output_dir=config.medium_term_persist_path)

        # 创建带记忆的链
        self.memory = self._create_memory_chain()

        debug(f"初始化中期记忆: script={script_id}, max_tokens={config.medium_term_max_tokens}, "
              f"persist={self.persist_path is not None}")

    def _get_session_history(self, session_id: str) -> ChatMessageHistory:
        """获取或创建会话历史"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = ChatMessageHistory()
        return self._session_histories[session_id]

    def _create_summary_chain(self):
        """创建摘要链"""
        def summarize(input_dict):
            """生成摘要"""
            summary = input_dict.get("summary", "")
            new_lines = input_dict.get("new_lines", "")

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

        return RunnableLambda(summarize)

    def _create_memory_chain(self):
        """创建带记忆的链"""
        summary_chain = self._create_summary_chain()

        return RunnableWithMessageHistory(
            summary_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history"
        )

    def add(self, stage_name: str, content: str, metadata: Optional[Dict] = None):
        """添加阶段内容"""
        # 检查内容长度，如果超过限制则先截断
        if len(content) > self.max_token_limit * 4:
            content = content[:self.max_token_limit * 4]

        # 获取当前摘要
        current_summary = self.get_summary()

        # 保存到摘要链
        session_id = f"stage_{stage_name}"
        self.memory.invoke(
            {"summary": current_summary, "new_lines": content, "input": content},
            config={"configurable": {"session_id": session_id}}
        )

        # 缓存阶段摘要
        if metadata and metadata.get("keep_full"):
            self._stage_summaries[stage_name] = content

        # 持久化到文件
        self._persist_to_file()

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
        return ""

    def get_stage_summary(self, stage_name: str) -> Optional[str]:
        """获取特定阶段摘要"""
        return self._stage_summaries.get(stage_name)

    def clear(self):
        """清空摘要"""
        self._session_histories.clear()
        self._stage_summaries.clear()

        # 重新创建记忆链
        self.memory = self._create_memory_chain()

        # 删除持久化文件
        if self.persist_path:
            summary_file = self.persist_path / "summary.json"
            if summary_file.exists():
                summary_file.unlink()

        debug("清空中期记忆")

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
                "updated_at": datetime.now().isoformat(),
                "max_tokens": self.max_token_limit
            }
            self.storage.save_json_result(self.script_id, "", data, f"summary_{datetime.now().strftime('%Y%m%d%H')}.json")

        except Exception as e:
            error(f"持久化摘要失败: {e}")

    def _load_from_file(self):
        """从文件加载"""
        if not self.persist_path:
            return

        try:
            summary_file = self.persist_path / "summary.json"
            if not summary_file.exists():
                return

            with open(summary_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 恢复阶段摘要
            self._stage_summaries = data.get("stage_summaries", {})

            info(f"加载摘要文件: {summary_file}, 阶段数={len(self._stage_summaries)}")
        except Exception as e:
            error(f"加载摘要文件失败: {e}")

    def export_summary(self) -> Dict[str, Any]:
        """导出摘要（用于调试或迁移）"""
        return {
            "script_id": self.script_id,
            "summary": self.get_summary(),
            "stage_summaries": self._stage_summaries,
            "stats": self.get_stats()
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        summary = self.get_summary()
        return {
            "type": "medium_term",
            "summary_length": len(summary),
            "max_tokens": self.max_token_limit,
            "stages_count": len(self._stage_summaries),
            "summary_preview": summary[:100] if summary else "",
            "persisted": self.persist_path is not None,
            "persist_path": str(self.persist_path) if self.persist_path else None
        }