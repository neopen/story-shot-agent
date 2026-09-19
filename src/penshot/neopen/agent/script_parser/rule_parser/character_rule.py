"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character_rule.py
@Description: 角色规则 - 从角色提示行、人物设定章节与台词归属中抽取角色
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from penshot.neopen.agent.script_parser.rule_parser.rule_contracts import EntityRule
from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    LineKind,
    ParseContext,
)
from penshot.neopen.agent.script_parser.rule_parser.scene_segmenter import (
    metadata_spans,
)
from penshot.neopen.agent.script_parser.rule_parser.text_helpers import (
    NON_CHARACTER_WORDS,
    find_subject,
    infer_gender,
)
from penshot.neopen.agent.script_parser.script_parser_models import (
    CharacterInfo,
    CharacterType,
)

# 人物设定章节的标题，其后到下一个场景标题之间的内容为角色档案
_CHARACTER_SECTIONS = frozenset(
    {"人物", "角色", "人物设定", "角色设定", "出场人物", "主要人物", "选角要点"}
)
# 角色档案里的属性标签：其后的值属于当前角色，本身不是角色名
_ATTRIBUTE_LABELS = frozenset(
    {
        "年龄",
        "性别",
        "身份",
        "性格",
        "特征",
        "外貌",
        "身高",
        "体重",
        "职业",
        "爱好",
        "特长",
        "台词",
        "语速",
        "生日",
        "别名",
        "简介",
        "备注",
    }
)
# 主角判定：台词量占全剧的比例达到该值时视为主角
_LEAD_ROLE = "主角"
_SUPPORTING_ROLE = "配角"
_EXTRA_ROLE = "龙套"
_MAX_TRAITS = 6
_MAX_TRAIT_LENGTH = 12


@dataclass
class CharacterEvidence:
    """角色证据 - 同一个角色名可能来自提示行、档案或台词归属"""

    name: str
    description: str = ""
    cue_descriptions: List[str] = field(default_factory=list)
    scene_ids: List[str] = field(default_factory=list)
    speech_count: int = 0
    # 首次出现次序，用于在台词量相同时保持剧本文档顺序
    order: int = 0

    def merge(self, other: "CharacterEvidence") -> None:
        """合并同名角色的证据，描述取更长的那个"""
        if len(other.description) > len(self.description):
            self.description = other.description
        for cue in other.cue_descriptions:
            if cue and cue not in self.cue_descriptions:
                self.cue_descriptions.append(cue)
        for scene_id in other.scene_ids:
            if scene_id not in self.scene_ids:
                self.scene_ids.append(scene_id)
        self.speech_count += other.speech_count


