"""
@FileName: base_video_splitter.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 22:30
"""
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict

from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence
from penshot.neopen.agent.video_splitter.video_splitter_models import FragmentSequence
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info, warning, error, debug


class BaseVideoSplitter(ABC):
    """视频分割器抽象基类"""

    def __init__(self, config: Optional[ShotConfig] = None):
        self.config = config
        self._initialize()

    def _initialize(self):
        """初始化分割器"""
        debug(f"初始化视频分割器: {self.__class__.__name__}")

    @abstractmethod
    def cut(self, shot_sequence: ShotSequence, parsed_script: ParsedScript,
            repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> FragmentSequence:
        """将镜头序列分割为片段（抽象方法）"""
        pass

    def post_process(self, fragment_sequence: FragmentSequence) -> FragmentSequence:
        """后处理：填充统计数据等"""
        fragments = fragment_sequence.fragments

        if not fragments:
            warning("分割结果为空")
            return fragment_sequence

        # 计算统计数据
        total_duration = sum(frag.duration for frag in fragments)

        # 计算拆分比例（估算）
        original_shot_count = fragment_sequence.source_info.get("shot_count", 0)
        fragments_split = sum(1 for frag in fragments
                              if len(frag.element_ids) > 0)  # 简化估算

        fragment_sequence.stats.update({
            "fragment_count": len(fragments),
            "total_duration": round(total_duration, 2),
            "avg_duration": round(total_duration / len(fragments), 2) if fragments else 0,
            "fragments_under_5s": sum(1 for frag in fragments if frag.duration <= 5.0),
            "fragments_split": fragments_split,
            "split_ratio": round(fragments_split / len(fragments), 2) if fragments else 0
        })

        # 更新元数据
        fragment_sequence.metadata.update({
            "total_fragments": len(fragments),
            "cutter_type": self.__class__.__name__
        })

        info(f"分割完成: {len(fragments)}个片段, 总时长{total_duration:.2f}秒")
        return fragment_sequence

    def validate_sequence(self, fragment_sequence: FragmentSequence) -> bool:
        """验证片段序列的基本有效性"""
        fragments = fragment_sequence.fragments

        if not fragments:
            error("片段序列为空")
            return False

        # 检查时长限制
        for i, frag in enumerate(fragments):
            if frag.duration > self.config.duration_split_threshold:
                error(f"片段{i + 1}超时: {frag.duration}秒 > {self.config.duration_split_threshold}秒")
                return False

            if frag.duration < self.config.min_fragment_duration:
                warning(f"片段{i + 1}时长过短: {frag.duration}秒")

        # 检查时间连续性
        current_time = 0.0
        for i, frag in enumerate(fragments):
            if abs(frag.start_time - current_time) > 0.1:  # 允许0.1秒误差
                warning(f"片段{i + 1}时间不连续: {frag.start_time} vs {current_time}")
            current_time = frag.start_time + frag.duration

        return True

    def _generate_fragment_id(self, fragment_idx: int) -> str:
        """生成片段ID"""
        return f"frag_{fragment_idx + 1:03d}"
