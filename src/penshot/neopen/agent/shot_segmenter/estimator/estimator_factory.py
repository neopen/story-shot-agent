"""
@FileName: estimator_factory.py
@Description: 时长估算器工厂
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/19
"""
from typing import Dict

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.action_estimator import ActionDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.base_estimator import BaseDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.dialogue_estimator import DialogueDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.scene_estimator import SceneDurationEstimator
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotType, ShotSequence
from penshot.logger import debug, info, error
from penshot.utils.log_utils import print_log_exception


class DurationEstimatorFactory:
    """时长估算器工厂"""

    _estimators = {}

    @classmethod
    def get_estimator(cls, shot_type: ShotType) -> BaseDurationEstimator:
        """根据镜头类型获取估算器"""
        estimator_key = shot_type.value

        if estimator_key not in cls._estimators:
            cls._estimators[estimator_key] = cls._create_estimator(shot_type)

        return cls._estimators[estimator_key]

    @classmethod
    def _create_estimator(cls, shot_type: ShotType) -> BaseDurationEstimator:
        """创建估算器"""
        if shot_type == ShotType.CLOSE_UP:
            return DialogueDurationEstimator()
        elif shot_type == ShotType.WIDE_SHOT:
            return SceneDurationEstimator()
        else:  # MEDIUM_SHOT
            return ActionDurationEstimator()

    @classmethod
    def estimate_shot(cls, shot: ShotInfo, script: ParsedScript) -> float:
        """估算单个镜头时长"""
        estimator = cls.get_estimator(shot.shot_type)
        return estimator.estimate_shot(shot, script)

    @classmethod
    def estimate_sequence(cls, sequence: ShotSequence, script: ParsedScript) -> ShotSequence:
        """估算整个序列"""
        info(f"开始估算镜头序列，共{len(sequence.shots)}个镜头")

        for i, shot in enumerate(sequence.shots):
            try:
                # 获取估算器
                estimator = cls.get_estimator(shot.shot_type)

                # 设置上下文
                context = estimator.context
                context.update_from_shot(shot, script)
                context.total_shots = len(sequence.shots)

                # 估算时长
                shot.duration = estimator.estimate_shot(shot, script)

                debug(f"镜头 {i + 1}: {shot.shot_type.value} - {shot.duration}s")

            except Exception as e:
                error(f"估算镜头 {shot.id} 失败: {e}")
                print_log_exception()
                # shot.duration = 3.0  # 默认时长

        # 更新时间戳和统计数据
        current_time = 0.0
        for shot in sequence.shots:
            shot.start_time = current_time
            current_time += shot.duration

        sequence.stats = cls._update_stats(sequence)

        info(f"估算完成，总时长: {sequence.stats['total_duration']}s")
        return sequence

    @classmethod
    def _update_stats(cls, sequence: ShotSequence) -> Dict:
        """更新统计数据"""
        stats = {
            "shot_count": len(sequence.shots),
            "total_duration": sum(s.duration for s in sequence.shots),
            "avg_shot_duration": 0.0,
            "close_up_count": 0,
            "wide_shot_count": 0,
            "medium_shot_count": 0
        }

        if stats["shot_count"] > 0:
            stats["avg_shot_duration"] = stats["total_duration"] / stats["shot_count"]

        for shot in sequence.shots:
            if shot.shot_type == ShotType.CLOSE_UP:
                stats["close_up_count"] += 1
            elif shot.shot_type == ShotType.WIDE_SHOT:
                stats["wide_shot_count"] += 1
            else:
                stats["medium_shot_count"] += 1

        return stats


# 单例实例
estimator_factory = DurationEstimatorFactory()
