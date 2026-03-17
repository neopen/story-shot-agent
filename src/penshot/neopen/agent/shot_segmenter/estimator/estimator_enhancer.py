"""
@FileName: estimator_enhancer.py
@Description: 时长估算增强器（后处理优化）
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/19
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.estimator_models import CorrectionRecord, CorrectionReason, CorrectionLevel
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotSequence, ShotInfo, ShotType
from penshot.logger import debug, info


class DurationEnhancer:
    """时长估算增强器"""

    def __init__(self):
        self._load_rules()
        self.correction_history = []

    def _load_rules(self):
        """加载增强规则"""
        # 镜头类型基准
        self.shot_baselines = {
            ShotType.CLOSE_UP: {"min": 1.5, "max": 4.5, "optimal": 2.5},
            ShotType.MEDIUM_SHOT: {"min": 2.0, "max": 5.0, "optimal": 3.0},
            ShotType.WIDE_SHOT: {"min": 3.0, "max": 6.0, "optimal": 4.0}
        }

        # 情感镜头延长
        self.emotional_boost = 1.3

        # 节奏规则
        self.pacing_rules = {
            "opening": 1.2,  # 开场镜头略长
            "climax": 1.3,  # 高潮镜头延长
            "ending": 1.2,  # 结尾镜头略长
            "transition": 0.8  # 过渡镜头加快
        }

    def enhance(self,
                sequence: ShotSequence,
                script: ParsedScript,
                base_confidence: float = 0.7) -> Tuple[ShotSequence, List[CorrectionRecord]]:
        """增强时长估算"""
        debug("开始时长增强")

        # 创建副本
        enhanced = sequence.model_copy(deep=True)
        corrections = []

        # 1. 逐镜头优化
        for i, shot in enumerate(enhanced.shots):
            correction = self._enhance_shot(shot, script, i, len(enhanced.shots))
            if correction:
                corrections.append(correction)

        # 2. 整体一致性检查
        enhanced = self._check_consistency(enhanced)

        # 3. 更新时间戳和统计
        current_time = 0.0
        for shot in enhanced.shots:
            shot.start_time = current_time
            current_time += shot.duration

        enhanced.stats = self._update_stats(enhanced)

        # 记录历史
        self.correction_history.append({
            "timestamp": datetime.now().isoformat(),
            "correction_count": len(corrections),
            "total_change": sum(abs(c.corrected_duration - c.original_duration) for c in corrections)
        })

        info(f"增强完成: 修正{len(corrections)}个镜头")
        return enhanced, corrections

    def _enhance_shot(self,
                      shot: ShotInfo,
                      script: ParsedScript,
                      position: int,
                      total_shots: int) -> Optional[CorrectionRecord]:
        """增强单个镜头"""
        original = shot.duration
        new_duration = original
        reasons = []
        rules = []

        # 1. 检查是否在合理范围内
        baseline = self.shot_baselines.get(shot.shot_type)
        if baseline:
            if new_duration < baseline["min"]:
                new_duration = baseline["min"]
                reasons.append(CorrectionReason.TOO_SHORT)
                rules.append("min_duration")
            elif new_duration > baseline["max"]:
                new_duration = baseline["max"]
                reasons.append(CorrectionReason.TOO_LONG)
                rules.append("max_duration")

        # 2. 情感镜头调整
        scene_mood = self._get_scene_mood(shot, script)
        if scene_mood in ["悲伤", "激动", "紧张"] and shot.shot_type == ShotType.CLOSE_UP:
            if new_duration < 3.0:
                new_duration = 3.0
                reasons.append(CorrectionReason.EMOTIONAL)
                rules.append("emotional_closeup")

        # 3. 节奏调整
        if position == 0:  # 开场镜头
            if new_duration < 3.0:
                new_duration *= self.pacing_rules["opening"]
                reasons.append(CorrectionReason.PACING)
                rules.append("scene_open")
        elif position == total_shots - 1:  # 结尾镜头
            if new_duration < 3.0:
                new_duration *= self.pacing_rules["ending"]
                reasons.append(CorrectionReason.PACING)
                rules.append("scene_close")

        # 如果没有变化，返回None
        if abs(new_duration - original) < 0.01:
            return None

        # 确定修正级别
        change_percent = abs(new_duration - original) / original
        if change_percent > 0.3:
            level = CorrectionLevel.MAJOR
        elif change_percent > 0.1:
            level = CorrectionLevel.MODERATE
        else:
            level = CorrectionLevel.MINOR

        # 更新镜头
        shot.duration = round(new_duration, 2)

        return CorrectionRecord(
            shot_id=shot.id,
            original_duration=original,
            corrected_duration=shot.duration,
            correction_level=level,
            reasons=reasons,
            rules_applied=rules
        )

    def _check_consistency(self, sequence: ShotSequence) -> ShotSequence:
        """检查一致性"""
        # 1. 连续相同类型镜头时长应有变化
        for i in range(1, len(sequence.shots)):
            prev = sequence.shots[i - 1]
            curr = sequence.shots[i]

            if prev.shot_type == curr.shot_type:
                if abs(prev.duration - curr.duration) < 0.3:
                    curr.duration = prev.duration + 0.3

        return sequence

    def _get_scene_mood(self, shot: ShotInfo, script: ParsedScript) -> str:
        """获取场景情绪"""
        for scene in script.scenes:
            if scene.id == shot.scene_id:
                if scene.audio_context:
                    return scene.audio_context.atmosphere
        return "neutral"

    def _update_stats(self, sequence: ShotSequence) -> Dict:
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
