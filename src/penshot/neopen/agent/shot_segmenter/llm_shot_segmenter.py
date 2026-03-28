"""
@FileName: llm_shot_segmenter.py
@Description: 基于LLM的镜头生成器
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/26 17:35
"""
import json
import re
from typing import Optional, List, Dict

from penshot.logger import info, error, debug, warning
from penshot.neopen.agent.base_llm_agent import BaseLLMAgent
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, SceneInfo, GlobalMetadata
from penshot.neopen.agent.shot_segmenter.base_shot_segmenter import BaseShotSegmenter
from penshot.neopen.agent.shot_segmenter.rule_shot_segmenter import RuleShotSegmenter
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from penshot.neopen.shot_config import ShotConfig
from penshot.utils.log_utils import print_log_exception


class LLMShotSegmenter(BaseShotSegmenter, BaseLLMAgent):
    """基于LLM的分镜拆分器"""

    def __init__(self, llm_client, config: Optional[ShotConfig]):
        super().__init__(config)
        self.llm_client = llm_client
        self.current_repair_params = None

        # 初始化提示词
        self._init_prompts()

    def _init_prompts(self):
        """初始化提示词模板"""
        # 系统提示词
        self.system_prompt = self._get_prompt_template("shot_segmenter_system")

        # 用户提示词模板
        self.user_prompt_template = self._get_prompt_template("shot_segmenter_user")


    def split(self, parsed_script: ParsedScript, repair_params: Optional[QualityRepairParams]) -> ShotSequence:
        """使用LLM拆分剧本"""
        info(f"使用LLM拆分分镜，剧本: {parsed_script.title}")

        # 如果有修复参数，保存到实例
        if repair_params:
            self.current_repair_params = repair_params

        all_shots = []
        current_time = 0.0

        # 设置剧本引用
        script_ref = {
            "title": parsed_script.title or "未命名剧本",
            "total_elements": parsed_script.stats.get("total_elements", 0),
            "original_duration": parsed_script.stats.get("total_duration", 0.0)
        }

        # 为每个场景调用LLM
        for scene_idx, scene in enumerate(parsed_script.scenes):
            try:
                scene_shots = self._split_scene_with_llm(
                    scene, current_time, len(all_shots),
                    parsed_script.global_metadata
                )
                all_shots.extend(scene_shots)

                # 更新当前时间
                if scene_shots:
                    current_time = scene_shots[-1].start_time + scene_shots[-1].duration

            except Exception as e:
                error(f"场景{scene.id}分镜失败: {str(e)}")
                print_log_exception()
                # 降级到规则拆分
                rule_splitter = RuleShotSegmenter(self.config)
                fallback_shots = rule_splitter.split_scene(scene, current_time, len(all_shots))
                all_shots.extend(fallback_shots)

        # 构建序列
        shot_sequence = ShotSequence(
            script_reference=script_ref,
            shots=all_shots
        )

        # 后处理
        shot_sequence = self._post_process(shot_sequence)

        # 如果有修复参数，应用修复
        if self.current_repair_params and self.current_repair_params.fix_needed:
            shot_sequence = self._apply_repair_params(shot_sequence, parsed_script)

        return shot_sequence

    def _split_scene_with_llm(self, scene: SceneInfo, start_time: float,
                              shot_offset: int, global_metadata: GlobalMetadata) -> List[ShotInfo]:
        """使用LLM拆分单个场景"""

        # 使用详细格式
        global_context = self._format_global_metadata(global_metadata, scene_id=scene.id, format_type="shot")

        # 准备元素列表文本
        elements_list = "\n".join([
            f"  {i + 1}. [{elem.type.value}] {elem.character or '场景'}, {elem.emotion}: {elem.content} (预估时长: {elem.duration}秒)"
            for i, elem in enumerate(scene.elements)
        ])

        # 构建修复提示（如果有）
        repair_hint = ""
        if self.current_repair_params and self.current_repair_params.fix_needed and self.current_repair_params.issue_types:
            repair_hint = f"""
                【重要：修复要求】
                    之前的分镜存在以下问题：
                    - 问题类型: {', '.join(self.current_repair_params.issue_types)}
                    - 修复建议: {json.dumps(self.current_repair_params.suggestions, ensure_ascii=False) if self.current_repair_params.suggestions else '无'}
                    
                    请根据上述建议调整分镜生成策略，避免再次出现相同问题。
                """

        # 准备用户提示词
        user_prompt = self.user_prompt_template.format(
            scene_id=scene.id,
            location=scene.location,
            time_of_day=scene.time_of_day or "未指定",
            description=scene.description or "无描述",
            weather=scene.weather or "无",
            elements_count=len(scene.elements),
            elements_list=elements_list,
            global_context=global_context,
            repair_hint=repair_hint
        )

        debug(f"场景{scene.id}分镜提示词长度: {len(user_prompt)}字符")

        # 调用LLM
        response = self._call_llm_chat_with_retry(self.llm_client, self.system_prompt, user_prompt)

        # 解析响应
        shots_data = self._parse_ai_response(response, scene.id, start_time, shot_offset)

        return shots_data

    def _parse_ai_response(self, response: str, scene_id: str, start_time: float, shot_offset: int) -> List[ShotInfo]:
        """解析LLM响应并构建镜头列表"""
        shots = []

        try:
            # 尝试解析JSON
            # 清理响应：移除markdown代码块标记
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            # 解析JSON
            shots_data = json.loads(cleaned_response)

            # 如果返回的是单个镜头对象，转换为列表
            if isinstance(shots_data, dict):
                shots_data = [shots_data]

            current_time = start_time

            for i, shot_data in enumerate(shots_data):
                shot_id = self._generate_shot_id(shot_offset + i)

                # 获取shot_type
                shot_type_str = shot_data.get("shot_type", "medium_shot")
                try:
                    shot_type = ShotType(shot_type_str)
                except ValueError:
                    warning(f"未知的镜头类型: {shot_type_str}, 使用默认值medium_shot")
                    shot_type = ShotType.MEDIUM_SHOT

                # 获取时长
                duration = shot_data.get("duration", 3.0)
                if duration < 0.5:
                    duration = 1.0
                elif duration > 8.0:
                    duration = 5.0

                shot = ShotInfo(
                    id=shot_id,
                    scene_id=scene_id,
                    description=shot_data.get("description", ""),
                    start_time=round(current_time, 2),
                    duration=round(duration, 2),
                    emotion=shot_data.get("emotion", "neutral"),
                    shot_type=shot_type,
                    main_character=shot_data.get("main_character"),
                    element_ids=shot_data.get("element_ids", []),
                    confidence=shot_data.get("confidence", 0.8)
                )

                shots.append(shot)
                current_time += shot.duration

            info(f"场景{scene_id}生成{len(shots)}个镜头")

        except json.JSONDecodeError as e:
            error(f"解析LLM响应JSON失败: {e}")
            error(f"原始响应: {response[:500]}...")
            # 尝试从文本中提取JSON
            shots_data = self._extract_json_from_text(response)
            if shots_data:
                return self._parse_ai_response(json.dumps(shots_data), scene_id, start_time, shot_offset)

        except Exception as e:
            error(f"解析镜头数据异常: {e}")
            print_log_exception()

        return shots

    def _extract_json_from_text(self, text: str) -> Optional[List[Dict]]:
        """从文本中提取JSON数据"""
        # 尝试匹配JSON数组
        json_pattern = r'\[\s*\{.*?\}\s*\]'
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass

        # 尝试匹配JSON对象
        json_pattern = r'\{\s*".*?"\s*:.*?\}'
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            try:
                return [json.loads(match.group())]
            except:
                pass

        return None

    def _apply_repair_params(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> ShotSequence:
        """应用修复参数调整分镜"""
        if not self.current_repair_params:
            return shot_sequence

        info(f"应用修复参数调整分镜，问题类型: {self.current_repair_params.issue_types}")

        suggestions = self.current_repair_params.suggestions or {}

        # 根据问题类型进行调整
        issue_types = set(self.current_repair_params.issue_types)

        if "shot_insufficient" in issue_types:
            # 镜头不足：增加更多镜头
            shot_sequence = self._add_more_shots(shot_sequence, parsed_script)

        if "shot_duration_too_long" in issue_types or "duration" in str(issue_types):
            # 时长过长：拆分长镜头
            shot_sequence = self._split_long_shots(shot_sequence)

        if "shot_type_uniform" in issue_types:
            # 镜头类型单一：调整类型
            shot_sequence = self._diversify_shot_types(shot_sequence)

        if "shot_repetitive" in issue_types:
            # 重复镜头：调整相邻镜头
            shot_sequence = self._fix_repetitive_shots(shot_sequence)

        if "shot_description_missing" in issue_types:
            # 描述缺失：补充描述
            shot_sequence = self._enhance_descriptions(shot_sequence, parsed_script)

        return shot_sequence

    def _add_more_shots(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> ShotSequence:
        """增加更多镜头"""
        new_shots = []
        for shot in shot_sequence.shots:
            new_shots.append(shot)
            # 对于重要镜头，添加特写
            if shot.main_character and shot.duration > 3.0:
                closeup = ShotInfo(
                    id=f"{shot.id}_cu",
                    scene_id=shot.scene_id,
                    description=f"{shot.main_character}的特写镜头，展现面部表情和情绪",
                    start_time=shot.start_time + shot.duration,
                    duration=min(2.0, shot.duration * 0.5),
                    emotion=shot.emotion,
                    shot_type=ShotType.CLOSE_UP,
                    main_character=shot.main_character,
                    element_ids=shot.element_ids,
                    confidence=0.7
                )
                new_shots.append(closeup)
                info(f"增加特写镜头: {closeup.id}")

        shot_sequence.shots = new_shots
        info(f"增加镜头后总数: {len(new_shots)}个")
        return shot_sequence

    def _split_long_shots(self, shot_sequence: ShotSequence) -> ShotSequence:
        """拆分过长的镜头"""
        new_shots = []
        for shot in shot_sequence.shots:
            if shot.duration > 5.0:
                # 拆分成两个镜头
                half_duration = shot.duration / 2
                shot1 = shot
                shot1.duration = round(half_duration, 2)
                new_shots.append(shot1)

                shot2 = ShotInfo(
                    id=f"{shot.id}_2",
                    scene_id=shot.scene_id,
                    description=f"{shot.description}（继续）",
                    start_time=shot.start_time + half_duration,
                    duration=round(half_duration, 2),
                    emotion=shot.emotion,
                    shot_type=shot.shot_type,
                    main_character=shot.main_character,
                    element_ids=shot.element_ids,
                    confidence=shot.confidence * 0.9
                )
                new_shots.append(shot2)
                info(f"拆分镜头: {shot.id} {shot.duration}s -> {half_duration:.1f}s + {half_duration:.1f}s")
            else:
                new_shots.append(shot)
        shot_sequence.shots = new_shots
        return shot_sequence

    def _diversify_shot_types(self, shot_sequence: ShotSequence) -> ShotSequence:
        """多样化镜头类型"""
        shot_types = [
            ShotType.WIDE_SHOT,  # 远景
            ShotType.MEDIUM_SHOT,  # 中景
            ShotType.CLOSE_UP,  # 特写
            ShotType.LONG_SHOT,  # 长焦
            ShotType.EXTREME_CLOSE_UP  # 极特写
        ]

        for i, shot in enumerate(shot_sequence.shots):
            # 根据位置分配不同类型
            type_index = i % len(shot_types)
            old_type = shot.shot_type
            shot.shot_type = shot_types[type_index]
            if old_type != shot.shot_type:
                info(f"调整镜头类型: {shot.id} {old_type.value} -> {shot.shot_type.value}")

        return shot_sequence

    def _fix_repetitive_shots(self, shot_sequence: ShotSequence) -> ShotSequence:
        """修复重复镜头"""
        shot_types = [ShotType.WIDE_SHOT, ShotType.MEDIUM_SHOT, ShotType.CLOSE_UP]

        for i in range(len(shot_sequence.shots) - 1):
            curr = shot_sequence.shots[i]
            next_shot = shot_sequence.shots[i + 1]

            # 如果相邻镜头类型相同，调整下一个
            if curr.shot_type == next_shot.shot_type:
                # 选择不同的类型
                for alt_type in shot_types:
                    if alt_type != curr.shot_type:
                        old_type = next_shot.shot_type
                        next_shot.shot_type = alt_type
                        info(f"修复重复镜头: {next_shot.id} {old_type.value} -> {alt_type.value}")
                        break

        return shot_sequence

    def _enhance_descriptions(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> ShotSequence:
        """增强镜头描述"""
        for shot in shot_sequence.shots:
            if not shot.description or len(shot.description.strip()) < 15:
                # 根据镜头类型生成默认描述
                type_desc = {
                    ShotType.WIDE_SHOT: "广阔的视角展现场景全貌",
                    ShotType.MEDIUM_SHOT: "中景镜头，清晰展现人物动作和表情",
                    ShotType.CLOSE_UP: "特写镜头，聚焦细节和情感",
                    ShotType.LONG_SHOT: "长焦镜头，营造空间感",
                    ShotType.EXTREME_CLOSE_UP: "极特写，强调关键细节"
                }

                default_desc = type_desc.get(shot.shot_type, "镜头画面")

                if shot.main_character:
                    shot.description = f"{shot.main_character}的{default_desc}"
                else:
                    shot.description = default_desc

                info(f"补充描述: {shot.id} -> {shot.description[:50]}...")

        return shot_sequence
