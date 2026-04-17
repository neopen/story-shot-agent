"""
@FileName: estimator_models.py
@Description: 时长估算相关模型
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/19
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class CorrectionLevel(str, Enum):
    MINOR = "minor"  # 微调 (< 10%)
    MODERATE = "moderate"  # 中等调整 (10-30%)
    MAJOR = "major"  # 重大调整 (> 30%)


class CorrectionReason(str, Enum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    EMOTIONAL = "emotional"
    PACING = "pacing"
    CONSISTENCY = "consistency"


@dataclass
class CorrectionRecord:
    """修正记录"""
    shot_id: str
    original_duration: float
    corrected_duration: float
    correction_level: str
    reasons: List[str]
    rules_applied: List[str]

    def to_dict(self) -> Dict:
        return {
            "shot_id": self.shot_id,
            "original_duration": self.original_duration,
            "corrected_duration": self.corrected_duration,
            "change_percent": round((self.corrected_duration - self.original_duration) / self.original_duration * 100, 2),
            "correction_level": self.correction_level,
            "reasons": self.reasons,
            "rules_applied": self.rules_applied
        }


class IntensityLevel(str, Enum):
    """强度级别枚举"""
    VERY_LOW = "very_low"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    VERY_HIGH = "very_high"