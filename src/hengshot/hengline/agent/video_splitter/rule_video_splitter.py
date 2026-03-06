"""
@FileName: llm_video_splitter.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 22:30
"""
from typing import List, Optional

from hengshot.hengline.agent.script_parser.script_parser_models import ParsedScript
from hengshot.hengline.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from hengshot.hengline.agent.video_splitter.base_video_splitter import BaseVideoSplitter
from hengshot.hengline.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from hengshot.hengline.hengline_config import HengLineConfig
from hengshot.logger import info


class RuleVideoSplitter(BaseVideoSplitter):
    """简单规则视频分割器 - MVP版本"""

    def __init__(self, config: Optional[HengLineConfig]):
        super().__init__(config)
        # 简单规则：镜头时长>5秒就拆分
        self.split_threshold = getattr(config, 'duration_split_threshold', 5.5)  # 超过5秒触发分割

    def cut(self, shot_sequence: ShotSequence, parsed_script: ParsedScript) -> FragmentSequence:
        """简单规则分割：镜头时长>5秒就拆分"""
        info(f"开始视频分割，镜头数: {len(shot_sequence.shots)}")

        fragments = []
        current_time = 0.0

        # 设置源信息
        source_info = {
            "shot_count": len(shot_sequence.shots),
            "original_duration": shot_sequence.stats.get("total_duration", 0.0),
            "title": shot_sequence.script_reference.get("title", "")
        }

        # 遍历所有镜头
        for shot in shot_sequence.shots:
            shot_fragments = self.split_shot(shot, current_time, len(fragments))
            fragments.extend(shot_fragments)

            # 更新当前时间
            if shot_fragments:
                current_time = shot_fragments[-1].start_time + shot_fragments[-1].duration

        # 构建序列
        fragment_sequence = FragmentSequence(
            source_info=source_info,
            fragments=fragments
        )

        # 后处理
        return self.post_process(fragment_sequence)

    def split_shot(self, shot: ShotInfo, start_time: float, fragment_offset: int) -> List[VideoFragment]:
        """分割单个镜头"""
        fragments = []

        # 镜头时长≤5秒：直接作为一个片段
        if shot.duration <= self.split_threshold:
            fragment_id = self._generate_fragment_id(fragment_offset)

            fragment = VideoFragment(
                id=fragment_id,
                shot_id=shot.id,
                element_ids=shot.element_ids,
                start_time=start_time,
                duration=shot.duration,
                # description=self._generate_fragment_description(shot),
                description=shot.description,
                continuity_notes={
                    "main_character": shot.main_character,
                    "location": f"场景{shot.scene_id}",
                    "main_action": shot.description
                }
            )
            fragments.append(fragment)

        else:
            # 镜头时长>5秒：需要拆分
            # 简单策略：等分为2-3个片段
            num_segments = min(3, int(shot.duration / 2.5) + 1)  # 确保每个片段≥2.5秒
            segment_duration = shot.duration / num_segments

            for seg_idx in range(num_segments):
                fragment_id = f"frag_{fragment_offset + len(fragments) + 1:03d}_{seg_idx + 1}"

                # 如果是第一个片段，包含所有元素引用
                # 如果是后续片段，只引用部分元素（简化处理）
                element_ids = shot.element_ids if seg_idx == 0 else []

                fragment = VideoFragment(
                    id=fragment_id,
                    shot_id=shot.id,
                    element_ids=element_ids,
                    start_time=start_time + seg_idx * segment_duration,
                    duration=round(segment_duration, 2),
                    description=f"{shot.description} (部分{seg_idx + 1}/{num_segments})",
                    continuity_notes={
                        "main_character": shot.main_character,
                        "location": f"场景{shot.scene_id}",
                        "main_action": shot.description if seg_idx == 0 else "动作延续"
                    },
                    requires_special_attention=(seg_idx > 0)  # 拆分片段需要特殊处理
                )
                fragments.append(fragment)

        return fragments

    def _generate_fragment_description(self, shot: ShotInfo) -> str:
        """生成片段描述"""
        # 简化描述：镜头描述 + 镜头类型
        base_desc = shot.description

        # 添加镜头类型信息
        type_mapping = ShotType.get_type_mapping()

        shot_type_desc = type_mapping.get(shot.shot_type, shot.shot_type.value)

        # if len(base_desc) > 40:
        #     base_desc = base_desc[:37] + "..."

        return f"{shot_type_desc}：{base_desc}"
