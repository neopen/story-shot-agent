"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: rule_contracts.py
@Description: 规则解析器契约 - 定义可扩展的规则接口与注册表
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/17
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Generic, List, Optional, Type, TypeVar

from penshot.neopen.agent.script_parser.rule_parser.rule_models import (
    LineMatch,
    LineToken,
    SceneDraft,
)

if TYPE_CHECKING:
    from penshot.neopen.agent.script_parser.rule_parser.config_vocabulary import (
        RuleVocabulary,
    )
    from penshot.neopen.agent.script_parser.rule_parser.rule_models import ParseContext

T = TypeVar("T")


class LineClassifier(ABC):
    """行分类器 - 责任链节点

    顺序敏感：链上第一个返回 LineMatch 的分类器胜出，
    因此实现应尽量收紧自己的匹配条件，避免误吞后续分类器的行。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """分类器名称，用于注册与诊断"""

    @abstractmethod
    def match(
        self, token: LineToken, vocabulary: "RuleVocabulary"
    ) -> Optional[LineMatch]:
        """尝试匹配该行，未命中返回 None"""


class EntityRule(ABC, Generic[T]):
    """实体抽取规则 - 顺序无关、可叠加

    对整份剧本扫描并产出实体候选，多个规则的结果会合并，
    因此实现只负责自己的实体类型，不需要关心其它规则。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """规则名称，用于注册与诊断"""

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """产出的实体类型标识"""

    @abstractmethod
    def extract(self, context: "ParseContext") -> List[T]:
        """扫描全部场景并返回抽取到的实体"""


class SceneAttributeRule(ABC):
    """场景属性规则 - 顺序无关

    就地补全单个场景草稿的属性（地点、时间、天气、氛围等），
    各规则写入不同字段，彼此不冲突。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """规则名称，用于注册与诊断"""

    @abstractmethod
    def apply(self, scene: SceneDraft, context: "ParseContext") -> None:
        """就地补全场景草稿属性"""


class RuleRegistry(Generic[T]):
    """规则注册表 - 按名称注册与查找

    为规则提供统一的登记入口，调用方可以按名称替换、追加或跳过单个规则，
    从而在不修改引擎的前提下扩展解析能力。
    """

    def __init__(self, rule_type: Type[T]):
        self._rule_type = rule_type
        self._rules: Dict[str, T] = {}

    def register(self, rule: T) -> T:
        """注册规则，同名规则会被覆盖"""
        if not isinstance(rule, self._rule_type):
            raise TypeError(f"规则 {rule!r} 不是 {self._rule_type.__name__} 的实例")
        self._rules[rule.name] = rule
        return rule

    def register_all(self, rules: List[T]) -> None:
        """批量注册规则"""
        for rule in rules:
            self.register(rule)

    def unregister(self, name: str) -> Optional[T]:
        """移除规则并返回，未注册时返回 None"""
        return self._rules.pop(name, None)

    def get(self, name: str) -> Optional[T]:
        """按名称获取规则"""
        return self._rules.get(name)

    def names(self) -> List[str]:
        """已注册规则名称，按注册顺序"""
        return list(self._rules)

    def all(self) -> List[T]:
        """已注册规则，按注册顺序"""
        return list(self._rules.values())
