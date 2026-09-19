"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: global_aggregator.py
@Description: 全局元数据聚合 - 把各规则抽取到的候选实体汇总为贯穿全剧的 GlobalMetadata
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

import re
from typing import Any, Dict, List, Sequence, Tuple

from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    LocationCandidate,
    OutfitCandidate,
    ParseContext,
    PropCandidate,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import label_values
from penshot.neopen.agent.script_parser.script_parser_models import (
    CharacterOutfit,
    GlobalMetadata,
    LocationItem,
    PropItem,
)

# 出现在多少个场景即视为贯穿全剧的关键道具
_RECURRING_SCENE_THRESHOLD = 2
# 地点别名与视觉特征的保留上限
_MAX_ALIASES = 4
_MAX_VISUAL_CUES = 6
# 连续性要点条数上限，避免长剧本产出难以消费的长文本
_MAX_NOTES = 8
# 音效标签：其后列出的条目视为音效
_AUDIO_LABELS = ("声音", "音效", "环境音", "音乐", "配乐")
_AUDIO_VALUE_SPLIT_RE = re.compile(r"[-–—•·、,，;；/]|\s{2,}")
_MAX_SOUND_LENGTH = 12
_NOISE_PARTS = frozenset({"", "无", "略", "同上", "其他"})


def _norm(name: str) -> str:
    """实体名归一化：去掉书名号与空白，用于判重"""
    return re.sub(r"[\s《》【】]", "", name or "")


def _same_place(left: str, right: str) -> bool:
    """两个地点名是否指同一处

    同名自然合并；后缀关系也合并，使「教室外走廊」并入「走廊」，
    从而保证规范名是其中最短的那个。
    """
    return left == right or left.endswith(right) or right.endswith(left)


