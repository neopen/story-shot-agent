"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: video_assembler_models.py
@Description: 视频组装合成模型
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19 23:02
"""
import time
from datetime import datetime
from typing import List, Any, Dict

from pydantic import Field, BaseModel

from penshot.neopen.agent.base_models import AgentMode


class VideoFragment(BaseModel):
    """MVP视频片段模型"""
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "split_by": AgentMode.RULE.value,
            "timestamp": time.time()
        }
    )

    id: str = Field(..., description="片段唯一ID，格式：frag_001")

    # 核心引用信息
    shot_id: str = Field(..., description="所属镜头ID")
    element_ids: List[str] = Field(
        default_factory=list,
        description="包含的剧本元素ID列表"
    )

    # 时间信息
    start_time: float = Field(default=0.0, description="全局开始时间（秒）")
    duration: float = Field(
        default=3.0,
        ge=1,
        le=10.0,
        description="片段时长（秒），强制≤10秒"
    )

    # 内容信息（极简）
    description: str = Field(
        default="",
        description="片段内容简洁描述"
    )

    # 极简的连续性标记
    continuity_notes: Dict[str, Any] = Field(
        default_factory=lambda: {
            "main_character": None,
            "location": None,
            "main_action": None
        }
    )

    # MVP扩展标记（可选）
    requires_special_attention: bool = Field(
        default=False,
        description="需要特殊处理的标记"
    )


class FragmentSequence(BaseModel):
    """MVP片段序列输出"""

    # 极简元数据
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "generated_at": datetime.now().isoformat(),
            "version": "mvp_1.0",
            "max_fragment_duration": 5.0
        }
    )

    # 源镜头信息（简化）
    source_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "shot_count": 0,
            "original_duration": 0.0,
            "title": ""
        }
    )

    # 核心片段列表
    fragments: List[VideoFragment] = Field(
        default_factory=list,
        description="按时间顺序排列的片段列表"
    )

    # 极简统计数据
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "fragment_count": 0,
            "total_duration": 0.0,
            "avg_duration": 0.0,
            "fragments_under_5s": 0,
            "fragments_split": 0,
            "split_ratio": 0.0
        }
    )

    def to_dict(self):
        return self.model_dump()

    def update_stats(self):
        """修复统计计算"""
        fragment_count = len(self.fragments)

        if fragment_count == 0:
            return

        total_duration = sum(f.duration for f in self.fragments)

        # 正确计算实际分割的镜头数
        split_shots = set()
        for f in self.fragments:
            if hasattr(f, 'metadata') and f.metadata:
                if f.metadata.get('is_split', False):
                    original_shot = f.metadata.get('original_shot')
                    if original_shot:
                        split_shots.add(original_shot)

        actual_split = len(split_shots)
        total_shots = self.source_info.get('shot_count', fragment_count)

        self.stats = {
            "fragment_count": fragment_count,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / fragment_count, 2),
            "fragments_under_5s": sum(1 for f in self.fragments if f.duration <= 5.0),
            "fragments_split": actual_split,  # 修复：使用实际分割数
            "split_ratio": round(actual_split / total_shots, 2) if total_shots > 0 else 0
        }