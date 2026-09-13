"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: workflow_memory.py
@Description: 工作流节点记忆管理，封装所有工作流节点的记忆功能
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/5/4 23:38
"""

from typing import Dict, Any, List, Optional
import json
from datetime import datetime

from penshot.logger import error, debug, info, warning
from penshot.neopen.knowledge.memory.memory_models import MemoryLevel
from penshot.utils.log_utils import print_log_exception


class WorkflowMemory:
    """
    工作流节点记忆管理类

    负责封装所有工作流节点的记忆功能，提供三层记忆存储和恢复接口：
    - 短期记忆：缓存完整的阶段结果（最近5条，TTL 1小时）
    - 中期记忆：持久化存储阶段统计摘要（最多20条）
    - 长期记忆：存储成功模式和可复用的知识向量（最多30条）
    """

    def __init__(self, script_id: str, memory_manager, knowledge_manager):
        """
        初始化工作流记忆管理器

        Args:
            script_id: 脚本ID
            memory_manager: 记忆管理器实例
            knowledge_manager: 知识管理器实例
        """
        self.script_id = script_id
        self.memory_manager = memory_manager
        self.knowledge_manager = knowledge_manager

        # 启动时恢复长期记忆中的常见问题模式
        self._load_common_patterns()

    def after_stage_completion(self, stage: str, result: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        阶段完成后保存记忆 - 优化版

        存储策略：
        - 短期记忆：存储完整的阶段结果（最近5条，TTL 1小时）
        - 中期记忆：存储阶段统计摘要（持久化到磁盘）
        - 长期记忆：存储成功模式和可复用的知识向量

        Args:
            stage: 阶段名称 (如 "parse_script", "segment_shot", "split_video", "convert_prompt")
            result: 阶段执行结果对象
            metadata: 可选的额外元数据
        """
        if not self.memory_manager:
            warning("记忆管理器未初始化，跳过记忆存储")
            return

        timestamp = datetime.now().isoformat()
        stage_key = stage.lower().replace("_node", "").replace("_", "_")

        info(f"开始保存阶段记忆: {stage_key}")

        try:
            # 1. 提取结果统计信息
            stats = self._extract_stage_stats(stage_key, result)

            # 合并外部元数据
            if metadata:
                stats.update(metadata)

            stats["timestamp"] = timestamp
            stats["stage_completed_at"] = timestamp

            # 2. 短期记忆缓存（完整结果）
            self.store_short_term_memory(stage_key, result, stats, timestamp)

            # 3. 中期记忆持久化（统计摘要）
            self.store_medium_term_memory(stage_key, stats, timestamp)

            # 4. 长期记忆知识存储（成功模式）
            self.store_long_term_memory(stage_key, result, stats, timestamp)

            info(f"阶段记忆保存完成: {stage_key}, 统计摘要: {json.dumps(stats, ensure_ascii=False, default=str)[:200]}")

        except Exception as e:
            error(f"保存阶段记忆失败: {stage_key}, 错误: {str(e)}")
            print_log_exception()

    def restore_context_for_stage(self, stage_key: str) -> Dict[str, Any]:
        """
        恢复指定阶段的完整记忆上下文

        Args:
            stage_key: 阶段标识 (parse_script, segment_shot, split_video, convert_prompt)

        Returns:
            包含短期、中期、长期记忆的上下文字典
        """
        context = {
            "recent_stats": self.get_memory_dict(f"stats_{stage_key}", level=MemoryLevel.MEDIUM_TERM, default={}),
            "recent_issues": self.get_memory_list(f"issues_{stage_key}", level=MemoryLevel.SHORT_TERM, default=[]),
            "common_patterns": self.get_memory_list(f"common_{stage_key}_patterns", level=MemoryLevel.LONG_TERM, default=[]),
            "successful_patterns": self.get_memory_list(f"successful_{stage_key}_patterns", level=MemoryLevel.LONG_TERM, default=[]),
            "latest_result": self.memory_manager.get(f"stage_{stage_key}_latest", level=MemoryLevel.SHORT_TERM, default=None),
            "has_memory": False
        }

        # 检查是否有任何有效记忆
        has_any_memory = (
            context["recent_stats"] or
            context["recent_issues"] or
            context["common_patterns"] or
            context["successful_patterns"] or
            context["latest_result"]
        )

        if has_any_memory:
            context["has_memory"] = True
            info(f"恢复阶段记忆: {stage_key}, "
                 f"统计={bool(context['recent_stats'])}, "
                 f"问题={len(context['recent_issues'])}, "
                 f"模式={len(context['common_patterns'])}, "
                 f"成功模式={len(context['successful_patterns'])}")

        return context

    def get_memory_dict(self, key: str, level: MemoryLevel, default: Optional[Dict] = None) -> Dict:
        """
        从记忆获取字典类型数据（自动反序列化）

        Args:
            key: 记忆键
            level: 记忆级别
            default: 默认值

        Returns:
            字典类型数据
        """
        if default is None:
            default = {}

        value = self.memory_manager.get(key, level=level, default=default)

        # 如果是字符串，尝试解析为 JSON
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return default

        # 确保返回字典
        if not isinstance(value, dict):
            return default

        return value

    def get_memory_list(self, key: str, level: MemoryLevel, default: Optional[List] = None) -> List:
        """
        从记忆获取列表类型数据（自动反序列化）

        Args:
            key: 记忆键
            level: 记忆级别
            default: 默认值

        Returns:
            列表类型数据
        """
        if default is None:
            default = []

        value = self.memory_manager.get(key, level=level, default=default)

        # 如果是字符串，尝试解析为 JSON
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return default

        # 确保返回列表
        if not isinstance(value, list):
            return [value] if value else default

        return value

    def _load_common_patterns(self) -> None:
        """加载常见问题模式到缓存（全局知识，不依赖任务）"""
        if not self.memory_manager:
            return

        # 获取长期记忆中的常见问题
        common_issues = self.get_memory_list("common_parse_issues", level=MemoryLevel.LONG_TERM, default=[])
        if common_issues:
            info(f"已加载 {len(common_issues)} 条常见问题模式")

        # 获取修复成功模式
        repair_patterns = self.get_memory_list("repair_success_patterns", level=MemoryLevel.LONG_TERM, default=[])
        if repair_patterns:
            info(f"已加载 {len(repair_patterns)} 条修复成功模式")

        # 获取成功提示词模式
        successful_prompts = self.get_memory_list("successful_prompt_patterns", level=MemoryLevel.LONG_TERM, default=[])
        if successful_prompts:
            info(f"已加载 {len(successful_prompts)} 条成功提示词模式")

    def _extract_stage_stats(self, stage_key: str, result: Any) -> Dict[str, Any]:
        """
        从阶段结果中提取统计信息

        Args:
            stage_key: 阶段标识
            result: 阶段结果对象

        Returns:
            统计信息字典
        """
        stats = {
            "stage": stage_key,
            "has_result": result is not None,
            "success": True
        }

        if result is None:
            return stats

        try:
            # 根据阶段类型提取不同的统计信息
            if stage_key == "parse_script":
                if hasattr(result, 'stats'):
                    stats.update({
                        "total_elements": result.stats.get("total_elements", 0),
                        "total_duration": result.stats.get("total_duration", 0),
                        "dialogue_count": result.stats.get("dialogue_count", 0),
                        "action_count": result.stats.get("action_count", 0),
                        "completeness_score": result.stats.get("completeness_score", 0),
                        "parsing_confidence": result.stats.get("parsing_confidence", {}),
                        "parse_attempts": result.stats.get("parse_attempts", 1)
                    })
                if hasattr(result, 'scenes'):
                    stats["scene_count"] = len(result.scenes)
                if hasattr(result, 'characters'):
                    stats["character_count"] = len(result.characters)

            elif stage_key == "segment_shot":
                if hasattr(result, 'stats'):
                    stats.update({
                        "shot_count": result.stats.get("shot_count", 0),
                        "total_duration": result.stats.get("total_duration", 0),
                        "avg_shot_duration": result.stats.get("avg_shot_duration", 0),
                        "close_up_count": result.stats.get("close_up_count", 0),
                        "wide_shot_count": result.stats.get("wide_shot_count", 0),
                        "medium_shot_count": result.stats.get("medium_shot_count", 0)
                    })
                if hasattr(result, 'shots'):
                    stats["shots_generated"] = len(result.shots)

            elif stage_key == "split_video":
                if hasattr(result, 'stats'):
                    stats.update({
                        "fragment_count": result.stats.get("fragment_count", 0),
                        "total_duration": result.stats.get("total_duration", 0),
                        "avg_duration": result.stats.get("avg_duration", 0),
                        "fragments_under_5s": result.stats.get("fragments_under_5s", 0),
                        "fragments_split": result.stats.get("fragments_split", 0),
                        "split_ratio": result.stats.get("split_ratio", 0)
                    })
                if hasattr(result, 'fragments'):
                    stats["fragments_generated"] = len(result.fragments)
                if hasattr(result, 'metadata'):
                    stats["split_method"] = result.metadata.get("split_method", "unknown")
                    stats["ai_split_count"] = result.metadata.get("ai_split_count", 0)
                    stats["rule_split_count"] = result.metadata.get("rule_split_count", 0)

            elif stage_key == "convert_prompt":
                if hasattr(result, 'fragments'):
                    prompts = result.fragments
                    stats["prompt_count"] = len(prompts)
                    stats["audio_prompt_count"] = sum(1 for p in prompts if hasattr(p, 'audio') and p.audio)

                    if prompts:
                        prompt_lengths = [len(p.prompt) if hasattr(p, 'prompt') else 0 for p in prompts]
                        stats["avg_prompt_length"] = sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0
                        stats["min_prompt_length"] = min(prompt_lengths) if prompt_lengths else 0
                        stats["max_prompt_length"] = max(prompt_lengths) if prompt_lengths else 0

                        # 统计风格分布
                        style_counts = {}
                        for p in prompts:
                            if hasattr(p, 'style') and p.style:
                                style_counts[p.style] = style_counts.get(p.style, 0) + 1
                        if style_counts:
                            stats["style_distribution"] = style_counts

                if hasattr(result, 'project_info'):
                    stats["total_duration"] = result.project_info.get("total_duration", 0)

            else:
                # 通用统计提取
                self._extract_generic_stats(result, stats)

        except Exception as e:
            warning(f"提取阶段统计信息失败: {stage_key}, {e}")

        return stats

    def _extract_generic_stats(self, result: Any, stats: Dict[str, Any]) -> None:
        """
        从结果中提取通用统计信息

        Args:
            result: 阶段结果对象
            stats: 统计信息字典（会被修改）
        """
        if hasattr(result, '__dict__'):
            generic_attrs = ['duration', 'count', 'total', 'size', 'length']
            specific_attrs = ['duration', 'count', 'total_elements', 'fragment_count', 'shot_count']

            for attr in specific_attrs:
                if hasattr(result, attr):
                    stats[attr] = getattr(result, attr)
                elif isinstance(result, dict) and attr in result:
                    stats[attr] = result[attr]

    def store_short_term_memory(self, stage_key: str, result: Any, stats: Dict, timestamp: str) -> None:
        """
        存储短期记忆 - 缓存最近的阶段结果

        短期记忆特点：
        - Redis优先，内存次之
        - 自动过期（TTL 1小时）
        - 存储完整的阶段结果
        - 用于快速恢复和上下文参考
        """
        try:
            # 序列化结果对象
            serialized_result = None
            if result is not None:
                if hasattr(result, 'model_dump'):
                    serialized_result = result.model_dump()
                elif hasattr(result, 'dict'):
                    serialized_result = result.dict()
                elif isinstance(result, dict):
                    serialized_result = result
                else:
                    serialized_result = str(result)

            # 构建短期记忆条目
            memory_entry = {
                "stage": stage_key,
                "timestamp": timestamp,
                "stats": stats,
                "result": serialized_result,
                "has_result": result is not None,
                "metadata": {
                    "version": "mvp_1.0",
                    "source": "workflow_nodes"
                }
            }

            # 存储到短期记忆（自动覆盖同一阶段的最新结果）
            self.memory_manager.add(
                input_text=f"stage_{stage_key}_latest",
                output_text=memory_entry,
                level=MemoryLevel.SHORT_TERM,
                metadata={
                    "_serialized": True,
                    "stage": stage_key,
                    "timestamp": timestamp,
                    "type": "stage_result"
                }
            )

            # 同时存储到历史列表（保留最近5条）
            history_key = f"stage_{stage_key}_history"
            history = self.memory_manager.get(history_key, level=MemoryLevel.SHORT_TERM, default=[])

            if not isinstance(history, list):
                history = []

            # 添加新条目
            history.append({
                "timestamp": timestamp,
                "stats": stats
            })

            # 只保留最近5条
            if len(history) > 5:
                history = history[-5:]

            self.memory_manager.add(
                input_text=history_key,
                output_text=history,
                level=MemoryLevel.SHORT_TERM,
                metadata={"_serialized": True, "stage": stage_key, "type": "stage_history"}
            )

            debug(f"短期记忆已存储: {stage_key}")

        except Exception as e:
            warning(f"存储短期记忆失败: {stage_key}, {e}")

    def store_medium_term_memory(self, stage_key: str, stats: Dict, timestamp: str) -> None:
        """
        存储中期记忆 - 阶段统计摘要持久化

        中期记忆特点：
        - 持久化到磁盘（JSON文件）
        - 存储各阶段的统计摘要
        - 用于跨阶段分析和趋势追踪
        - 支持多轮修复的统计对比
        """
        try:
            # 获取该阶段的现有统计历史
            stats_key = f"stats_{stage_key}"
            existing_stats = self.memory_manager.get(stats_key, level=MemoryLevel.MEDIUM_TERM, default={})

            if not isinstance(existing_stats, dict):
                existing_stats = {}

            # 构建历史统计列表
            history = existing_stats.get("history", [])

            # 添加当前统计
            history.append({
                "timestamp": timestamp,
                "stats": stats.copy()
            })

            # 只保留最近20条记录
            if len(history) > 20:
                history = history[-20:]

            # 计算汇总统计
            summary = self._calculate_medium_term_summary(history)

            # 更新中期记忆
            medium_term_data = {
                "stage": stage_key,
                "last_updated": timestamp,
                "total_attempts": len(history),
                "summary": summary,
                "history": history,
                "latest_stats": stats
            }

            self.memory_manager.add(
                input_text=stats_key,
                output_text=medium_term_data,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={
                    "_serialized": True,
                    "stage": stage_key,
                    "type": "stage_statistics",
                    "version": "mvp_1.0"
                }
            )

            # 同时更新阶段完成计数
            completion_key = f"stage_{stage_key}_completions"
            completions = self.memory_manager.get(completion_key, level=MemoryLevel.MEDIUM_TERM, default=[])

            if not isinstance(completions, list):
                completions = []

            completions.append({
                "timestamp": timestamp,
                "success": stats.get("success", True),
                "stats_summary": {k: v for k, v in stats.items() if isinstance(v, (int, float, str, bool))}
            })

            if len(completions) > 50:
                completions = completions[-50:]

            self.memory_manager.add(
                input_text=completion_key,
                output_text=completions,
                level=MemoryLevel.MEDIUM_TERM,
                metadata={"_serialized": True, "type": "completion_history"}
            )

            debug(f"中期记忆已存储: {stage_key}, 总尝试次数={len(history)}")

        except Exception as e:
            warning(f"存储中期记忆失败: {stage_key}, {e}")

    def _calculate_medium_term_summary(self, history: List[Dict]) -> Dict[str, Any]:
        """
        计算中期记忆的汇总统计

        Args:
            history: 历史统计记录列表

        Returns:
            汇总统计字典
        """
        if not history:
            return {}

        summary = {}

        # 收集所有统计中的数值字段
        numeric_fields = {}

        for record in history:
            stats = record.get("stats", {})
            for key, value in stats.items():
                if isinstance(value, (int, float)):
                    if key not in numeric_fields:
                        numeric_fields[key] = []
                    numeric_fields[key].append(value)

        # 计算均值、最小、最大
        for field, values in numeric_fields.items():
            if values:
                summary[field] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values)
                }

        # 添加趋势判断
        if "completeness_score" in numeric_fields:
            scores = numeric_fields["completeness_score"]
            if len(scores) >= 2:
                if scores[-1] > scores[0]:
                    summary["trend"] = "improving"
                elif scores[-1] < scores[0]:
                    summary["trend"] = "declining"
                else:
                    summary["trend"] = "stable"

        return summary

    def store_long_term_memory(self, stage_key: str, result: Any, stats: Dict, timestamp: str) -> None:
        """
        存储长期记忆 - 成功模式和可复用知识

        长期记忆特点：
        - 向量存储索引
        - 存储成功案例用于未来检索
        - 语义相似度搜索
        - 跨项目知识复用
        """
        try:
            # 判断是否为成功案例（适合长期存储）
            is_success = self._is_successful_case(stage_key, stats)

            if not is_success:
                debug(f"跳过长期记忆存储（非成功案例）: {stage_key}")
                return

            # 提取关键信息用于向量化
            content = self._extract_long_term_content(stage_key, result, stats)

            if not content:
                debug(f"无可提取的长期记忆内容: {stage_key}")
                return

            # 构建长期记忆条目
            memory_item = {
                "stage": stage_key,
                "timestamp": timestamp,
                "content": content,
                "stats": stats,
                "metadata": {
                    "version": "mvp_1.0",
                    "source": "workflow_nodes",
                    "success": True
                }
            }

            # 存储到长期记忆（用于语义检索）
            self.memory_manager.add(
                input_text=f"successful_{stage_key}_pattern",
                output_text=memory_item,
                level=MemoryLevel.LONG_TERM,
                metadata={
                    "_serialized": True,
                    "stage": stage_key,
                    "type": "successful_pattern",
                    "content_hash": hash(content[:200]) if content else None
                }
            )

            # 更新成功模式列表（用于历史上下文）
            patterns_key = f"successful_{stage_key}_patterns"
            patterns = self.memory_manager.get(patterns_key, level=MemoryLevel.LONG_TERM, default=[])

            if not isinstance(patterns, list):
                patterns = []

            # 添加新模式
            pattern_entry = {
                "timestamp": timestamp,
                "stats": {k: v for k, v in stats.items() if isinstance(v, (int, float, str, bool))},
                "content_preview": content[:200] if content else "",
                "content_hash": hash(content[:200]) if content else None
            }

            patterns.append(pattern_entry)

            # 只保留最近30条成功模式
            if len(patterns) > 30:
                patterns = patterns[-30:]

            self.memory_manager.add(
                input_text=patterns_key,
                output_text=patterns,
                level=MemoryLevel.LONG_TERM,
                metadata={"_serialized": True, "stage": stage_key, "type": "successful_patterns"}
            )

            # 更新知识管理器的成功提示词记录
            if stage_key == "convert_prompt" and self.knowledge_manager:
                self._update_knowledge_manager_with_success(result, stats)

            debug(f"长期记忆已存储: {stage_key}, 内容长度={len(content)}")

        except Exception as e:
            warning(f"存储长期记忆失败: {stage_key}, {e}")

    def _is_successful_case(self, stage_key: str, stats: Dict) -> bool:
        """
        判断是否为成功案例（适合长期存储）

        Args:
            stage_key: 阶段标识
            stats: 统计信息

        Returns:
            是否为成功案例
        """
        # 基础条件：必须成功
        if not stats.get("success", True):
            return False

        # 根据阶段判断质量阈值
        if stage_key == "parse_script":
            completeness = stats.get("completeness_score", 0)
            return completeness >= 0.8

        elif stage_key == "segment_shot":
            shot_count = stats.get("shot_count", 0)
            total_duration = stats.get("total_duration", 0)
            return shot_count >= 1 and total_duration > 0

        elif stage_key == "split_video":
            fragment_count = stats.get("fragment_count", 0)
            return fragment_count >= 1

        elif stage_key == "convert_prompt":
            prompt_count = stats.get("prompt_count", 0)
            audio_count = stats.get("audio_prompt_count", 0)
            # 成功条件：有提示词，且音频覆盖率合理
            return prompt_count >= 1 and (audio_count >= prompt_count * 0.5)

        return True

    def _extract_long_term_content(self, stage_key: str, result: Any, stats: Dict) -> str:
        """
        提取用于长期记忆存储的内容

        Args:
            stage_key: 阶段标识
            result: 阶段结果
            stats: 统计信息

        Returns:
            可存储的内容文本
        """
        content_parts = []

        try:
            # 添加阶段标识和统计信息
            content_parts.append(f"[{stage_key}] 执行完成")
            content_parts.append(f"统计: {stats}")

            # 根据阶段提取具体内容
            if stage_key == "parse_script":
                if hasattr(result, 'scenes'):
                    scene_descs = [f"场景{s.id}: {s.description[:100]}" for s in result.scenes[:5]]
                    content_parts.append(f"场景: {scene_descs}")
                if hasattr(result, 'characters'):
                    char_names = [c.name for c in result.characters]
                    content_parts.append(f"角色: {', '.join(char_names)}")

            elif stage_key == "segment_shot":
                if hasattr(result, 'shots'):
                    shot_summaries = [f"镜头{s.id}: {s.shot_type.value if hasattr(s.shot_type, 'value') else s.shot_type}, {s.duration}s"
                                      for s in result.shots[:10]]
                    content_parts.append(f"镜头: {shot_summaries}")

            elif stage_key == "split_video":
                if hasattr(result, 'fragments'):
                    frag_summaries = [f"片段{f.id}: {f.duration}s" for f in result.fragments[:10]]
                    content_parts.append(f"片段: {frag_summaries}")

            elif stage_key == "convert_prompt":
                if hasattr(result, 'fragments'):
                    prompt_summaries = []
                    for f in result.fragments[:5]:
                        style = getattr(f, 'style', 'unknown')
                        prompt_len = len(getattr(f, 'prompt', ''))
                        prompt_summaries.append(f"片段{f.fragment_id}: 风格={style}, 长度={prompt_len}")
                    content_parts.append(f"提示词: {prompt_summaries}")

            # 合并所有部分
            content = "\n".join(content_parts)

            # 限制长度（避免超出向量模型限制）
            if len(content) > 2000:
                content = content[:1997] + "..."

            return content

        except Exception as e:
            warning(f"提取长期记忆内容失败: {stage_key}, {e}")
            return f"[{stage_key}] 执行完成，统计: {stats}"

    def _update_knowledge_manager_with_success(self, result: Any, stats: Dict) -> None:
        """
        更新知识管理器中的成功提示词

        Args:
            result: 提示词转换结果
            stats: 统计信息
        """
        try:
            if not hasattr(result, 'fragments'):
                return

            for fragment in result.fragments:
                fragment_id = getattr(fragment, 'fragment_id', 'unknown')
                prompt_text = getattr(fragment, 'prompt', '')
                style = getattr(fragment, 'style', 'cinematic')
                duration = getattr(fragment, 'duration', 0)

                if prompt_text and len(prompt_text) > 20:
                    self.knowledge_manager.save_successful_prompt(
                        fragment_id=fragment_id,
                        script_id=self.script_id,
                        prompt_text=prompt_text,
                        quality_score=stats.get("completeness_score", 85.0),
                        additional_metadata={
                            "style": style,
                            "duration": duration,
                            "stage": "convert_prompt"
                        }
                    )

            debug(f"已更新知识管理器: {len(result.fragments)} 个成功提示词")

        except Exception as e:
            warning(f"更新知识管理器失败: {e}")