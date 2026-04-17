"""
@FileName: base_shot_generator.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/17 22:03
"""
from abc import abstractmethod, ABC
from typing import Optional, Dict, Any

from penshot.neopen.agent.base_models import ElementType
from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript, BaseElement
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotType
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info, warning, error


class BaseShotSegmenter(ABC):
    """分镜拆分器抽象基类"""

    def __init__(self, config: Optional[ShotConfig]):
        self.config = config
        self._initialize()

    def _initialize(self):
        """初始化拆分器"""
        info(f"初始化分镜拆分器: {self.__class__.__name__}")

    @abstractmethod
    def split(self, parsed_script: ParsedScript, repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> ShotSequence:
        """拆分剧本为镜头序列（抽象方法）"""
        pass

    def _post_process(self, shot_sequence: ShotSequence) -> ShotSequence:
        """后处理：填充统计数据等"""
        shots = shot_sequence.shots

        if not shots:
            warning("分镜结果为空")
            return shot_sequence

        # 计算统计数据
        total_duration = sum(shot.duration for shot in shots)
        close_up_count = sum(1 for shot in shots if shot.shot_type == ShotType.CLOSE_UP)
        wide_shot_count = sum(1 for shot in shots if shot.shot_type == ShotType.WIDE_SHOT)
        medium_shot_count = len(shots) - close_up_count - wide_shot_count

        # 更新统计数据
        shot_sequence.stats.update({
            "shot_count": len(shots),
            "total_duration": round(total_duration, 2),
            "avg_shot_duration": round(total_duration / len(shots), 2),
            "close_up_count": close_up_count,
            "wide_shot_count": wide_shot_count,
            "medium_shot_count": medium_shot_count
        })

        # 更新元数据
        shot_sequence.metadata.update({
            "total_shots": len(shots),
            "splitter_type": self.__class__.__name__
        })

        info(f"分镜完成: {len(shots)}个镜头, 总时长{total_duration:.1f}秒")
        return shot_sequence

    def _validate_sequence(self, shot_sequence: ShotSequence) -> bool:
        """验证镜头序列的基本有效性"""
        shots = shot_sequence.shots

        if not shots:
            error("镜头序列为空")
            return False

        # 检查时间连续性
        current_time = 0.0
        for i, shot in enumerate(shots):
            if abs(shot.start_time - current_time) > 0.1:  # 允许0.1秒误差
                warning(f"镜头{i + 1}时间不连续: {shot.start_time} vs {current_time}")

            if shot.duration < self.config.min_shot_duration:
                warning(f"镜头{i + 1}时长过短: {shot.duration}秒")

            if shot.duration > self.config.max_shot_duration:
                warning(f"镜头{i + 1}时长过长: {shot.duration}秒")

            current_time = shot.start_time + shot.duration

        return True

    def _generate_shot_id(self, shot_idx: int) -> str:
        """生成镜头ID"""
        return f"shot_{shot_idx + 1:03d}"

    def _determine_shot_type(self, element: BaseElement) -> ShotType:
        """根据元素类型确定镜头类型（基础规则）"""
        if element.type == ElementType.DIALOGUE:
            return ShotType.CLOSE_UP
        elif element.type == ElementType.SCENE:
            return ShotType.WIDE_SHOT
        else:  # ACTION
            return ShotType.MEDIUM_SHOT
