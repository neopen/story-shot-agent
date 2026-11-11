"""角色服装连续性回归测试。

覆盖被反复误报的 `appearance_change`：
1. 同一角色在片段间换用“身穿/佩戴”等措辞不算服装变化；
2. 片段未描述服装、或只提到鞋袜/配饰时沿用上次已知服装，不误报；
3. 真正换装仍会上报；
4. 外观基线按轮次隔离，本轮首片段不与上轮末片段比较；
5. 摘要统计包含 warning，避免“问题总数 2 但各级别都是 0”。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.continuity_guardian_checker import (
    ContinuityGuardianChecker,
)
from penshot.neopen.agent.continuity_guardian.continuity_guardian_models import (
    ContinuityCheckResult,
    ContinuityIssueType,
)

TEACHER_DRESS_WITH_GLASSES = (
    "medium shot, classroom interior, beige silk dress female teacher with glasses "
    "entering through door, walking towards student Li Ming\n\n"
    "中景镜头：教室内部，身穿米色丝绸连衣裙、佩戴眼镜的女教师轻轻推门进入，"
    "走向学生李明 [Character consistency: 语文老师, clothing: 得体的浅色连衣裙或套装]"
)
TEACHER_SILK_DRESS = (
    "over-the-shoulder shot, Chinese language teacher standing beside him, "
    "wearing beige silk dress and glasses, leaning slightly forward\n\n"
    "过肩镜头：语文老师站在李明身旁，身穿米色丝绸连衣裙并佩戴眼镜，身体微微前倾"
)
TEACHER_GLASSES_ONLY = "close-up shot, teacher 佩戴眼镜, calm encouraging expression"


def _fragment(fragment_id: str, prompt: str) -> SimpleNamespace:
    """构造片段提示词对象"""
    return SimpleNamespace(
        fragment_id=fragment_id, prompt=prompt, main_character="语文老师"
    )


def _context(prompts) -> dict:
    """构造连续性检查所需上下文"""
    return {
        "parsed_script": SimpleNamespace(
            characters=[SimpleNamespace(name="语文老师")], scenes=[]
        ),
        "shot_sequence": SimpleNamespace(shots=[]),
        "instructions": SimpleNamespace(fragments=prompts),
    }


def _appearance_issues(result: ContinuityCheckResult) -> list:
    """筛出外观变化问题"""
    return [
        issue
        for issue in result.issues
        if issue.type == ContinuityIssueType.CHARACTER_APPEARANCE_CHANGE
    ]


def _run_checker(prompts) -> ContinuityCheckResult:
    """执行一次角色连续性检查"""
    checker = ContinuityGuardianChecker()
    result = ContinuityCheckResult()
    checker.check_character_continuity(_context(prompts), result)
    return result


class TestAppearanceWordingIsNotChange:
    """措辞差异不得判成外观变化"""

    def test_wearing_and_accessory_phrasing_is_consistent(self):
        """“身穿连衣裙”与“佩戴眼镜”交替出现时不再上报 穿 -> 戴"""
        result = _run_checker(
            [
                _fragment("frag_003", TEACHER_DRESS_WITH_GLASSES),
                _fragment("frag_004", TEACHER_SILK_DRESS),
                _fragment("frag_009", TEACHER_GLASSES_ONLY),
            ]
        )

        assert not _appearance_issues(result)

    def test_same_garment_with_extra_modifiers_is_consistent(self):
        """同一件衣服增删修饰语不算换装"""
        result = _run_checker(
            [
                _fragment("frag_001", "medium shot, wearing a beige silk dress"),
                _fragment("frag_002", "close-up shot, wearing a light dress"),
            ]
        )

        assert not _appearance_issues(result)

    def test_field_missing_in_later_fragment_keeps_baseline(self):
        """后一片段没写服装时沿用上次服装，不与更早片段误比较"""
        result = _run_checker(
            [
                _fragment("frag_001", "medium shot, wearing a beige silk dress"),
                _fragment("frag_002", "close-up shot, only glasses in frame"),
                _fragment("frag_003", "wide shot, wearing a beige dress"),
            ]
        )

        assert not _appearance_issues(result)

    def test_footwear_only_mention_is_not_outfit_change(self):
        """只提到鞋袜等细节时不参与整体换装判定"""
        result = _run_checker(
            [
                _fragment("frag_001", "medium shot, wearing a beige silk dress"),
                _fragment("frag_002", "close-up shot of wet shoes on the floor"),
            ]
        )

        assert not _appearance_issues(result)


class TestRealAppearanceChange:
    """真实外观变化仍需上报"""

    def test_garment_swap_is_reported_once(self):
        """连衣裙换成雨衣上报一次，并给出实际服装词"""
        result = _run_checker(
            [
                _fragment("frag_001", "medium shot, wearing a beige silk dress"),
                _fragment("frag_002", "wide shot, wearing a red raincoat"),
            ]
        )

        issues = _appearance_issues(result)
        assert len(issues) == 1
        assert issues[0].fragment_id == "frag_002"
        assert "dress" in issues[0].description
        assert "raincoat" in issues[0].description

    def test_baseline_is_scoped_to_current_round(self):
        """本轮首片段不与上轮末片段比较，避免跨轮反复误报"""
        checker = ContinuityGuardianChecker()
        checker.check_all_continuity(
            _context(
                [
                    _fragment("frag_001", "medium shot, wearing a beige dress"),
                    _fragment("frag_002", "wide shot, wearing a red raincoat"),
                ]
            )
        )

        second = checker.check_all_continuity(
            _context([_fragment("frag_101", "medium shot, wearing a beige dress")])
        )

        assert not _appearance_issues(second)


class TestContinuitySummary:
    """摘要统计"""

    def test_warning_issues_are_counted(self):
        """warning 级问题计入摘要，问题总数不再与各级别全 0 矛盾"""
        result = _run_checker(
            [
                _fragment("frag_001", "medium shot, wearing a beige dress"),
                _fragment("frag_002", "wide shot, wearing a red raincoat"),
            ]
        )

        summary = result.get_summary()
        assert summary["total_issues"] == 1
        assert summary["warning"] == 1
        assert summary["critical"] == 0
