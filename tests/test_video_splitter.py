"""
@FileName: test_video_splitter.py
@Description: 
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/26 23:15
"""
from hengshot.hengline.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from hengshot.hengline.agent.video_splitter.video_splitter_models import FragmentSequence


# MVP分段核心逻辑（伪代码）
def mvp_cut_shots(shot_sequence: ShotSequence) -> FragmentSequence:
    """MVP视频分割核心逻辑"""
    fragments = []

    for shot in shot_sequence.shots:
        if shot.duration <= 5.0:
            # 直接使用镜头作为一个片段
            fragment = create_fragment(shot)
            fragments.append(fragment)
        else:
            # 简单等分拆分
            # 例如8秒镜头 -> 拆为4秒+4秒两个片段
            num_parts = 2  # MVP固定拆为2部分
            part_duration = shot.duration / num_parts

            for i in range(num_parts):
                fragment = create_partial_fragment(shot, i, num_parts, part_duration)
                fragments.append(fragment)

    return FragmentSequence(fragments=fragments)