class GlobalAggregator:
    """全局元数据聚合器

    实体规则各自只产出自己类型的候选，聚合器负责跨场景合并同一实体、
    裁定重要性与连续性要点，最终产出完整的 GlobalMetadata。
    """

    def aggregate(
        self,
        context: ParseContext,
        props: Sequence[PropCandidate],
        outfits: Sequence[OutfitCandidate],
        locations: Sequence[LocationCandidate],
    ) -> GlobalMetadata:
        """汇总道具、服装、地点与音频信息"""
        key_props = self._merge_props(props, context)
        character_outfits = self._merge_outfits(outfits)
        key_locations, aliases = self._merge_locations(locations, context)
        return GlobalMetadata(
            key_props=key_props,
            character_outfits=character_outfits,
            key_locations=key_locations,
            continuity_notes=self._continuity_notes(
                context, key_props, character_outfits, aliases
            ),
            audio_atmosphere=self._audio_atmosphere(context),
            recurring_sounds=self._recurring_sounds(context),
        )

    # ---------------------------- 关键道具 ----------------------------
    def _merge_props(
        self, props: Sequence[PropCandidate], context: ParseContext
    ) -> List[PropItem]:
        """同名道具合并，并把出现的场景按剧本顺序排列"""
        merged: Dict[str, PropCandidate] = {}
        for candidate in props:
            key = _norm(candidate.name)
            if not key:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            for scene_id in candidate.appears_in or [candidate.scene_id]:
                if scene_id and scene_id not in existing.appears_in:
                    existing.appears_in.append(scene_id)
            existing.color = existing.color or candidate.color
            existing.description = existing.description or candidate.description
            existing.marker = existing.marker or candidate.marker

        order = {scene.id: index for index, scene in enumerate(context.scenes)}
        items: List[PropItem] = []
        for candidate in merged.values():
            scenes = [
                scene for scene in candidate.appears_in or [candidate.scene_id] if scene
            ]
            scenes.sort(key=lambda scene_id: order.get(scene_id, len(order)))
            items.append(
                PropItem(
                    name=candidate.name,
                    description=candidate.description
                    or f"出现在场景：{'、'.join(scenes)}",
                    appears_in=scenes,
                    color=candidate.color,
                    importance=self._prop_importance(scenes, candidate),
                )
            )
        items.sort(key=lambda item: (-len(item.appears_in), item.name))
        return items

    @staticmethod
    def _prop_importance(scenes: Sequence[str], candidate: PropCandidate) -> str:
        """出现于多个场景或带出现/消失标记的道具对连续性影响最大"""
        if len(scenes) >= _RECURRING_SCENE_THRESHOLD or candidate.marker:
            return "high"
        return "medium"

    # ---------------------------- 角色服装 ----------------------------
    @staticmethod
    def _merge_outfits(outfits: Sequence[OutfitCandidate]) -> List[CharacterOutfit]:
        """同一角色的同类服装合并，颜色/风格/材质取首个非空值"""
        merged: Dict[Tuple[str, str], OutfitCandidate] = {}
        for candidate in outfits:
            if not candidate.character:
                continue
            key = (candidate.character, candidate.keyword or candidate.description)
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            existing.color = existing.color or candidate.color
            existing.style = existing.style or candidate.style
            existing.material = existing.material or candidate.material
            if len(candidate.description) > len(existing.description):
                existing.description = candidate.description

        return [
            CharacterOutfit(
                character=candidate.character,
                description=candidate.description,
                color=candidate.color,
                style=candidate.style,
                material=candidate.material,
            )
            for candidate in merged.values()
        ]

    # ---------------------------- 关键地点 ----------------------------
    def _merge_locations(
        self, locations: Sequence[LocationCandidate], context: ParseContext
    ) -> Tuple[List[LocationItem], Dict[str, List[str]]]:
        """同名与后缀关系的地点合并，别名与视觉特征累加

        返回地点列表，以及「规范名 -> 别名」映射，后者用于生成连续性要点。
        """
        groups: List[Dict[str, Any]] = []
        for candidate in sorted(
            locations, key=lambda item: (len(item.name), item.name)
        ):
            name = candidate.name.strip()
            if not name:
                continue
            group = next(
                (item for item in groups if _same_place(name, item["name"])), None
            )
            if group is None:
                groups.append(
                    {
                        "name": name,
                        "description": "",
                        "scenes": [],
                        "cues": [],
                        "aliases": [],
                    }
                )
                group = groups[-1]
            elif name != group["name"] and name not in group["aliases"]:
                group["aliases"].append(name)

            if candidate.scene_id and candidate.scene_id not in group["scenes"]:
                group["scenes"].append(candidate.scene_id)
            group["description"] = group["description"] or candidate.description
            for cue in candidate.visual_cues:
                if (
                    cue
                    and cue not in group["cues"]
                    and len(group["cues"]) < _MAX_VISUAL_CUES
                ):
                    group["cues"].append(cue)

        order = {scene.id: index for index, scene in enumerate(context.scenes)}
        items: List[LocationItem] = []
        aliases: Dict[str, List[str]] = {}
        for group in groups:
            scenes = sorted(
                group["scenes"], key=lambda scene_id: order.get(scene_id, len(order))
            )
            items.append(
                LocationItem(
                    name=group["name"],
                    description=group["description"] or group["name"],
                    appears_in=scenes,
                    visual_cues=group["cues"],
                )
            )
            if group["aliases"]:
                aliases[group["name"]] = group["aliases"][:_MAX_ALIASES]
        items.sort(key=lambda item: (-len(item.appears_in), item.name))
        return items, aliases

    # ---------------------------- 音频与连续性 ----------------------------
    def _recurring_sounds(self, context: ParseContext) -> List[str]:
        """在 2 个及以上场景出现的音效词，含「声音：」标签里列出的条目"""
        scene_counts: Dict[str, int] = {}
        for scene in context.scenes:
            heard = set(scene.env_sounds) | set(self._labeled_sounds(scene.meta_text))
            for sound in heard:
                scene_counts[sound] = scene_counts.get(sound, 0) + 1
        return [
            sound
            for sound, count in scene_counts.items()
            if count >= _RECURRING_SCENE_THRESHOLD
        ]

    @staticmethod
    def _labeled_sounds(text: str) -> List[str]:
        """「声音：脚步声、笑声」这类标签值里列出的音效"""
        sounds: List[str] = []
        for label in _AUDIO_LABELS:
            for value in label_values(text, label):
                for part in _AUDIO_VALUE_SPLIT_RE.split(value):
                    sound = part.strip(" ：:*（）()")
                    if (
                        sound
                        and sound not in _NOISE_PARTS
                        and len(sound) <= _MAX_SOUND_LENGTH
                        and sound not in sounds
                    ):
                        sounds.append(sound)
        return sounds

    @staticmethod
    def _audio_atmosphere(context: ParseContext) -> str:
        """全局音频氛围取出现次数最多的场景氛围"""
        counts: Dict[str, int] = {}
        for scene in context.scenes:
            if scene.atmosphere:
                counts[scene.atmosphere] = counts.get(scene.atmosphere, 0) + 1
        if not counts:
            return "neutral"
        return max(counts.items(), key=lambda item: item[1])[0]

    def _continuity_notes(
        self,
        context: ParseContext,
        key_props: Sequence[PropItem],
        outfits: Sequence[CharacterOutfit],
        aliases: Dict[str, List[str]],
    ) -> str:
        """生成确定性的中文连续性要点，供下游保持跨镜头一致"""
        notes: List[str] = []
        for prop in key_props:
            if len(prop.appears_in) >= _RECURRING_SCENE_THRESHOLD:
                notes.append(
                    f"道具「{prop.name}」出现在 {len(prop.appears_in)} 个场景，外观需保持一致。"
                )
        for outfit in outfits:
            notes.append(
                f"角色「{outfit.character}」的服装（{outfit.description}）需保持一致。"
            )
        for name, alias_list in aliases.items():
            notes.append(
                f"地点「{name}」在不同场景写作：{'、'.join(alias_list)}，视为同一地点。"
            )
        if context.scenes:
            notes.append(
                f"全剧共 {len(context.scenes)} 个场景，场景地点与时段需按序衔接。"
            )
        return "\n".join(notes[:_MAX_NOTES])
