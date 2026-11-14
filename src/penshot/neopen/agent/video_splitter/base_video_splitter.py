"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: base_video_splitter.py
@Description: 
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/26 22:30
"""
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List, Tuple

from penshot.neopen.agent.quality_auditor.quality_auditor_models import QualityRepairParams
from penshot.neopen.agent.script_parser.script_parser_models import ParsedScript
from penshot.neopen.agent.shot_segmenter.estimator.action_nodes import (
    compute_duration_from_text,
    count_dialogue_chars_by_elements,
    count_text_dialogue_chars,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import ShotInfo, ShotSequence
from penshot.neopen.agent.video_splitter.fragment_dedupe import (
    ACTION_RESPLIT,
    ACTION_TRUNCATE,
    DuplicateCandidate,
    find_duplicate_candidates,
    merge_fragments,
    resplit_duplicate_pair,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.shot_config import ShotConfig
from penshot.logger import info, warning, error, debug

# FR-076：片段时长下限，独立于 ShotConfig 的历史默认值
FRAGMENT_MIN_DURATION = 2.5


class BaseVideoSplitter(ABC):
    """视频分割器抽象基类"""

    def __init__(self, config: ShotConfig):
        self.config = config
        self._initialize()

    def _initialize(self) -> None:
        """初始化分割器"""
        debug(f"初始化视频分割器: {self.__class__.__name__}")

    @abstractmethod
    def cut(self, shot_sequence: ShotSequence, parsed_script: ParsedScript,
            repair_params: Optional[QualityRepairParams], historical_context: Optional[Dict[str, Any]]) -> FragmentSequence:
        """将镜头序列分割为片段（抽象方法）"""
        pass

    def post_process(
        self,
        fragment_sequence: FragmentSequence,
        shot_sequence: Optional[ShotSequence] = None,
        parsed_script: Optional[ParsedScript] = None,
    ) -> FragmentSequence:
        """后处理：统一时长、消除同镜头重复、重编号并填充统计"""
        fragments = fragment_sequence.fragments

        if not fragments:
            warning("分割结果为空")
            return fragment_sequence

        # FR-075/076：先统一时长口径，再去重，保证合并时长为两者之和
        self._normalize_fragment_durations(fragments, parsed_script)
        self._reflow_timeline(fragments)

        dedupe_report: Optional[Dict[str, Any]] = None
        if shot_sequence is not None and shot_sequence.shots:
            fragments, dedupe_report = self._apply_dedupe(
                fragments, shot_sequence.shots
            )
            fragment_sequence.fragments = fragments
            fragment_sequence.metadata["dedupe_report"] = dedupe_report
            self._reflow_timeline(fragments)

        fragment_sequence.metadata["fragment_id_map"] = self._renumber_fragments(
            fragments
        )

        total_duration = sum(frag.duration for frag in fragments)

        fragment_sequence.stats.update(
            {
                "fragment_count": len(fragments),
                "total_duration": round(total_duration, 2),
                "avg_duration": round(total_duration / len(fragments), 2),
                "fragments_under_5s": sum(
                    1 for frag in fragments if frag.duration <= 5.0
                ),
            }
        )

        fragment_sequence.metadata.update(
            {
                "total_fragments": len(fragments),
                "cutter_type": self.__class__.__name__,
                "average_duration": round(total_duration / len(fragments), 2),
                "dedupe_applied": dedupe_report is not None,
            }
        )

        fragment_sequence.update_stats()
        self._sync_split_stats(fragment_sequence)

        info(f"分割完成: {len(fragments)}个片段, 总时长{total_duration:.2f}秒")
        return fragment_sequence

    def _normalize_fragment_durations(
        self,
        fragments: List[VideoFragment],
        parsed_script: Optional[ParsedScript],
    ) -> None:
        """按动作复杂度重算片段时长（FR-075/FR-076）"""
        max_duration = getattr(self.config, "max_fragment_duration", 5.0)
        for fragment in fragments:
            quoted_chars = count_text_dialogue_chars(fragment.description)
            element_chars = count_dialogue_chars_by_elements(
                fragment.element_ids, parsed_script
            )
            fragment.duration = compute_duration_from_text(
                fragment.description,
                dialogue_chars=max(quoted_chars, element_chars),
                max_duration=max_duration,
                min_duration=FRAGMENT_MIN_DURATION,
            )

    def _apply_dedupe(
        self,
        fragments: List[VideoFragment],
        shots: List[ShotInfo],
    ) -> Tuple[List[VideoFragment], Dict[str, Any]]:
        """消除同一镜头内的疑似重复片段（FR-070~FR-074）

        跨镜头候选只记录不处理，避免把相邻但内容不同的独立镜头合并。
        """
        candidates = find_duplicate_candidates(fragments, shots)
        shot_lookup = {shot.id: shot for shot in shots}
        max_duration = getattr(self.config, "max_fragment_duration", 5.0)

        eligible: Dict[Tuple[int, int], DuplicateCandidate] = {}
        skipped: List[Dict[str, Any]] = []
        for candidate in candidates:
            previous = fragments[candidate.prev_index]
            current = fragments[candidate.index]
            if previous.shot_id != current.shot_id:
                skipped.append({**candidate.to_dict(), "reason": "cross_shot"})
                continue
            eligible[(candidate.prev_index, candidate.index)] = candidate

        operations: List[Dict[str, Any]] = []
        result: List[VideoFragment] = []
        index = 0
        while index < len(fragments):
            pair_candidate = eligible.get((index, index + 1))
            if pair_candidate is None:
                result.append(fragments[index])
                index += 1
                continue

            previous, current = fragments[index], fragments[index + 1]
            record: Dict[str, Any] = {
                **pair_candidate.to_dict(),
                "prev_id": previous.id,
                "cur_id": current.id,
                "shot_id": previous.shot_id,
            }

            merged = merge_fragments(
                previous, current, max_duration=max_duration
            )
            if merged is not None:
                result.append(merged)
                record.update(
                    {
                        "action": "merge",
                        "durations": [merged.duration],
                        "replacement_count": 1,
                    }
                )
                operations.append(record)
                index += 2
                continue

            outcome = resplit_duplicate_pair(
                previous,
                current,
                shot=shot_lookup.get(previous.shot_id),
                max_duration=max_duration,
                min_duration=FRAGMENT_MIN_DURATION,
            )
            result.extend(outcome.fragments)
            record.update(
                {
                    "action": outcome.action,
                    "reason": outcome.reason,
                    "durations": [fragment.duration for fragment in outcome.fragments],
                    "replacement_count": len(outcome.fragments),
                    "warnings": list(outcome.warnings),
                    "dropped_duration": outcome.dropped_duration,
                }
            )
            operations.append(record)
            index += 2

        summary = {
            "candidate_count": len(candidates),
            "same_shot_count": len(eligible),
            "skipped_cross_shot": len(skipped),
            "merged": sum(1 for op in operations if op["action"] == "merge"),
            "resplit": sum(
                1 for op in operations if op["action"] == ACTION_RESPLIT
            ),
            "truncated": sum(
                1 for op in operations if op["action"] == ACTION_TRUNCATE
            ),
            "split_shots": len(
                {
                    op["shot_id"]
                    for op in operations
                    if op["action"] == ACTION_RESPLIT
                }
            ),
        }

        return result, {
            "candidates": [candidate.to_dict() for candidate in candidates],
            "operations": operations,
            "skipped": skipped,
            "summary": summary,
        }

    def _reflow_timeline(self, fragments: List[VideoFragment]) -> None:
        """按新时长重排开始时间，保持时间连续性"""
        if not fragments:
            return
        cursor = fragments[0].start_time
        for fragment in fragments:
            fragment.start_time = round(cursor, 2)
            cursor += fragment.duration

    def _renumber_fragments(self, fragments: List[VideoFragment]) -> Dict[str, Any]:
        """按顺序重编号并记录新旧 ID 映射"""
        id_map: Dict[str, Any] = {}
        for index, fragment in enumerate(fragments):
            old_id = fragment.id
            new_id = self._generate_fragment_id(index)
            metadata = dict(fragment.metadata or {})
            source_ids = (
                metadata.get("merged_from")
                or metadata.get("resplit_from")
                or [old_id]
            )
            metadata["pre_renumber_id"] = old_id
            fragment.metadata = metadata
            fragment.id = new_id
            id_map[new_id] = {
                "shot_id": fragment.shot_id,
                "fragment_id": old_id,
                "source_fragment_ids": list(source_ids),
            }
        return id_map

    def _sync_split_stats(self, fragment_sequence: FragmentSequence) -> None:
        """按实际来源镜头校正 fragments_split，并同步 is_split 标记"""
        groups: Dict[str, List[VideoFragment]] = {}
        for fragment in fragment_sequence.fragments:
            metadata = fragment.metadata or {}
            shot_key = str(metadata.get("original_shot") or fragment.shot_id)
            groups.setdefault(shot_key, []).append(fragment)

        split_shots = sum(1 for group in groups.values() if len(group) > 1)
        shot_count = int(
            fragment_sequence.source_info.get("shot_count") or len(groups)
        )

        fragment_sequence.stats["fragments_split"] = split_shots
        fragment_sequence.stats["split_ratio"] = (
            round(split_shots / shot_count, 2) if shot_count else 0
        )

        for group in groups.values():
            is_split = len(group) > 1
            for fragment in group:
                fragment.metadata["is_split"] = is_split

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
