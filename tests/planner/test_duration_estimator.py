"""
@FileName: ai_estimator.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/12 21:03
"""
import hashlib
import json
import re
from datetime import datetime
from typing import List, Dict, Any

from penshot.neopen.agent.script_parser2.script_parser_models import Scene, Dialogue, Action
from penshot.neopen.agent.shot_generator_bak.base_temporal_planner import BaseTemporalPlanner
from penshot.neopen.agent.shot_generator_bak.estimator.base_estimator import EstimationError, EstimationErrorLevel
from penshot.neopen.agent.temporal_planner.temporal_planner_model import DurationEstimation, ElementType
from penshot.neopen.prompts.temporal_planner_prompt import DurationPromptTemplates


class AIDurationEstimator(BaseTemporalPlanner):
    """ AI 时长估算器 """

    def __init__(self, llm_client):
        """初始化时序规划智能体"""
        super().__init__()
        self.llm = llm_client
        self.prompt_templates = DurationPromptTemplates()
        self.error_log: List[EstimationError] = []
        self.cache: Dict[str, DurationEstimation] = {}

    def estimate_scene_duration(self, scene_data: Scene, context: Dict = None) -> DurationEstimation:
        """
        使用AI估算场景时长（完整实现）
        """
        start_time = datetime.now()

        try:
            # 1. 生成提示词
            prompt = self.prompt_templates.scene_duration_prompt(scene_data, context)
            prompt_hash = self._generate_prompt_hash(prompt)

            # 2. 检查缓存
            cache_key = f"scene_{scene_data.scene_id}_{prompt_hash}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            # 3. 调用LLM
            raw_response = self._call_llm_with_retry(self.llm, prompt)

            # 4. 解析响应
            parsed_result = self._parse_scene_response(raw_response, scene_data, prompt_hash)

            # 5. 验证和修复
            validated_result = self._validate_scene_estimation(parsed_result, scene_data)

            # 6. 添加元数据
            validated_result.prompt_hash = prompt_hash
            validated_result.timestamp = datetime.now().isoformat()
            validated_result.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 7. 缓存结果
            self.cache[cache_key] = validated_result

            return validated_result

        except Exception as e:
            self._log_error(
                self.error_log,
                element_id=scene_data.get("scene_id", "unknown"),
                error_type="scene_estimation_failed",
                message=f"场景估算失败: {str(e)}",
                level=EstimationErrorLevel.ERROR
            )

            # 返回降级估算
            return self._fallback_scene_estimation(scene_data, context)

    def estimate_dialogue_duration(self, dialogue_data: Dialogue, context: Dict = None) -> DurationEstimation:
        """
        使用AI估算对话时长（完整实现）
        """
        start_time = datetime.now()

        try:
            # 检查是否为沉默
            if dialogue_data.type == "silence" or not dialogue_data.content.strip():
                return self.estimate_silence_duration(dialogue_data, context)

            prompt = self.prompt_templates.dialogue_duration_prompt(dialogue_data, context)
            prompt_hash = self._generate_prompt_hash(prompt)

            cache_key = f"dialogue_{dialogue_data.dialogue_id}_{prompt_hash}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            raw_response = self._call_llm_with_retry(self.llm, prompt)
            parsed_result = self._parse_dialogue_response(raw_response, dialogue_data, prompt_hash)
            validated_result = self._validate_dialogue_estimation(parsed_result, dialogue_data)

            # 添加对话特有分析
            validated_result = self._enhance_dialogue_analysis(validated_result, dialogue_data)

            # 添加元数据
            validated_result.prompt_hash = prompt_hash
            validated_result.timestamp = datetime.now().isoformat()
            validated_result.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            self.cache[cache_key] = validated_result
            return validated_result

        except Exception as e:
            self._log_error(
                self.error_log,
                element_id=dialogue_data.dialogue_id,
                error_type="dialogue_estimation_failed",
                message=f"对话估算失败: {str(e)}",
                level=EstimationErrorLevel.ERROR
            )

            return self._fallback_dialogue_estimation(dialogue_data, context)

    def estimate_action_duration(self, action_data: Action, context: Dict = None) -> DurationEstimation:
        """
        使用AI估算动作时长（完整实现）
        """
        start_time = datetime.now()

        try:
            prompt = self.prompt_templates.action_duration_prompt(action_data, context)
            prompt_hash = self._generate_prompt_hash(prompt)

            cache_key = f"action_{action_data.action_id}_{prompt_hash}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            raw_response = self._call_llm_with_retry(self.llm, prompt)
            parsed_result = self._parse_action_response(raw_response, action_data, prompt_hash)
            validated_result = self._validate_action_estimation(parsed_result, action_data)

            # 添加动作序列分析
            validated_result = self._analyze_action_sequence(validated_result, action_data)

            # 为连续性守护智能体准备信息
            validated_result = self._extract_continuity_info(validated_result, action_data)

            # 添加元数据
            validated_result.prompt_hash = prompt_hash
            validated_result.timestamp = datetime.now().isoformat()
            validated_result.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            self.cache[cache_key] = validated_result
            return validated_result

        except Exception as e:
            self._log_error(
                self.error_log,
                element_id=action_data.get("action_id", "unknown"),
                error_type="action_estimation_failed",
                message=f"动作估算失败: {str(e)}",
                level=EstimationErrorLevel.ERROR
            )

            return self._fallback_action_estimation(action_data, context)

    def batch_estimate(self, elements: List[Any], element_type: ElementType,
                       context: Dict = None) -> List[DurationEstimation]:
        """
        批量估算同类型元素（完整实现）
        """
        results = []

        if element_type == ElementType.SCENE:
            prompt = self.prompt_templates.batch_scene_prompt(elements, context)
        elif element_type == ElementType.DIALOGUE:
            prompt = self.prompt_templates.batch_dialogue_prompt(elements, context)
        elif element_type == ElementType.ACTION:
            prompt = self.prompt_templates.batch_action_prompt(elements, context)
        else:
            raise ValueError(f"不支持的元素类型: {element_type.value}")

        try:
            raw_response = self._call_llm_with_retry(self.llm, prompt)
            batch_results = self._parse_batch_response(raw_response, element_type)

            # 将批量结果与原始元素匹配
            for i, element in enumerate(elements):
                element_id = element.get(f"{element_type.value}_id", f"{element_type.value}_{i}")
                result = None

                if i < len(batch_results):
                    # 有对应的批量估算结果
                    batch_result = batch_results[i]

                    # 转换为DurationEstimation对象
                    result = self._create_duration_estimation(batch_result.get("estimated_duration", 0), batch_result.get("confidence", 0.7), batch_result, element, element_type)

                else:
                    # 批量结果不足，回退到单元素估算
                    if element_type == ElementType.SCENE:
                        result = self.estimate_scene_duration(element, context)
                    elif element_type == ElementType.DIALOGUE:
                        result = self.estimate_dialogue_duration(element, context)
                    elif element_type == ElementType.ACTION:
                        result = self.estimate_action_duration(element, context)
                    elif element_type == ElementType.SILENCE:
                        result = self.estimate_silence_duration(element, context)

                results.append(result)

        except Exception as e:
            self._log_error(
                self.error_log,
                element_id=f"batch_{element_type}",
                error_type="batch_estimation_failed",
                message=f"批量估算失败: {str(e)}",
                level=EstimationErrorLevel.ERROR
            )

            # 回退到逐个估算
            for element in elements:
                result = None
                if element_type == ElementType.SCENE:
                    result = self.estimate_scene_duration(element, context)
                elif element_type == ElementType.DIALOGUE:
                    result = self.estimate_dialogue_duration(element, context)
                elif element_type == ElementType.ACTION:
                    result = self.estimate_action_duration(element, context)
                elif element_type == ElementType.SILENCE:
                    result = self.estimate_silence_duration(element, context)
                results.append(result)

        return results

    def estimate_with_context_chain(self, elements: List[Any],
                                    element_type: ElementType) -> List[DurationEstimation]:
        """
        考虑上下文链的估算（元素间有关联时）
        """
        results = []
        previous_context = {}

        for i, element in enumerate(elements):
            # 构建上下文链
            context = {
                "previous_elements": previous_context,
                "position_in_sequence": i,
                "total_elements": len(elements)
            }

            result = None
            # 估算当前元素
            if element_type == ElementType.SCENE:
                result = self.estimate_scene_duration(element, context)
            elif element_type == ElementType.DIALOGUE:
                result = self.estimate_dialogue_duration(element, context)
            elif element_type == ElementType.ACTION:
                result = self.estimate_action_duration(element, context)
            elif element_type == ElementType.SILENCE:
                result = self.estimate_silence_duration(element, context)

            results.append(result)

            # 更新上下文供下一个元素使用
            previous_context = {
                "element_id": element.get(f"{element_type}_id", f"{element_type}_{i}"),
                "estimated_duration": result.estimated_duration,
                # "emotional_state": self._extract_emotional_state(result),
                "key_visuals": result.visual_hints.get("suggested_shot_types", [])
            }

        return results

    def estimate_silence_duration(self, dialogue_data: Dialogue, context: Dict = None) -> DurationEstimation:
        """专门处理沉默时长估算"""
        prompt = self.prompt_templates.silence_duration_prompt(dialogue_data, context)
        prompt_hash = self._generate_prompt_hash(prompt)

        cache_key = f"silence_{dialogue_data.dialogue_id}_{prompt_hash}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        raw_response = self._call_llm_with_retry(self.llm, prompt)
        parsed_result = self._parse_silence_response(raw_response, dialogue_data, prompt_hash)

        # 沉默需要特殊的验证
        validated_result = self._validate_silence_estimation(parsed_result, dialogue_data)

        # 增强沉默分析
        validated_result = self._enhance_silence_analysis(validated_result, dialogue_data)

        validated_result.prompt_hash = prompt_hash
        validated_result.timestamp = datetime.now().isoformat()

        self.cache[cache_key] = validated_result
        return validated_result

    def _parse_scene_response(self, response: str, scene_data: Scene, prompt_hash: str) -> dict[str, dict[Any, Any] | float | dict[str, bool] | str] | None | dict[
        str | Any, str | float | Any]:
        """完整解析场景响应"""
        try:
            # 清理响应文本
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)

            # 验证必需字段
            if "estimated_duration" not in data:
                raise ValueError("响应缺少 estimated_duration 字段")

            # 构建结果字典
            result = {
                "element_id": scene_data.scene_id,
                "element_type": "scene",
                "estimated_duration": float(data.get("estimated_duration", 3.0)),
                "confidence": float(data.get("confidence", 0.7)),
                "reasoning": data.get("reasoning_breakdown", {}),
                "visual_hints": data.get("visual_hints", {}),
                "duration_breakdown": data.get("duration_breakdown", {}),
                "key_factors": data.get("key_factors", []),
                "pacing_notes": data.get("pacing_notes", ""),
                "continuity_requirements": data.get("continuity_requirements", []),
                "shot_suggestions": data.get("shot_suggestions", []),
                "prompt_hash": prompt_hash
            }

            return result

        except (json.JSONDecodeError, ValueError) as e:
            self._log_error(
                self.error_log,
                element_id=scene_data.scene_id,
                error_type="scene_response_parse_error",
                message=f"场景响应解析失败: {str(e)}",
                level=EstimationErrorLevel.WARNING,
                recovery_action="使用降级估算",
                fallback_value=4.0
            )

            # 尝试从文本中提取数字
            duration_match = re.search(r'(\d+\.?\d*)秒', response)
            if duration_match:
                return {
                    "element_id": scene_data.scene_id,
                    "element_type": "scene",
                    "estimated_duration": float(duration_match.group(1)),
                    "confidence": 0.5,
                    "reasoning": {"extracted_from_text": True},
                    "visual_hints": {},
                    "prompt_hash": prompt_hash
                }

            # 完全失败
            return None

    def _parse_dialogue_response(self, response: str, dialogue_data: Dialogue, prompt_hash: str) -> dict[str, Any]:
        """完整解析对话响应"""
        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)

            result = {
                "element_id": dialogue_data.dialogue_id,
                "element_type": "dialogue",
                "estimated_duration": float(data.get("estimated_duration", 2.0)),
                "confidence": float(data.get("confidence", 0.7)),
                "reasoning": data.get("reasoning_breakdown", {}),
                "visual_hints": data.get("visual_hints", {}),
                "speech_characteristics": data.get("speech_characteristics", {}),
                "duration_breakdown": data.get("duration_breakdown", {}),
                "emotional_trajectory": data.get("emotional_trajectory", []),
                "key_factors": data.get("key_factors", []),
                "pacing_notes": data.get("pacing_notes", ""),
                "prompt_hash": prompt_hash
            }

            # 计算情感权重
            result["emotional_weight"] = self._calculate_emotional_weight(dialogue_data, data)

            return result

        except (json.JSONDecodeError, ValueError) as e:
            self._log_error(
                self.error_log,
                element_id=dialogue_data.dialogue_id,
                error_type="dialogue_response_parse_error",
                message=f"对话响应解析失败: {str(e)}",
                level=EstimationErrorLevel.WARNING,
                recovery_action="使用词数估算",
                fallback_value=2.5
            )

            # 基于词数估算
            word_count = len(dialogue_data.content.split())
            fallback_duration = word_count * 0.4  # 0.4秒/词

            return {
                "element_id": dialogue_data.dialogue_id,
                "element_type": "dialogue",
                "estimated_duration": fallback_duration,
                "confidence": 0.4,
                "reasoning": {"fallback_word_based": True, "word_count": word_count},
                "visual_hints": {},
                "prompt_hash": prompt_hash
            }

    def _parse_silence_response(self, response: str, dialogue_data: Dialogue, prompt_hash: str) -> dict[str, Any]:
        """完整解析沉默响应"""
        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)

            result = {
                "element_id": dialogue_data.dialogue_id,
                "element_type": "silence",
                "estimated_duration": float(data.get("estimated_duration", 2.5)),
                "confidence": float(data.get("confidence", 0.7)),
                "reasoning": data.get("reasoning_breakdown", {}),
                "visual_hints": data.get("visual_hints", {}),
                "silence_type": data.get("silence_type", "emotional"),
                "duration_breakdown": data.get("duration_breakdown", {}),
                "emotional_trajectory": data.get("emotional_trajectory", []),
                "key_factors": data.get("key_factors", []),
                "pacing_notes": data.get("pacing_notes", ""),
                "continuity_requirements": data.get("continuity_requirements", []),
                "prompt_hash": prompt_hash
            }

            return result

        except (json.JSONDecodeError, ValueError) as e:
            self._log_error(
                self.error_log,
                element_id=dialogue_data.dialogue_id,
                error_type="silence_response_parse_error",
                message=f"沉默响应解析失败: {str(e)}",
                level=EstimationErrorLevel.WARNING,
                recovery_action="使用默认沉默时长",
                fallback_value=3.0
            )

            return {
                "element_id": dialogue_data.dialogue_id,
                "element_type": "silence",
                "estimated_duration": 3.0,
                "confidence": 0.5,
                "reasoning": {"fallback_default_silence": True},
                "visual_hints": {},
                "prompt_hash": prompt_hash
            }

    def _parse_action_response(self, response: str, action_data: Action, prompt_hash: str) -> dict[str, Any]:
        """完整解析动作响应"""
        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)

            result = {
                "element_id": action_data.action_id,
                "element_type": "action",
                "estimated_duration": float(data.get("estimated_duration", 1.5)),
                "confidence": float(data.get("confidence", 0.7)),
                "reasoning": data.get("reasoning_breakdown", {}),
                "visual_hints": data.get("visual_hints", {}),
                "action_components": data.get("action_components", []),
                "duration_breakdown": data.get("duration_breakdown", {}),
                "key_factors": data.get("key_factors", []),
                "pacing_notes": data.get("pacing_notes", ""),
                "continuity_requirements": data.get("continuity_requirements", []),
                "prompt_hash": prompt_hash
            }

            # 计算复杂度得分
            result["complexity_score"] = self._calculate_action_complexity(action_data, data)

            return result

        except (json.JSONDecodeError, ValueError) as e:
            self._log_error(
                self.error_log,
                element_id=action_data.get("action_id", "unknown"),
                error_type="action_response_parse_error",
                message=f"动作响应解析失败: {str(e)}",
                level=EstimationErrorLevel.WARNING,
                recovery_action="基于描述长度估算",
                fallback_value=1.5
            )

            # 基于描述长度估算
            desc = action_data.get("description", "")
            word_count = len(desc.split())
            fallback_duration = word_count * 0.3  # 0.3秒/词

            return {
                "element_id": action_data.get("action_id", "unknown"),
                "element_type": "action",
                "estimated_duration": fallback_duration,
                "confidence": 0.4,
                "reasoning": {"fallback_word_based": True, "word_count": word_count},
                "visual_hints": {},
                "prompt_hash": prompt_hash
            }

    def _parse_batch_response(self, response: str, element_type: ElementType) -> List[Dict]:
        """解析批量响应"""
        try:
            cleaned_response = self._clean_json_response(response)
            data = json.loads(cleaned_response)

            if "results" in data:
                return data["results"]
            else:
                # 如果没有results字段，尝试直接解析为数组
                if isinstance(data, list):
                    return data
                else:
                    # 尝试其他可能的格式
                    return [data]

        except (json.JSONDecodeError, ValueError) as e:
            self._log_error(
                self.error_log,
                element_id=f"batch_{element_type.value}",
                error_type="batch_response_parse_error",
                message=f"批量响应解析失败: {str(e)}",
                level=EstimationErrorLevel.ERROR
            )

            return []

    def _validate_scene_estimation(self, parsed_result: dict[str, Any], scene_data: Scene) -> DurationEstimation:
        """验证场景估算结果"""
        if parsed_result is None:
            return self._fallback_scene_estimation(scene_data)

        duration = parsed_result.estimated_duration
        confidence = parsed_result.confidence

        # 验证时长合理性
        if duration <= 0:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="invalid_duration",
                message=f"场景时长无效: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="使用默认值4.0秒",
                fallback_value=4.0
            )
            duration = 4.0
            confidence = min(confidence, 0.5)  # 降低置信度

        # 验证置信度
        if confidence < 0.3:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="low_confidence",
                message=f"场景估算置信度过低: {confidence}",
                level=EstimationErrorLevel.WARNING
            )

        # 验证场景时长范围（通常1-15秒）
        if duration > 20:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="excessive_duration",
                message=f"场景时长过长: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="限制为15秒"
            )
            duration = min(duration, 15.0)

        # 转换为DurationEstimation对象
        return self._create_duration_estimation(duration, confidence, parsed_result, scene_data, ElementType.SCENE)

    def _validate_dialogue_estimation(self, parsed_result: dict[str, Any], dialogue_data: Dialogue) -> DurationEstimation:
        """验证对话估算结果"""
        if parsed_result is None:
            return self._fallback_dialogue_estimation(dialogue_data)

        duration = parsed_result.estimated_duration
        confidence = parsed_result.confidence

        # 验证时长合理性
        word_count = len(dialogue_data.content.split())

        if word_count > 0:
            # 检查词速是否合理（通常0.2-1.0秒/词）
            seconds_per_word = duration / word_count if word_count > 0 else 0
            if seconds_per_word < 0.1:
                self._log_error(
                    self.error_log,
                    element_id=parsed_result.element_id,
                    error_type="too_fast_speech",
                    message=f"语速过快: {seconds_per_word:.2f}秒/词",
                    level=EstimationErrorLevel.WARNING,
                    recovery_action="调整为基础语速"
                )
                duration = word_count * 0.4  # 调整为0.4秒/词
                confidence = min(confidence, 0.6)
            elif seconds_per_word > 1.5:
                self._log_error(
                    self.error_log,
                    element_id=parsed_result.element_id,
                    error_type="too_slow_speech",
                    message=f"语速过慢: {seconds_per_word:.2f}秒/词",
                    level=EstimationErrorLevel.WARNING,
                    recovery_action="限制为1.0秒/词"
                )
                duration = word_count * 1.0
                confidence = min(confidence, 0.6)

        # 转换为DurationEstimation对象
        return self._create_duration_estimation(duration, confidence, parsed_result, dialogue_data, ElementType.DIALOGUE)

    def _validate_silence_estimation(self, parsed_result: dict[str, Any], dialogue_data: Dialogue) -> DurationEstimation:
        """验证沉默估算结果"""
        if parsed_result is None:
            return self._fallback_silence_estimation(dialogue_data)

        duration = parsed_result.estimated_duration
        confidence = parsed_result.confidence

        # 验证沉默时长合理性（通常1-8秒）
        if duration < 0.5:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="silence_too_short",
                message=f"沉默时长过短: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="调整为1.0秒"
            )
            duration = 1.0
            confidence = min(confidence, 0.6)
        elif duration > 10:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="silence_too_long",
                message=f"沉默时长过长: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="限制为8.0秒"
            )
            duration = min(duration, 8.0)
            confidence = min(confidence, 0.6)

        # 转换为DurationEstimation对象
        return self._create_duration_estimation(duration, confidence, parsed_result, dialogue_data, ElementType.SILENCE)

    def _validate_action_estimation(self, parsed_result: dict[str, Any], action_data: Action) -> DurationEstimation:
        """验证动作估算结果"""
        if parsed_result is None:
            return self._fallback_action_estimation(action_data)

        duration = parsed_result.estimated_duration
        confidence = parsed_result.confidence

        # 验证动作时长合理性（通常0.5-8秒）
        if duration < 0.3:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="action_too_short",
                message=f"动作时长过短: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="调整为0.5秒"
            )
            duration = 0.5
            confidence = min(confidence, 0.6)
        elif duration > 12:
            self._log_error(
                self.error_log,
                element_id=parsed_result.element_id,
                error_type="action_too_long",
                message=f"动作时长过长: {duration}秒",
                level=EstimationErrorLevel.WARNING,
                recovery_action="限制为10.0秒"
            )
            duration = min(duration, 10.0)
            confidence = min(confidence, 0.6)

        # 转换为DurationEstimation对象
        return self._create_duration_estimation(duration, confidence, parsed_result, action_data, ElementType.ACTION)

    def _enhance_dialogue_analysis(self, result: DurationEstimation, dialogue_data: Dialogue) -> DurationEstimation:
        """增强对话分析"""
        # 分析对话的情感值
        emotion = dialogue_data.emotion
        content = dialogue_data.content

        # 检测情感关键词
        emotional_keywords = ["你还好吗", "我回来了", "……", "？"]
        emotion_score = 0

        for keyword in emotional_keywords:
            if keyword in content:
                emotion_score += 1

        # 根据情绪描述增强
        if "微颤" in emotion:
            emotion_score += 2
        if "哽咽" in emotion:
            emotion_score += 3

        # 更新情感轨迹
        if not result.emotional_trajectory and emotion_score > 0:
            result.emotional_trajectory = [
                {"time": 0.0, "emotion": "anticipation", "intensity": 5},
                {"time": result.estimated_duration * 0.3, "emotion": "expression", "intensity": 7},
                {"time": result.estimated_duration * 0.8, "emotion": "lingering", "intensity": 6}
            ]

        return result

    def _enhance_silence_analysis(self, result: DurationEstimation, dialogue_data: Dialogue) -> DurationEstimation:
        """增强沉默分析"""
        # 根据动作描述调整
        if "张了张嘴" in dialogue_data.parenthetical:
            # 尝试说话但失败的动作需要时间
            if result.estimated_duration < 2.0:
                result.estimated_duration = 2.5
                result.confidence = min(result.confidence, 0.7)

        # 添加视觉建议
        if not result.visual_hints:
            result.visual_hints = {
                "suggested_shot_types": ["extreme_close_up", "slow_zoom"],
                "focus_elements": ["eyes", "mouth", "hands"],
                "expression_emphasis": "micro_expressions"
            }

        return result

    def _analyze_action_sequence(self, result: DurationEstimation, action_data: Action) -> DurationEstimation:
        """分析动作序列"""
        # 如果是关键转折动作，增加情感权重
        key_action_indicators = ["按下接听键", "手指瞬间收紧", "泪水在眼眶中打转", "猛地坐直"]

        for indicator in key_action_indicators:
            if indicator in action_data.description:
                # 添加关键动作标记
                result.key_factors.append("关键转折动作")

                # 增加视觉建议
                if "visual_hints" not in result:
                    result.visual_hints = {}
                result.visual_hints["dramatic_emphasis"] = True
                result.visual_hints["slow_motion_consideration"] = True

                break

        return result

    def _extract_continuity_info(self, result: DurationEstimation, action_data: Action) -> DurationEstimation:
        """提取连续性信息（为智能体3准备）"""
        actor = action_data.actor
        description = action_data.description

        # 检测状态变化
        state_changes = []

        if "主角" in actor:
            if "坐直" in description:
                state_changes.append("posture:从蜷坐到挺直")
            if "手指收紧" in description:
                state_changes.append("hand_tension:放松到紧绷")
            if "泪水" in description:
                state_changes.append("emotional_state:震惊到悲伤")

        if "旧羊毛毯" in actor and "滑落" in description:
            state_changes.append("prop_position:从肩头到地板")

        if state_changes:
            result.continuity_requirements.extend(state_changes)

        return result

    def _fallback_scene_estimation(self, scene_data: Scene, context: Dict = None) -> DurationEstimation:
        """场景估算降级方案"""
        # 基于简单规则的降级估算
        word_count = len(scene_data.description.split())
        base_duration = word_count * 0.06

        # 关键视觉元素加成
        visual_bonus = len(scene_data.key_visuals) * 0.4

        # 情绪加成
        mood_bonus = 0
        if "紧张" in scene_data.mood or "压抑" in scene_data.mood:
            mood_bonus = 1.5
        elif "孤独" in scene_data.mood:
            mood_bonus = 1.0

        total_duration = base_duration + visual_bonus + mood_bonus

        # 限制在合理范围
        total_duration = max(2.0, min(total_duration, 12.0))

        return DurationEstimation(
            element_id=scene_data.scene_id,
            element_type=ElementType.SCENE,
            original_duration=0,
            estimated_duration=round(total_duration, 2),
            confidence=0.4,
            reasoning_breakdown={"fallback_estimation": True, "method": "word_count_based"},
            visual_hints={"fallback": True, "suggested_shot_types": ["establishing_shot"]},
            key_factors=["fallback_estimation"],
            pacing_notes="降级估算，建议人工审核",
            emotional_weight=1,
            visual_complexity=1,
            character_states={},
            prop_states={},
            estimated_at=datetime.now().isoformat()
        )

    def _fallback_dialogue_estimation(self, dialogue_data: Dialogue, context: Dict = None) -> DurationEstimation:
        """对话估算降级方案"""
        content = dialogue_data.content
        emotion = dialogue_data.emotion

        word_count = len(content.split())

        # 基础语速
        words_per_second = 2.5

        # 情绪调整
        if "微颤" in emotion or "哽咽" in emotion:
            words_per_second = 1.8
        elif "快速" in emotion:
            words_per_second = 3.2

        base_duration = word_count / words_per_second if words_per_second > 0 else 0

        # 添加停顿
        pause = 0.3 if word_count > 0 else 0

        total_duration = base_duration + pause

        # 如果是沉默
        if not content.strip():
            total_duration = 2.5  # 默认沉默时长

        return DurationEstimation(
            element_id=dialogue_data.dialogue_id,
            element_type=ElementType.DIALOGUE,
            original_duration=0,
            estimated_duration=round(total_duration, 2),
            confidence=0.4,
            reasoning_breakdown={"fallback_estimation": True, "method": "word_count_with_emotion"},
            visual_hints={"fallback": True},
            key_factors=["fallback_estimation"],
            pacing_notes="降级估算，基于词数和情绪",
            emotional_weight=1,
            visual_complexity=1,
            character_states={},
            prop_states={},
            estimated_at=datetime.now().isoformat()
        )

    def _fallback_silence_estimation(self, dialogue_data: Dialogue, context: Dict = None) -> DurationEstimation:
        """沉默估算降级方案"""
        parenthetical = dialogue_data.parenthetical

        # 基于动作描述的沉默时长
        base_duration = 2.0

        if "张了张嘴" in parenthetical:
            base_duration = 3.0  # 尝试说话但失败需要更长时间
        elif "震惊" in parenthetical or "愣住" in parenthetical:
            base_duration = 3.5

        return DurationEstimation(
            element_id=dialogue_data.dialogue_id,
            element_type=ElementType.SILENCE,
            original_duration=0,
            estimated_duration=round(base_duration, 2),
            confidence=0.5,
            reasoning_breakdown={"fallback_estimation": True, "method": "parenthetical_based"},
            visual_hints={"fallback": True, "suggested_shot_types": ["close_up"]},
            key_factors=["fallback_estimation"],
            pacing_notes="降级估算，基于动作描述",
            emotional_weight=1,
            visual_complexity=1,
            character_states={},
            prop_states={},
            estimated_at=datetime.now().isoformat()
        )

    def _fallback_action_estimation(self, action_data: Action, context: Dict = None) -> DurationEstimation:
        """动作估算降级方案"""
        word_count = len(action_data.description.split())

        # 基于类型的基础时长
        type_baselines = {
            "posture": 2.0,
            "gaze": 1.5,
            "gesture": 1.2,
            "facial": 1.0,
            "physiological": 0.8,
            "interaction": 1.5,
            "prop_fall": 1.0,
            "device_alert": 2.0
        }

        base_duration = type_baselines.get(action_data.type, 1.5)

        # 根据描述复杂度调整
        complexity_factor = min(word_count / 5.0, 3.0)  # 每5词增加一倍，最多3倍

        total_duration = base_duration * complexity_factor

        return DurationEstimation(
            element_id=action_data.action_id,
            element_type=ElementType.ACTION,
            original_duration=0,
            estimated_duration=round(total_duration, 2),
            confidence=0.4,
            reasoning_breakdown={"fallback_estimation": True, "method": "type_and_complexity"},
            visual_hints={"fallback": True},
            key_factors=["fallback_estimation"],
            pacing_notes="降级估算，基于类型和复杂度",
            emotional_weight=1,
            visual_complexity=1,
            character_states={},
            prop_states={},
            estimated_at=datetime.now().isoformat()
        )

    def _clean_json_response(self, response: str) -> str:
        """清理JSON响应文本"""
        # 移除可能的Markdown代码块标记
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'\s*```', '', cleaned)

        # 移除开头和结尾的空白
        cleaned = cleaned.strip()

        # 尝试找到第一个{和最后一个}
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1

        if start >= 0 and end > start:
            cleaned = cleaned[start:end]

        return cleaned

    def _generate_prompt_hash(self, prompt: str) -> str:
        """生成提示词哈希（用于缓存键）"""
        return hashlib.md5(prompt.encode('utf-8')).hexdigest()[:8]

    def _calculate_emotional_weight(self, dialogue_data: Dialogue, ai_data: Dict) -> float:
        """计算情感权重"""
        base_weight = 1.0

        # 基于情绪描述
        emotion = dialogue_data.emotion
        if "微颤" in emotion:
            base_weight += 0.5
        if "哽咽" in emotion:
            base_weight += 1.0

        # 基于内容
        content = dialogue_data.content
        if "陈默" in content:  # 关键名字
            base_weight += 0.3
        if "？" in content or "……" in content:  # 疑问或省略号
            base_weight += 0.2

        # 基于AI分析（如果有）
        emotional_trajectory = ai_data.get("emotional_trajectory", [])
        if emotional_trajectory:
            avg_intensity = sum(point.get("intensity", 5) for point in emotional_trajectory) / len(emotional_trajectory)
            base_weight += (avg_intensity - 5) / 10  # 映射到权重调整

        return round(base_weight, 2)

    def _calculate_action_complexity(self, action_data: Action, ai_data: Dict) -> float:
        """计算动作复杂度得分"""
        # 基于描述长度
        word_count = len(action_data.description.split())
        length_score = min(word_count / 8.0, 3.0)  # 8词为基准，最多3分

        # 基于动作组件数量
        components = ai_data.get("action_components", [])
        component_score = min(len(components) / 3.0, 2.0)  # 3组件为基准，最多2分

        # 基于动作类型
        type_scores = {
            "complex_sequence": 2.0,
            "interaction": 1.5,
            "posture": 1.2,
            "gaze": 1.0,
            "gesture": 0.8,
            "facial": 0.8,
            "physiological": 0.6
        }
        type_score = type_scores.get(action_data.type, 1.0)

        # 综合得分
        total_score = (length_score + component_score + type_score) / 3.0

        return round(total_score, 2)

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()

    def clear_errors(self):
        """清空错误日志"""
        self.error_log.clear()


    def _create_duration_estimation(self, duration, confidence, parsed_data: Dict, element_data: Any,
                                    element_type: ElementType) -> DurationEstimation:
        """创建统一的DurationEstimation对象"""

        # 获取元素ID
        element_id = self._get_element_id(element_data, element_type)

        # 创建对象
        return DurationEstimation(
            element_id=element_id,
            element_type=element_type,
            original_duration=element_data.duration,
            estimated_duration=round(duration, 2),
            confidence=round(confidence, 2),
            reasoning_breakdown=parsed_data["reasoning_breakdown"],
            visual_hints=parsed_data["visual_hints"],
            key_factors=parsed_data["key_factors"],
            pacing_notes=parsed_data["pacing_notes"],
            emotional_weight=parsed_data.get("emotional_weight", 1.0),
            visual_complexity=parsed_data["visual_complexity"],
            character_states=parsed_data["character_states"],
            prop_states=parsed_data["prop_states"],
            estimated_at=datetime.now().isoformat()
        )

    def _get_element_id(self, element_data: Any, element_type: ElementType) -> str:
        """从元素数据中提取ID"""
        if element_type == ElementType.SCENE:
            return element_data.scene_id
        elif element_type == ElementType.DIALOGUE or element_type == ElementType.SILENCE:
            return element_data.dialogue_id
        elif element_type == ElementType.ACTION:
            return element_data.action_id

        return "unknown_element"
