"""
@FileName: llm_shot_generator.py
@Description: 基于LLM的镜头生成器
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 17:35
"""
from typing import Optional, List

from video_shot_breakdown.hengline.agent.base_agent import BaseAgent
from video_shot_breakdown.hengline.agent.script_parser.script_parser_models import ParsedScript, SceneInfo
from video_shot_breakdown.hengline.agent.shot_segmenter.base_shot_segmenter import BaseShotSegmenter
from video_shot_breakdown.hengline.agent.shot_segmenter.rule_shot_segmenter import RuleShotSegmenter
from video_shot_breakdown.hengline.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from video_shot_breakdown.hengline.hengline_config import HengLineConfig
from video_shot_breakdown.logger import info, error


class LLMShotSegmenter(BaseShotSegmenter, BaseAgent):
    """基于LLM的分镜拆分器"""

    def __init__(self, llm_client, config: Optional[HengLineConfig]):
        super().__init__(config)
        self.llm_client = llm_client

    def split(self, parsed_script: ParsedScript) -> ShotSequence:
        """使用LLM拆分剧本"""
        info(f"使用LLM拆分分镜，剧本: {parsed_script.title}")

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
                scene_shots = self._split_scene_with_llm(scene, current_time, len(all_shots))
                all_shots.extend(scene_shots)

                # 更新当前时间
                if scene_shots:
                    current_time = scene_shots[-1].start_time + scene_shots[-1].duration

            except Exception as e:
                error(f"场景{scene.id}分镜失败: {str(e)}")
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
        return self._post_process(shot_sequence)

    def _split_scene_with_llm(self, scene: SceneInfo, start_time: float, shot_offset: int) -> List[ShotInfo]:
        """使用LLM拆分单个场景"""
        # 准备元素列表文本
        elements_list = "\n".join([
            f"{i + 1}. [{elem.type}] {elem.character or '场景'}: {elem.content[:50]}... (时长: {elem.duration}秒)"
            for i, elem in enumerate(scene.elements)
        ])

        # 准备提示词
        user_prompt = self._get_prompt_template("shot_segmenter_user").format(
            location=scene.location,
            time_of_day=scene.time_of_day or "未指定",
            description=scene.description or "无描述",
            elements_list=elements_list
        )

        system_prompt = self._get_prompt_template("shot_segmenter_system")

        # 调用LLM
        response = self._call_llm_chat_with_retry(self.llm_client, system_prompt, user_prompt)

        # 解析响应
        shots_data = self._parse_ai_response(response, scene.id, start_time, shot_offset)

        return shots_data

    def _parse_ai_response(self, response: str, scene_id: str, start_time: float, shot_offset: int) -> List[ShotInfo]:
        """解析LLM响应"""
        import json
        shots_data = json.loads(response)

        shots = []
        current_time = start_time

        for i, shot_data in enumerate(shots_data):
            shot = ShotInfo(
                id=self._generate_shot_id(shot_offset + i),
                scene_id=scene_id,
                description=shot_data.get("description", ""),
                start_time=round(current_time, 2),
                duration=shot_data.get("duration", 3.0),
                shot_type=ShotType(shot_data.get("shot_type", "medium_shot")),
                main_character=shot_data.get("main_character"),
                element_ids=shot_data.get("element_ids", []),
                confidence=0.8  # LLM结果默认置信度
            )

            shots.append(shot)
            current_time += shot.duration

        return shots
