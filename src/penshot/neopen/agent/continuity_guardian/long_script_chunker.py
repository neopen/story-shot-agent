"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: long_script_chunker.py
@Description: 超长剧本分块处理器
@Author: NeoPen
@Time: 2026/4/28 0:21
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ScriptChunk:
    """剧本块"""
    chunk_id: int
    start_scene: int
    end_scene: int
    scenes: List[Any]  # SceneInfo 对象列表
    estimated_duration: float = 0.0

    # 块间状态传递
    entry_character_states: Dict[str, Dict] = field(default_factory=dict)
    exit_character_states: Dict[str, Dict] = field(default_factory=dict)

    # 连续性锚点
    continuity_anchors: Dict[str, Any] = field(default_factory=dict)


class LongScriptChunker:
    """超长剧本分块器"""

    def __init__(self, max_scenes_per_chunk: int = 30,
                 max_duration_per_chunk: float = 180.0,  # 3分钟
                 overlap_scenes: int = 3):
        self.max_scenes_per_chunk = max_scenes_per_chunk
        self.max_duration_per_chunk = max_duration_per_chunk
        self.overlap_scenes = overlap_scenes

    def chunk_script(self, parsed_script) -> List[ScriptChunk]:
        """
        将剧本分块

        策略：
        1. 按场景数分块
        2. 保持场景边界（不断开场景内部）
        3. 块间有重叠场景用于连续性检查
        """
        scenes = parsed_script.scenes
        total_scenes = len(scenes)

        if total_scenes <= self.max_scenes_per_chunk:
            return [self._create_chunk(0, scenes, 0, total_scenes - 1)]

        chunks = []
        chunk_scenes = []
        current_duration = 0.0

        for i, scene in enumerate(scenes):
            scene_duration = self._estimate_scene_duration(scene)

            # 检查是否需要开始新块
            if (len(chunk_scenes) >= self.max_scenes_per_chunk or
                    current_duration + scene_duration > self.max_duration_per_chunk):
                if chunk_scenes:
                    chunks.append(self._create_chunk(
                        len(chunks),
                        chunk_scenes,
                        chunk_scenes[0].number - 1,
                        chunk_scenes[-1].number - 1
                    ))
                    # 保留重叠场景
                    overlap = chunk_scenes[-self.overlap_scenes:] if self.overlap_scenes > 0 else []
                    chunk_scenes = overlap
                    current_duration = sum(self._estimate_scene_duration(s) for s in chunk_scenes)

            chunk_scenes.append(scene)
            current_duration += scene_duration

        # 最后一个块
        if chunk_scenes:
            chunks.append(self._create_chunk(
                len(chunks),
                chunk_scenes,
                chunk_scenes[0].number - 1,
                chunk_scenes[-1].number - 1
            ))

        return chunks

    def _estimate_scene_duration(self, scene) -> float:
        """估算场景时长（秒）"""
        # 基于元素数量估算
        element_count = len(getattr(scene, 'elements', []))
        return max(10.0, element_count * 4.0)  # 每个元素约4秒

    def _create_chunk(self, chunk_id: int, scenes: List,
                      start_scene: int, end_scene: int) -> ScriptChunk:
        """创建剧本块"""
        return ScriptChunk(
            chunk_id=chunk_id,
            start_scene=start_scene,
            end_scene=end_scene,
            scenes=scenes,
            estimated_duration=sum(self._estimate_scene_duration(s) for s in scenes)
        )
