"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: llm_video_splitter.py
@Description: 
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 22:30
"""
from typing import List, Optional, Dict, Any

from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from penshot.neopen.agent.video_splitter.base_video_splitter import BaseVideoSplitter
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence, VideoFragment
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info


class RuleVideoSplitter(BaseVideoSplitter):
    """简单规则视频分割器 - MVP版本"""

    def __init__(self, config: Optional[ShotConfig]):
        super().__init__(config)
        # 简单规则：镜头时长>5秒就拆分
        self.split_threshold = getattr(config, 'duration_split_threshold', 5.5)  # 超过5秒触发分割

    def cut(self, shot_sequence: ShotSequence, parsed_script: ParsedScript,
            repair_params: Optional[QualityRepairParams],
            historical_context: Optional[Dict[str, Any]]) -> FragmentSequence:
        """修复版：正确统计分割情况"""
        info(f"开始视频分割，镜头数: {len(shot_sequence.shots)}")

        fragments = []
        current_time = 0.0

        # 统计变量
        actual_split_shots = 0  # 实际被分割的镜头数

        source_info = {
            "shot_count": len(shot_sequence.shots),
            "original_duration": shot_sequence.stats.get("total_duration", 0.0),
            "title": shot_sequence.script_reference.get("title", "")
        }

        for shot_idx, shot in enumerate(shot_sequence.shots):
            shot_fragments = self.split_shot(shot, current_time, len(fragments))
            fragments.extend(shot_fragments)

            # 统计实际分割情况
            if len(shot_fragments) > 1:
                actual_split_shots += 1

            if shot_fragments:
                current_time = shot_fragments[-1].start_time + shot_fragments[-1].duration

        # 修复统计数据
        fragment_count = len(fragments)
        total_duration = sum(f.duration for f in fragments)

        fragment_sequence = FragmentSequence(
            source_info=source_info,
            fragments=fragments,
            metadata={
                "split_method": "rule",
                "actual_split_shots": actual_split_shots,  # 新增
                "total_shots": len(shot_sequence.shots),  # 新增
                "split_ratio": round(actual_split_shots / len(shot_sequence.shots), 2) if shot_sequence.shots else 0,
                "total_fragments": fragment_count,
                "average_duration": round(total_duration / fragment_count, 2) if fragment_count else 0
            }
        )

        # 更新stats
        fragment_sequence.stats.update({
            "fragment_count": fragment_count,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / fragment_count, 2) if fragment_count else 0,
            "fragments_split": actual_split_shots,
            "split_ratio": round(actual_split_shots / len(shot_sequence.shots), 2) if shot_sequence.shots else 0
        })

        info(f"分割统计: 总镜头{len(shot_sequence.shots)}个, 实际分割{actual_split_shots}个, 输出片段{fragment_count}个")

        return self.post_process(fragment_sequence)

    def split_shot(self, shot: ShotInfo, start_time: float, fragment_offset: int) -> List[VideoFragment]:
        """分割单个镜头（修复版）"""
        fragments = []

        if shot.duration <= self.split_threshold:
            # 不分割，直接作为一个片段
            fragment_id = self._generate_fragment_id(fragment_offset)

            fragment = VideoFragment(
                id=fragment_id,
                shot_id=shot.id,
                element_ids=shot.element_ids,
                start_time=start_time,
                duration=shot.duration,
                description=shot.description,
                continuity_notes={
                    "main_character": shot.main_character,
                    "location": f"场景{shot.scene_id}",
                    "main_action": shot.description,
                    "split_type": "none"  # 标记未分割
                },
                metadata={
                    "split_by": "rule",
                    "is_split": False,
                    "original_shot": shot.id
                }
            )
            fragments.append(fragment)
        else:
            # 需要分割
            num_segments = min(3, int(shot.duration / 2.5) + 1)
            segment_duration = shot.duration / num_segments

            for seg_idx in range(num_segments):
                fragment_id = self._generate_fragment_id(fragment_offset + seg_idx)
                if seg_idx > 0:
                    fragment_id = f"{fragment_id}_s{seg_idx + 1}"

                fragment = VideoFragment(
                    id=fragment_id,
                    shot_id=shot.id,
                    element_ids=shot.element_ids if seg_idx == 0 else [],
                    start_time=round(start_time + seg_idx * segment_duration, 2),
                    duration=round(segment_duration, 2),
                    description=f"{shot.description} (部分{seg_idx + 1}/{num_segments})",
                    continuity_notes={
                        "main_character": shot.main_character,
                        "location": f"场景{shot.scene_id}",
                        "main_action": shot.description if seg_idx == 0 else "动作延续",
                        "split_type": "split",
                        "part": f"{seg_idx + 1}/{num_segments}"
                    },
                    metadata={
                        "split_by": "rule",
                        "is_split": True,
                        "original_shot": shot.id,
                        "segment_index": seg_idx,
                        "total_segments": num_segments
                    },
                    requires_special_attention=(seg_idx > 0)
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
