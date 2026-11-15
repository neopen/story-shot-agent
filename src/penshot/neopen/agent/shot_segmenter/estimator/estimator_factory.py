"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: estimator_factory.py
@Description: 时长估算器工厂
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19
"""
from typing import Any, Dict, List, Optional

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.action_estimator import ActionDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.action_nodes import compute_duration
from penshot.neopen.agent.shot_segmenter.estimator.base_estimator import BaseDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.dialogue_estimator import DialogueDurationEstimator
from penshot.neopen.agent.shot_segmenter.estimator.scene_estimator import SceneDurationEstimator
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotType, ShotSequence
from penshot.logger import debug, info, error, warning
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
        """估算整个序列

        主路径使用动作节点确定性公式（FR-075/FR-076）；按镜头类型分派的
        估算器只在镜头缺少描述时作为回退，其结果同时作为“解析元素推算值”
        写入统计报告（FR-078）。

        Args:
            sequence: 待估算的镜头序列
            script: 剧本解析结果

        Returns:
            写入时长与统计报告的镜头序列
        """
        debug(f"开始估算镜头序列，共{len(sequence.shots)}个镜头")

        element_durations: List[float] = []
        duration_sources: List[str] = []
        total_shots = len(sequence.shots)

        for i, shot in enumerate(sequence.shots):
            element_duration = cls._estimate_element_duration(shot, script, total_shots)
            element_durations.append(element_duration or 0.0)

            if shot.description.strip():
                shot.duration = compute_duration(shot, script)
                duration_sources.append("action_nodes")
            elif element_duration is not None:
                shot.duration = round(element_duration, 2)
                duration_sources.append("fallback_estimator")
                warning(f"镜头 {shot.id} 缺少描述，回退到元素估算时长 {shot.duration}s")
            else:
                shot.duration = compute_duration(shot, script)
                duration_sources.append("action_nodes")
                warning(f"镜头 {shot.id} 缺少描述且元素估算失败，使用公式下限 {shot.duration}s")

            debug(f"镜头 {i + 1}: {shot.shot_type.value} - {shot.duration}s ({duration_sources[-1]})")

        # 更新时间戳和统计数据
        current_time = 0.0
        for shot in sequence.shots:
            shot.start_time = current_time
            current_time += shot.duration

        total_duration = round(sum(s.duration for s in sequence.shots), 2)
        target_duration = cls._resolve_target_duration(script)
        duration_delta = (
            None if target_duration is None else round(target_duration - total_duration, 2)
        )

        sequence.stats = cls._update_stats(
            sequence,
            element_duration=round(sum(element_durations), 2),
            target_duration=target_duration,
            duration_delta=duration_delta,
            duration_source=cls._resolve_duration_source(duration_sources),
        )

        if duration_delta is not None and duration_delta > 0:
            warning(
                f"总时长不足：目标 {target_duration}s，实际 {total_duration}s，"
                f"差 {duration_delta}s"
            )

        info(f"估算完成，总时长: {sequence.stats['total_duration']}s")
        return sequence

    @classmethod
    def _estimate_element_duration(
        cls,
        shot: ShotInfo,
        script: ParsedScript,
        total_shots: int,
    ) -> Optional[float]:
        """用类型分派估算器计算解析元素推算时长，失败时返回 None"""
        try:
            estimator = cls.get_estimator(shot.shot_type)

            context = estimator.context
            context.update_from_shot(shot, script)
            context.total_shots = total_shots

            return estimator.estimate_shot(shot, script)
        except Exception as e:
            error(f"估算镜头 {shot.id} 元素时长失败: {e}")
            print_log_exception()
            return None

    @staticmethod
    def _resolve_target_duration(script: Optional[ParsedScript]) -> Optional[float]:
        """读取剧本显式目标时长；未声明或非法时返回 None（FR-079）"""
        if script is None:
            return None

        for container in (getattr(script, "metadata", None), getattr(script, "stats", None)):
            if not container or "target_duration" not in container:
                continue
            value = container["target_duration"]
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                warning(f"忽略非法目标时长: {value!r}")
        return None

    @staticmethod
    def _resolve_duration_source(sources: List[str]) -> str:
        """汇总本序列实际使用的时长来源"""
        unique = set(sources)
        if not unique or unique == {"action_nodes"}:
            return "action_nodes"
        if unique == {"fallback_estimator"}:
            return "fallback_estimator"
        return "mixed"

    @classmethod
    def _update_stats(
        cls,
        sequence: ShotSequence,
        *,
        element_duration: Optional[float] = None,
        target_duration: Optional[float] = None,
        duration_delta: Optional[float] = None,
        duration_source: str = "action_nodes",
    ) -> Dict:
        """更新统计数据并写入总时长报告字段"""
        stats: Dict[str, Any] = {
            "shot_count": len(sequence.shots),
            "total_duration": round(sum(s.duration for s in sequence.shots), 2),
            "avg_shot_duration": 0.0,
            "close_up_count": 0,
            "wide_shot_count": 0,
            "medium_shot_count": 0,
            "element_duration": element_duration,
            "target_duration": target_duration,
            "duration_delta": duration_delta,
            "duration_source": duration_source,
        }

        if stats["shot_count"] > 0:
            stats["avg_shot_duration"] = round(stats["total_duration"] / stats["shot_count"], 2)

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
