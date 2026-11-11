"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: transition_shots.py
@Description: 场景边界过渡镜头的确定性插入
@Author: neopen
@GitHub: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

from typing import List

from penshot.logger import info
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
    ShotType,
)


def choose_transition_shot_type(adjacent_type: ShotType) -> ShotType:
    """选择与相邻镜头不同的过渡景别，形成视觉切换提示"""
    if adjacent_type in (
        ShotType.WIDE_SHOT,
        ShotType.LONG_SHOT,
        ShotType.PANORAMA,
    ):
        return ShotType.CLOSE_UP
    return ShotType.WIDE_SHOT


def insert_transition_shots(shot_sequence: ShotSequence) -> ShotSequence:
    """在缺乏视觉提示的场景边界插入过渡镜头

    判定条件与连续性检查保持一致：相邻镜头跨场景、均非过渡镜头、
    且景别相同。修复是确定性的，因此不会像重新生成分镜那样反复回到
    同一问题。
    """
    shots = shot_sequence.shots
    if len(shots) < 2:
        return shot_sequence

    new_shots: List[ShotInfo] = []
    inserted = 0

    for index, shot in enumerate(shots):
        if index > 0:
            prev_shot = shots[index - 1]
            if (
                prev_shot.scene_id != shot.scene_id
                and not prev_shot.is_transition
                and not shot.is_transition
                and prev_shot.shot_type == shot.shot_type
            ):
                transition_type = choose_transition_shot_type(prev_shot.shot_type)
                type_desc = ShotType.get_type_mapping().get(transition_type, "过渡画面")
                new_shots.append(
                    ShotInfo(
                        id=f"{shot.id}_trans",
                        scene_id=shot.scene_id,
                        description=(
                            f"过渡镜头：{prev_shot.scene_id} 到 {shot.scene_id}"
                            f" 的场景衔接，{type_desc}"
                        ),
                        duration=1.2,
                        shot_type=transition_type,
                        emotion=shot.emotion,
                        main_character=shot.main_character or prev_shot.main_character,
                        confidence=0.6,
                        is_transition=True,
                    )
                )
                inserted += 1
        new_shots.append(shot)

    if inserted == 0:
        return shot_sequence

    current_time = 0.0
    for shot in new_shots:
        shot.start_time = round(current_time, 2)
        current_time += shot.duration

    shot_sequence.shots = new_shots
    total_duration = sum(s.duration for s in new_shots)
    shot_sequence.stats.update(
        {
            "shot_count": len(new_shots),
            "total_duration": round(total_duration, 2),
            "avg_shot_duration": round(total_duration / len(new_shots), 2),
            "close_up_count": sum(
                1 for s in new_shots if s.shot_type == ShotType.CLOSE_UP
            ),
            "wide_shot_count": sum(
                1 for s in new_shots if s.shot_type == ShotType.WIDE_SHOT
            ),
            "medium_shot_count": sum(
                1 for s in new_shots if s.shot_type == ShotType.MEDIUM_SHOT
            ),
        }
    )
    info(f"连续性修复：在{inserted}个场景边界插入过渡镜头")
    return shot_sequence
