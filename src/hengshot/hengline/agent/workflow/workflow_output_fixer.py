"""
@FileName: workflow_output_fixer.py
@Description: 修复workflow最终输出中的片段序列问题
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/2/9
"""
import time
from typing import Dict, Any, Optional, List

from hengshot.hengline.agent.video_splitter.video_splitter_models import FragmentSequence
from hengshot.hengline.agent.workflow.workflow_states import WorkflowState
from hengshot.logger import info, warning, error, debug


class WorkflowOutputFixer:
    """修复workflow输出中的片段序列问题"""

    def __init__(self, is_debug: bool = False):
        self.fix_history = []
        # 为True时，返回各个阶段完整的数据处理结果
        self.is_debug = is_debug

    async def enhanced_workflow_invoke(self, workflow, initial_state: WorkflowState) -> Dict[str, Any]:
        """
        增强的workflow调用，确保返回正确的分割片段

        Args:
            workflow: LangGraph workflow对象
            initial_state: 初始工作流状态

        Returns:
            修复后的最终结果
        """
        debug("开始增强的workflow调用（修复片段序列）")

        try:
            # 1. 执行原始workflow（支持异步）
            debug(f"执行原始workflow，任务ID: {initial_state.task_id}")

            # 注意：这里需要await workflow.ainvoke
            final_state = await workflow.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": f"process_{id(initial_state)}"}}
            )

            # 2. 分析并修复输出
            debug("分析workflow输出，寻找正确的片段序列...")
            fixed_output = self._analyze_and_fix_output(final_state, initial_state)

            # 3. 记录修复历史
            self._record_fix_history(initial_state.task_id, fixed_output)

            info(f"workflow输出修复完成，任务ID: {initial_state.task_id}")
            return fixed_output

        except Exception as e:
            error(f"增强workflow调用失败: {str(e)}")
            import traceback
            traceback.print_exc()

            # 返回错误结果
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "task_id": getattr(initial_state, 'task_id', 'unknown'),
                "workflow_status": "exception"
            }

    def _analyze_and_fix_output(self, final_state: Any, initial_state: WorkflowState) -> Dict[str, Any]:
        """
        分析并修复workflow输出

        关键逻辑：
        1. 查找正确的fragment_sequence（来自fragment_for_ai_node）
        2. 替换最终输出中的错误片段数据
        3. 保持其他数据完整性
        """
        try:
            # 转换为字典以便处理
            if isinstance(final_state, dict):
                state_dict = final_state
            elif hasattr(final_state, 'dict'):
                state_dict = final_state.dict()
            elif hasattr(final_state, '__dict__'):
                state_dict = final_state.__dict__
            else:
                error(f"无法识别的final_state类型: {type(final_state)}")
                return self._build_fallback_result(initial_state)

            debug(f"分析状态字典，键: {list(state_dict.keys())}")

            # 查找正确的fragment_sequence
            correct_fragment_sequence = self._find_correct_fragment_sequence(state_dict)

            if not correct_fragment_sequence:
                warning("未找到正确的fragment_sequence，尝试深度搜索...")
                correct_fragment_sequence = self._deep_search_fragment_sequence(state_dict)

            if correct_fragment_sequence:
                info(f"找到正确的片段序列: {len(correct_fragment_sequence.fragments)}个片段")

                # 修复最终输出
                fixed_result = self._fix_final_result(state_dict, correct_fragment_sequence, initial_state)
                return fixed_result
            else:
                warning("未找到任何正确的片段序列，使用原始输出")
                return self._convert_state_to_result(state_dict, initial_state)

        except Exception as e:
            error(f"分析修复输出时出错: {str(e)}")
            return self._build_fallback_result(initial_state)

    def _find_correct_fragment_sequence(self, state_dict: Dict[str, Any]) -> Optional[FragmentSequence]:
        """
        查找正确的fragment_sequence

        关键：查找来自fragment_for_ai_node的片段数据
        """
        try:
            # 尝试从多个可能的键中查找
            search_keys = [
                # 直接键名
                'fragment_sequence',
                'video_splitter_output',
                'splitter_output',
                'fragments_output',

                # 节点输出键名（可能带前缀）
                'fragment_for_ai_node_output',
                'fragment_for_ai_result',
                'split_video_result',

                # 中间状态键名
                'current_fragments',
                'generated_fragments',
                'ai_fragments'
            ]

            for key in search_keys:
                if key in state_dict:
                    candidate = state_dict[key]
                    debug(f"检查键 '{key}': {type(candidate)}")

                    if self._is_valid_fragment_sequence(candidate):
                        fragment_sequence = self._convert_to_fragment_sequence(candidate)
                        if fragment_sequence:
                            info(f"从键 '{key}' 找到有效的片段序列")
                            return fragment_sequence

            # 检查workflow状态中的其他数据
            if 'intermediate_results' in state_dict:
                intermediate = state_dict['intermediate_results']
                if isinstance(intermediate, dict):
                    for key, value in intermediate.items():
                        if 'fragment' in key.lower() or 'split' in key.lower():
                            if self._is_valid_fragment_sequence(value):
                                fragment_sequence = self._convert_to_fragment_sequence(value)
                                if fragment_sequence:
                                    info(f"从intermediate_results的'{key}'找到片段序列")
                                    return fragment_sequence

            return None

        except Exception as e:
            error(f"查找片段序列时出错: {str(e)}")
            return None

    def _deep_search_fragment_sequence(self, state_dict: Dict[str, Any]) -> Optional[FragmentSequence]:
        """深度搜索片段序列数据"""
        try:
            visited = set()

            def deep_search(obj, path=""):
                obj_id = id(obj)
                if obj_id in visited:
                    return None
                visited.add(obj_id)

                if isinstance(obj, dict):
                    # 检查当前字典
                    for key, value in obj.items():
                        if 'fragment' in key.lower() or 'split' in key.lower():
                            if self._is_valid_fragment_sequence(value):
                                fragment_sequence = self._convert_to_fragment_sequence(value)
                                if fragment_sequence:
                                    debug(f"深度搜索在路径 '{path}.{key}' 找到片段序列")
                                    return fragment_sequence

                    # 递归搜索子字典
                    for key, value in obj.items():
                        result = deep_search(value, f"{path}.{key}")
                        if result:
                            return result

                elif isinstance(obj, list):
                    # 搜索列表中的字典
                    for i, item in enumerate(obj):
                        result = deep_search(item, f"{path}[{i}]")
                        if result:
                            return result

                return None

            return deep_search(state_dict)

        except Exception as e:
            error(f"深度搜索时出错: {str(e)}")
            return None

    def _is_valid_fragment_sequence(self, candidate: Any) -> bool:
        """检查是否是有效的FragmentSequence"""
        try:
            # 如果是FragmentSequence对象
            if isinstance(candidate, FragmentSequence):
                return True

            # 如果是字典格式
            if isinstance(candidate, dict):
                # 检查是否有fragments字段
                if 'fragments' in candidate:
                    fragments = candidate['fragments']
                    if isinstance(fragments, list) and len(fragments) > 0:
                        # 检查片段结构
                        first_fragment = fragments[0]
                        if isinstance(first_fragment, dict):
                            # 检查必要字段
                            required_fields = ['id', 'shot_id', 'duration']
                            return all(field in first_fragment for field in required_fields)

            return False

        except Exception as e:
            debug(f"检查有效性时出错: {str(e)}")
            return False

    def _convert_to_fragment_sequence(self, candidate: Any) -> Optional[FragmentSequence]:
        """转换为FragmentSequence对象"""
        try:
            if isinstance(candidate, FragmentSequence):
                return candidate

            if isinstance(candidate, dict):
                # 从字典创建FragmentSequence
                fragments = candidate.get('fragments', [])
                metadata = candidate.get('metadata', {})
                source_info = candidate.get('source_info', {})
                stats = candidate.get('stats', {})

                # 确保metadata中有正确的信息
                if 'total_fragments' not in metadata:
                    metadata['total_fragments'] = len(fragments)
                if 'generated_at' not in metadata:
                    metadata['generated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
                if 'cutter_type' not in metadata:
                    metadata['cutter_type'] = 'LLMVideoSplitter_Fixed'

                return FragmentSequence(
                    fragments=fragments,
                    metadata=metadata,
                    source_info=source_info,
                    stats=stats
                )

            return None

        except Exception as e:
            error(f"转换FragmentSequence时出错: {str(e)}")
            return None

    def _fix_final_result(self, state_dict: Dict[str, Any],
                          correct_fragment_sequence: FragmentSequence,
                          initial_state: WorkflowState) -> Dict[str, Any]:
        """修复最终结果"""
        try:
            # 构建基础结果
            result = {
                "success": True,
                "data": {},
                "task_id": getattr(initial_state, 'task_id', 'unknown'),
                "workflow_status": "completed"
            }

            # 提取需要的数据
            inner_data = {}

            # 添加instructions（如果存在）
            if 'instructions' in state_dict:
                inner_data["instructions"] = state_dict['instructions']

            # 1. 添加修复后的fragment_sequence
            if self.is_debug:
                inner_data["fragment_sequence"] = self._prepare_fragment_sequence_data(correct_fragment_sequence)

            # 2. 添加其他必要的数据
            if self.is_debug:
                self._add_other_data(state_dict, inner_data, correct_fragment_sequence)

            # 3. 添加处理统计
            if self.is_debug:
                inner_data["processing_stats"] = self._build_processing_stats(state_dict, correct_fragment_sequence)

            # 4. 设置data.data
            result["data"] = inner_data

            # 5. 添加时间戳
            result["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            result["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            result["processing_time_ms"] = int(time.time() * 1000)  # 简化处理

            debug(f"修复完成，最终数据结构: {list(inner_data.keys())}")

            return result

        except Exception as e:
            error(f"修复最终结果时出错: {str(e)}")
            return self._build_fallback_result(initial_state)

    def _prepare_fragment_sequence_data(self, fragment_sequence: FragmentSequence) -> Dict[str, Any]:
        """准备片段序列数据"""
        try:
            # 转换为字典
            if hasattr(fragment_sequence, 'dict'):
                fs_dict = fragment_sequence.model_dump()
            elif hasattr(fragment_sequence, '__dict__'):
                fs_dict = fragment_sequence.__dict__
            else:
                fs_dict = fragment_sequence.to_dict()

            # 确保metadata中有修复标记
            metadata = fs_dict.get('metadata', {})
            metadata['fixed_by_output_fixer'] = True
            metadata['fix_timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
            metadata['fix_version'] = "1.0"
            fs_dict['metadata'] = metadata

            # 验证片段数量
            fragments = fs_dict.get('fragments', [])
            if 'stats' not in fs_dict:
                fs_dict['stats'] = {}

            fs_dict['stats']['fragment_count'] = len(fragments)
            fs_dict['stats']['total_duration'] = sum(f.get('duration', 0) for f in fragments)

            if len(fragments) > 0:
                fs_dict['stats']['avg_duration'] = fs_dict['stats']['total_duration'] / len(fragments)
            else:
                fs_dict['stats']['avg_duration'] = 0

            return fs_dict

        except Exception as e:
            error(f"准备片段序列数据时出错: {str(e)}")
            return {}

    def _add_other_data(self, state_dict: Dict[str, Any],
                        inner_data: Dict[str, Any],
                        fragment_sequence: FragmentSequence):
        """添加其他数据"""
        try:
            # 添加shot_sequence
            if 'shot_sequence' in state_dict:
                inner_data["shot_sequence"] = state_dict['shot_sequence']

            # 添加script_analysis
            if 'parsed_script' in state_dict:
                inner_data["script_analysis"] = state_dict['parsed_script']

            # 添加audit_report（如果存在）
            if 'audit_report' in state_dict:
                inner_data["audit_report"] = state_dict['audit_report']

            # 添加continuity_issues（如果存在）
            if 'continuity_issues' in state_dict:
                inner_data["continuity_issues"] = state_dict['continuity_issues']

        except Exception as e:
            error(f"添加其他数据时出错: {str(e)}")

    def _build_processing_stats(self, state_dict: Dict[str, Any],
                                fragment_sequence: FragmentSequence) -> Dict[str, Any]:
        """构建处理统计"""
        try:
            stats = {
                "completed_stages": self._get_completed_stages(state_dict),
                "stage_count": len(self._get_completed_stages(state_dict)),
                "has_final_output": True,
                "current_node": "generate_output",
                "current_stage": "completed",
                "global_loops": state_dict.get('global_current_loops', 0),
                "global_max_loops": state_dict.get('global_max_loops', 0),
                "error_count": len(state_dict.get('error_messages', []))
            }

            # 添加审计信息
            if 'audit_report' in state_dict:
                audit_report = state_dict['audit_report']
                if isinstance(audit_report, dict):
                    stats["audit"] = {
                        "score": audit_report.get('score', 100),
                        "status": audit_report.get('status', 'passed'),
                        "passed_checks": audit_report.get('passed_checks', 0),
                        "total_checks": audit_report.get('total_checks', 0)
                    }

            # 添加片段统计
            stats["fragment_stats"] = {
                "total_fragments": len(fragment_sequence.fragments),
                "avg_duration": fragment_sequence.stats.get('avg_duration', 0) if hasattr(fragment_sequence, 'stats') else 0,
                "fixed_by_output_fixer": True
            }

            return stats

        except Exception as e:
            error(f"构建处理统计时出错: {str(e)}")
            return {}

    def _get_completed_stages(self, state_dict: Dict[str, Any]) -> List[str]:
        """获取完成的阶段"""
        stages = []

        if state_dict.get('parsed_script'):
            stages.append("PARSER")
        if state_dict.get('shot_sequence'):
            stages.append("SEGMENTER")
        if state_dict.get('fragment_sequence'):
            stages.append("SPLITTER")
        if state_dict.get('instructions'):
            stages.append("CONVERTER")
        if state_dict.get('audit_report'):
            stages.append("AUDITOR")
        if state_dict.get('continuity_issues') is not None:
            stages.append("CONTINUITY")

        return stages

    def _convert_state_to_result(self, state_dict: Dict[str, Any],
                                 initial_state: WorkflowState) -> Dict[str, Any]:
        """将状态字典转换为结果格式"""
        try:
            # 这是原始的转换逻辑，从你的代码中提取
            success = False
            data = None

            # 提取信息
            data = state_dict.get('final_output')

            if data is not None:
                success = True
            else:
                # 检查是否到达结束状态
                current_stage = state_dict.get('current_stage')
                current_node = state_dict.get('current_node')

                if current_stage == 'completed' or current_node == 'generate_output':
                    success = True
                    data = {
                        "task_id": state_dict.get('task_id', getattr(initial_state, 'task_id', 'unknown')),
                        "instructions": state_dict.get('instructions'),
                        "fragment_sequence": state_dict.get('fragment_sequence'),
                        "audit_report": state_dict.get('audit_report'),
                        "status": "completed"
                    }

            # 构建结果
            result = {
                "success": success,
                "data": data,
                "errors": state_dict.get('error_messages', []),
                "processing_stats": self._get_completed_stages(state_dict),
                "task_id": getattr(initial_state, 'task_id', 'unknown'),
                "workflow_status": "completed" if success else "failed"
            }

            return result

        except Exception as e:
            error(f"转换状态到结果时出错: {str(e)}")
            return self._build_fallback_result(initial_state)

    def _build_fallback_result(self, initial_state: WorkflowState) -> Dict[str, Any]:
        """构建回退结果"""
        return {
            "success": False,
            "error": "无法修复workflow输出",
            "data": None,
            "task_id": getattr(initial_state, 'task_id', 'unknown'),
            "workflow_status": "failed"
        }

    def _record_fix_history(self, task_id: str, result: Dict[str, Any]):
        """记录修复历史"""
        fix_record = {
            "task_id": task_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": result.get("success", False),
            "fragment_count": 0
        }

        # 统计片段数量
        try:
            data = result.get("data", {}).get("data", {})
            fragment_sequence = data.get("fragment_sequence", {})
            fragments = fragment_sequence.get("fragments", [])
            fix_record["fragment_count"] = len(fragments)
        except:
            pass

        self.fix_history.append(fix_record)

        # 保持历史记录长度
        if len(self.fix_history) > 100:
            self.fix_history = self.fix_history[-100:]