class CharacterRule(EntityRule[CharacterInfo]):
    """角色抽取规则

    证据来源按可信度递减：角色提示行 > 人物设定档案 > 台词归属 > 正文主语。
    """

    @property
    def name(self) -> str:
        return "character"

    @property
    def entity_type(self) -> str:
        return "character"

    def extract(self, context: ParseContext) -> List[CharacterInfo]:
        """抽取并按出场顺序返回角色列表"""
        evidence = self._collect(context)
        ordered = sorted(
            evidence.values(), key=lambda item: (-item.speech_count, item.order)
        )
        lead_names = self._lead_names(ordered)
        return [self._to_info(item, lead_names) for item in ordered if item.name]

    # ---------------------------- 证据收集 ----------------------------
    def _collect(self, context: ParseContext) -> Dict[str, CharacterEvidence]:
        evidence: Dict[str, CharacterEvidence] = {}
        for collector in (
            self._collect_from_tokens,
            self._collect_from_bios,
            self._collect_from_drafts,
        ):
            collector(context, evidence)
        return evidence

    @staticmethod
    def _ensure(evidence: Dict[str, CharacterEvidence], name: str) -> CharacterEvidence:
        """取回同名角色证据，首次出现时记录文档次序"""
        item = evidence.get(name)
        if item is None:
            item = CharacterEvidence(name=name, order=len(evidence))
            evidence[name] = item
        return item

    def _collect_from_tokens(
        self, context: ParseContext, evidence: Dict[str, CharacterEvidence]
    ) -> None:
        # 场记区域里的行按分类结果仍是 CHARACTER（如「中层：寻找存在的痕迹」），必须排除
        excluded = metadata_spans(context.tokens)
        for token in context.tokens:
            if token.kind is not LineKind.CHARACTER or token.index in excluded:
                continue
            name = (token.payload.get("name") or "").strip()
            if not self._is_plausible(name, context):
                continue
            item = self._ensure(evidence, name)
            cue = token.payload.get("cue_description")
            if cue and cue not in item.cue_descriptions:
                item.cue_descriptions.append(cue)
            if token.payload.get("inline_dialogue"):
                self._attach_scene(item, context, token.index)
                item.speech_count += 1

    def _collect_from_bios(
        self, context: ParseContext, evidence: Dict[str, CharacterEvidence]
    ) -> None:
        """解析「人物设定」章节里的角色名行与其后的属性行

        形如 ``1. **李明**`` 的短行开启一个新角色，紧随的 ``- 年龄：18岁``
        这类属性行把值并进该角色的描述；属性标签本身不是角色名。
        """
        in_section = False
        current: Optional[CharacterEvidence] = None
        for token in context.tokens:
            role = token.payload.get("role")
            if role in ("section", "metadata_section"):
                label = token.payload.get("section") or token.payload.get("label") or ""
                in_section = self._is_character_section(label)
                if not in_section:
                    current = None
                continue
            if token.kind is LineKind.SCENE_HEADING:
                in_section = False
                current = None
                continue
            if not in_section or token.is_blank:
                continue

            text = token.text.lstrip("#-* ").strip()
            if "：" in text or ":" in text:
                head, _, value = text.replace(":", "：").partition("：")
                current = self._apply_entry(
                    head.strip(" -*"), value.strip(), current, context, evidence
                )
                continue

            name = text.strip(" -*")
            if self._is_plausible(name, context):
                current = self._ensure(evidence, name)

    def _apply_entry(
        self,
        head: str,
        value: str,
        current: Optional[CharacterEvidence],
        context: ParseContext,
        evidence: Dict[str, CharacterEvidence],
    ) -> Optional[CharacterEvidence]:
        """处理一条「标签：值」行，返回新的当前角色

        只有角色属性标签才把值并入当前角色；``地点``/``时间`` 这类场记标签
        属于场景信息，虽同样不是角色名，但不应混进角色描述。
        """
        if not head:
            return current
        if head in _ATTRIBUTE_LABELS:
            if current is not None and value:
                current.description = f"{current.description}；{value}".lstrip("；")
            return current
        if head in context.vocabulary.metadata_labels or not self._is_plausible(
            head, context
        ):
            return current
        item = self._ensure(evidence, head)
        if len(value) > len(item.description):
            item.description = value
        return item

    def _collect_from_drafts(
        self, context: ParseContext, evidence: Dict[str, CharacterEvidence]
    ) -> None:
        """台词归属与动作主体：正文里出现过的角色名"""
        for scene in context.scenes:
            for draft in scene.drafts:
                if not draft.character:
                    continue
                if not self._is_plausible(draft.character, context):
                    continue
                item = self._ensure(evidence, draft.character)
                if scene.id not in item.scene_ids:
                    item.scene_ids.append(scene.id)
                if draft.type.value == "dialogue":
                    item.speech_count += 1

    @staticmethod
    def _attach_scene(
        item: CharacterEvidence, context: ParseContext, line_index: int
    ) -> None:
        scene = context.scene_of_line(line_index)
        if scene is not None and scene.id not in item.scene_ids:
            item.scene_ids.append(scene.id)

    @staticmethod
    def _is_character_section(label: str) -> bool:
        return any(section and section in label for section in _CHARACTER_SECTIONS)

    def _is_plausible(self, name: str, context: ParseContext) -> bool:
        if not name or len(name) > 8:
            return False
        if name in NON_CHARACTER_WORDS or name in context.vocabulary.metadata_labels:
            return False
        if find_subject(name, context.vocabulary.subject_verbs):
            # 「李明独自」这类残留：整段就是主语+动词时说明没切干净
            return False
        return not any(char.isdigit() for char in name)

    # ---------------------------- 结果构造 ----------------------------
    @staticmethod
    def _lead_names(ordered: Sequence[CharacterEvidence]) -> List[str]:
        """台词量最高的一到两个角色视为主角"""
        speakers = [item for item in ordered if item.speech_count > 0]
        if not speakers:
            return [item.name for item in ordered[:1]]
        best = speakers[0].speech_count
        return [item.name for item in speakers if item.speech_count == best][:2]

    def _to_info(
        self, item: CharacterEvidence, lead_names: Sequence[str]
    ) -> CharacterInfo:
        if item.name in lead_names:
            role = _LEAD_ROLE
        elif item.speech_count > 0 or item.description:
            # 有人物档案的角色至少是配角，档案占位符之外的才算龙套
            role = _SUPPORTING_ROLE
        else:
            role = _EXTRA_ROLE
        description = item.description or "".join(item.cue_descriptions)
        return CharacterInfo(
            name=item.name,
            gender=infer_gender(item.name, item.description),
            role=role,
            type=CharacterType.DEFAULT,
            description=description or None,
            key_traits=self._traits(item),
        )

    @staticmethod
    def _traits(item: CharacterEvidence) -> List[str]:
        traits: List[str] = []
        for part in (
            item.description.replace("；", "、").replace("，", "、").split("、")
        ):
            trait = part.strip()
            if trait and len(trait) <= _MAX_TRAIT_LENGTH and trait not in traits:
                traits.append(trait)
            if len(traits) >= _MAX_TRAITS:
                break
        return traits


def default_character_rule() -> CharacterRule:
    """默认角色规则"""
    return CharacterRule()
