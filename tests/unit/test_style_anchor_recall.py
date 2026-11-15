"""M0.4.1 P1 回归测试：英文风格前缀生效 + 向量检索按角色/场景锚点召回。

覆盖：
- `infer_style_anchor` 从显式元数据 / 关键词 / 音频氛围推断英文风格；
- `build_style_prefix` 只输出英文并去重；
- `process_with_contract` 将英文风格锚点写入契约；
- `process_with_style_consistency` 真正把英文风格前缀注入 prompt；
- `build_fragment_anchor_query` / `build_issue_anchor_query` 按角色外观与场景构建查询；
- 工作流锚点召回：按锚点检索并按去重后注入历史成功提示词。
"""

from types import SimpleNamespace

from penshot.neopen.agent.continuity_guardian.anchor_recall import (
    build_fragment_anchor_query,
    build_issue_anchor_query,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
    SceneContract,
)
from penshot.neopen.agent.continuity_guardian.style_anchors import (
    build_style_prefix,
    infer_style_anchor,
    infer_style_anchor_with_provenance,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.shot_segmenter.shot_segmenter_models import (
    ShotInfo,
    ShotSequence,
)
from penshot.neopen.agent.video_splitter.video_splitter_models import (
    FragmentSequence,
    VideoFragment,
)
from penshot.neopen.agent.workflow.workflow_nodes import WorkflowNodes
from penshot.neopen.agent.workflow.workflow_state_types import WorkflowState


# ---------------------------------------------------------------------------
# 风格锚点（英文前缀）
# ---------------------------------------------------------------------------


def _parsed_script(**overrides):
    """构造最小剧本解析结果"""
    metadata = overrides.pop("metadata", {"parser_type": "llm"})
    atmosphere = overrides.pop("atmosphere", "neutral")
    notes = overrides.pop("notes", "")
    scenes = overrides.pop("scenes", [])
    return SimpleNamespace(
        title=overrides.pop("title", ""),
        metadata=metadata,
        scenes=scenes,
        global_metadata=SimpleNamespace(
            continuity_notes=notes, audio_atmosphere=atmosphere
        ),
    )


def test_infer_style_anchor_from_explicit_metadata():
    """显式英文 genre 优先，六维取题材风格，显式英文描述保留"""
    parsed = _parsed_script(
        metadata={"genre": "thriller", "style_description": "high contrast lighting"}
    )
    assert infer_style_anchor(parsed) == {
        "genre": "thriller",
        "lighting": "high contrast lighting",
        "palette": "desaturated palette",
        "mood": "tense",
        "framing": "shadowed framing",
        "description": "high contrast lighting",
    }


def test_infer_style_anchor_from_keywords():
    """无显式 genre 时从标题/连续性要点关键词推断"""
    parsed = _parsed_script(title="雨夜来电", notes="整体氛围悬疑紧张")
    assert infer_style_anchor(parsed).get("genre") == "thriller"


def test_infer_style_anchor_from_atmosphere():
    """英文音频氛围映射为短英文风格描述"""
    parsed = _parsed_script(atmosphere="tense")
    result = infer_style_anchor(parsed)
    assert result.get("genre") is None or result.get("genre") == ""
    assert result["description"] == "tense atmosphere, high contrast lighting"


def test_infer_style_anchor_from_chinese_atmosphere():
    """中文氛围/要点按关键词映射为短英文风格描述"""
    parsed = _parsed_script(notes="整体氛围从压抑逐渐转为怀旧、感动")
    result = infer_style_anchor(parsed)
    assert result["description"] == "muted colors, melancholic tone"


def test_infer_style_anchor_from_scene_text():
    """场景文本中的校园/教室信号推断为 youth genre"""
    parsed = _parsed_script(
        title="记忆墙上的痕迹",
        scenes=[SimpleNamespace(location="教室", description="放学后的空教室")],
    )
    assert infer_style_anchor(parsed).get("genre") == "youth"


def test_infer_style_anchor_ignores_incidental_action_word():
    """真实剧本中"动作音"等描述不应误判为 action genre"""
    parsed = _parsed_script(
        title="痕迹",
        notes="前期以环境静默和细微动作音为主",
        atmosphere="整体氛围由静谧忧伤转为温暖治愈",
        scenes=[
            SimpleNamespace(
                location="教室", description="放学后的空教室，氛围安静且略带压抑"
            )
        ],
    )
    result = infer_style_anchor(parsed)
    assert result["genre"] == "youth"
    assert result["description"] == "muted colors, melancholic tone"


def test_infer_style_anchor_empty_signals():
    """无任何风格信号时兜底三维，genre 保持为空（FR-088/FR-090）"""
    assert infer_style_anchor(_parsed_script()) == {
        "lighting": "natural lighting",
        "palette": "muted colors",
        "mood": "neutral",
    }


def test_build_style_prefix_skips_chinese():
    """中文风格描述被跳过，维度值按固定顺序输出"""
    prefix = build_style_prefix(
        {"genre": "drama", "description": "雨夜街道，霓虹灯闪烁"}
    )
    assert prefix == "[Style: drama, naturalistic lighting, muted colors, emotional]"
    assert "雨夜" not in prefix


def test_build_style_prefix_dedupes():
    """题材与氛围映射到同一维度时不重复输出"""
    prefix = build_style_prefix({"genre": "thriller", "atmosphere": "tense"})
    assert prefix == (
        "[Style: thriller, high contrast lighting, desaturated palette, "
        "tense, shadowed framing]"
    )


def test_build_style_prefix_drops_legacy_phrases_conflicting_with_dimensions():
    """FR-021/FR-029：旧描述与已决议维度冲突时丢弃并写入 provenance"""
    anchor = {
        "genre": "youth",
        "lighting": "natural lighting",
        "palette": "fresh pastel palette",
        "mood": "hopeful",
        "framing": "coming-of-age framing",
        "grade": "soft pastel grade",
        "description": "muted colors, melancholic tone",
    }
    provenance = {"discarded": []}

    prefix = build_style_prefix(anchor, provenance)

    assert prefix == (
        "[Style: youth, natural lighting, fresh pastel palette, hopeful, "
        "coming-of-age framing, soft pastel grade]"
    )
    assert provenance["discarded"] == [
        {"dimension": "palette", "value": "muted colors", "source": "description"},
        {"dimension": "mood", "value": "melancholic tone", "source": "description"},
    ]


def test_youth_scene_with_melancholic_arc_keeps_single_mood():
    """题材优先于音频氛围：忧伤开篇的青春剧本仍只渲染 hopeful，冲突记入 discarded"""
    parsed = _parsed_script(
        title="痕迹",
        atmosphere=(
            "整体氛围从静谧、略带忧伤逐渐过渡到温暖、怀旧，"
            "最后以温馨、充满希望的基调结束"
        ),
        scenes=[SimpleNamespace(location="教室", description="放学后的空教室")],
    )

    anchor, provenance = infer_style_anchor_with_provenance(parsed)
    prefix = build_style_prefix(anchor, provenance)

    assert anchor["genre"] == "youth"
    assert anchor["mood"] == "hopeful"
    assert "hopeful" in prefix
    assert "melancholic tone" not in prefix
    assert "muted colors" not in prefix
    assert {item["dimension"] for item in provenance["discarded"]} == {
        "palette",
        "mood",
    }
    assert "melancholic" in provenance["mood_candidates"]


def test_process_with_contract_sets_english_style_anchor(monkeypatch):
    """process_with_contract 将英文风格锚点写入契约"""
    from penshot.neopen.agent.script_parser_agent import ScriptParserAgent

    agent = object.__new__(ScriptParserAgent)
    parsed = _parsed_script(
        title="雨夜来电", notes="悬疑氛围，注意角色服装一致", atmosphere="tense"
    )
    parsed.scenes = []
    parsed.characters = []
    monkeypatch.setattr(agent, "parser_process", lambda text: parsed)

    _, contract = agent.process_with_contract("剧本")

    assert contract.style_anchor["title"] == "雨夜来电"
    assert contract.style_anchor["source_notes"] == "悬疑氛围，注意角色服装一致"
    assert contract.style_anchor["genre"] == "thriller"
    assert contract.style_anchor["atmosphere"] == "tense"
    assert (
        contract.style_anchor["description"]
        == "tense atmosphere, high contrast lighting"
    )
    # T-206：来源与候选一并写入契约，并可随 to_dict 落盘
    assert contract.style_anchor_provenance["genre_source"] == "continuity_notes"
    assert contract.style_anchor_provenance["genre_keyword"] == "悬疑"
    assert contract.style_anchor_provenance["confidence"] == "medium"
    assert contract.style_anchor_provenance["mood_source"] == "audio_atmosphere"
    assert (
        contract.to_dict()["style_anchor_provenance"]
        == contract.style_anchor_provenance
    )


def test_generate_prompts_node_persists_style_provenance():
    """T-206：契约 provenance 写入 instructions.metadata（AC-024/027）"""
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="a woman waits", duration=3.0)
        ]
    )
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    provenance = {
        "genre_source": "audio_atmosphere",
        "genre_keyword": "浪漫",
        "confidence": "low",
    }
    contract.set_style_anchor_provenance(provenance)

    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes._recall_patterns_by_anchors = lambda state: ([], {})
    nodes.workflow_memory = SimpleNamespace(
        get_memory_dict=lambda *args, **kwargs: {},
        get_memory_list=lambda *args, **kwargs: [],
        after_stage_completion=lambda *args, **kwargs: None,
    )
    nodes.prompt_converter = SimpleNamespace(
        apply_historical_context=lambda *args, **kwargs: None,
        apply_repair_params=lambda *args, **kwargs: None,
        process_with_style_consistency=lambda *args, **kwargs: instructions,
        detect_issues=lambda *args, **kwargs: [],
        clear_repair_params=lambda *args, **kwargs: None,
        clear_historical_context=lambda *args, **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)

    state = WorkflowState.from_raw_script("剧本内容")
    state.domain.contract = contract
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[
            VideoFragment(
                id="frag_001",
                shot_id="shot_001",
                duration=3.0,
                description="小明起身",
                continuity_notes={},
            )
        ]
    )

    nodes.generate_prompts_node(state)

    assert instructions.metadata["style_anchor_provenance"] == provenance
    # 该用例把召回整体打桩为空，节点只如实落盘，不凭空补出查询数（FR-042）
    assert instructions.metadata["anchor_recall"] == {}


def test_generate_prompts_node_persists_recall_statistics():
    """T-506：节点把真实召回统计写入 instructions.metadata（FR-040/042）"""
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(fragment_id="frag_001", prompt="a woman waits", duration=3.0)
        ]
    )
    nodes = object.__new__(WorkflowNodes)
    nodes._update_task_progress = lambda *args, **kwargs: None
    nodes._complete_stage = lambda *args, **kwargs: None
    nodes.knowledge_manager = _FakeKnowledgeManager()
    nodes.workflow_memory = SimpleNamespace(
        get_memory_dict=lambda *args, **kwargs: {},
        get_memory_list=lambda *args, **kwargs: [],
        after_stage_completion=lambda *args, **kwargs: None,
    )
    nodes.prompt_converter = SimpleNamespace(
        apply_historical_context=lambda *args, **kwargs: None,
        apply_repair_params=lambda *args, **kwargs: None,
        process_with_style_consistency=lambda *args, **kwargs: instructions,
        detect_issues=lambda *args, **kwargs: [],
        clear_repair_params=lambda *args, **kwargs: None,
        clear_historical_context=lambda *args, **kwargs: None,
    )
    nodes.storage = SimpleNamespace(save_obj_result=lambda *args, **kwargs: None)

    state = WorkflowState.from_raw_script("剧本内容")
    state.domain.contract = _contract_with_anchor()
    state.domain.shot_sequence = _shot_sequence()
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[
            VideoFragment(
                id="frag_001",
                shot_id="shot_001",
                duration=3.0,
                description="小明起身",
                continuity_notes={"main_character": "小明"},
            ),
            VideoFragment(
                id="frag_002",
                shot_id="shot_404",
                duration=3.0,
                description="空镜头：窗帘被风吹起",
                continuity_notes={},
            ),
        ]
    )

    nodes.generate_prompts_node(state)

    anchor_recall = instructions.metadata["anchor_recall"]
    assert anchor_recall["fragments"] == 2
    assert anchor_recall["queries"] == 1
    assert anchor_recall["queries_skipped"] == 1
    assert anchor_recall["attempted"] == 1
    assert anchor_recall["hits"] == 1
    assert anchor_recall["injected"] == 1
    assert anchor_recall["status"] == "hit"
    assert anchor_recall["kb"]["template_count"] == 3
    assert anchor_recall["top_k"] == 2
    assert anchor_recall["max_score"] == 0.9


def test_process_with_style_consistency_injects_english_prefix():
    """带风格一致性转换会把英文风格前缀加到每个片段 prompt 前"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.set_style_anchor("genre", "thriller")

    fragment_sequence = SimpleNamespace(
        fragments=[SimpleNamespace(id="frag_001", continuity_notes={})]
    )
    instructions = SimpleNamespace(
        fragments=[SimpleNamespace(fragment_id="frag_001", prompt="a woman waits")]
    )
    agent.prompt_process = lambda fs, ps: instructions

    agent.process_with_style_consistency(fragment_sequence, None, contract)

    assert instructions.fragments[0].prompt.startswith("[Style:")
    assert instructions.fragments[0].prompt.endswith("a woman waits")
    assert instructions.fragments[0].prompt.count("[Style:") == 1


def test_fragment_style_shares_render_with_prefix():
    """T-207：fragment.style 与 [Style: ...] 前缀同源（FR-025/AC-022）"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent

    agent = object.__new__(PromptConverterAgent)
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.set_style_anchor("genre", "romance")
    contract.set_style_anchor("atmosphere", "romantic")

    fragment_sequence = SimpleNamespace(
        fragments=[SimpleNamespace(id="frag_001", continuity_notes={})]
    )
    instructions = SimpleNamespace(
        fragments=[
            SimpleNamespace(
                fragment_id="frag_001",
                prompt="a woman waits",
                style="high contrast lighting, suspense",
            )
        ]
    )
    agent.prompt_process = lambda fs, ps: instructions

    agent.process_with_style_consistency(fragment_sequence, None, contract)

    fragment = instructions.fragments[0]
    assert (
        fragment.style
        == "romance, soft warm lighting, warm palette, romantic, intimate framing"
    )
    assert fragment.prompt.startswith(f"[Style: {fragment.style}] ")
    assert "high contrast lighting" not in fragment.prompt
    assert fragment.prompt.count("[Style:") == 1


def test_repair_prompts_keeps_uniform_contract_style():
    """T-207：修复风格不一致时保留同源风格，不用默认风格覆盖"""
    from penshot.neopen.agent.prompt_converter_agent import PromptConverterAgent
    from penshot.neopen.agent.quality_auditor.quality_auditor_models import (
        BasicViolation,
        RuleType,
    )

    agent = object.__new__(PromptConverterAgent)
    contract_style = "romance, soft warm lighting, warm palette, romantic"
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id=f"frag_00{index}",
                prompt="a woman waits",
                duration=3.0,
                style=contract_style,
            )
            for index in range(1, 4)
        ]
    )
    issues = [BasicViolation.create_violation(rule_type=RuleType.STYLE_INCONSISTENT)]

    agent.repair_prompts(instructions, issues, SimpleNamespace(fragments=[]))

    assert {fragment.style for fragment in instructions.fragments} == {contract_style}


def test_llm_fix_style_consistency_uses_dominant_style():
    """T-207：转换器修复风格时统一到多数片段风格，不另取默认风格"""
    from penshot.neopen.agent.prompt_converter.llm_prompt_converter import (
        LLMPromptConverter,
    )

    converter = object.__new__(LLMPromptConverter)
    dominant = "romance, soft warm lighting, warm palette"
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001", prompt="a", duration=3.0, style=dominant
            ),
            AIVideoPrompt(
                fragment_id="frag_002", prompt="b", duration=3.0, style=dominant
            ),
            AIVideoPrompt(
                fragment_id="frag_003",
                prompt="c",
                duration=3.0,
                style="high contrast lighting",
            ),
        ]
    )

    converter._fix_style_consistency(instructions)

    assert {fragment.style for fragment in instructions.fragments} == {dominant}


# ---------------------------------------------------------------------------
# 锚点召回查询
# ---------------------------------------------------------------------------


def _contract_with_anchor():
    """构造含场景与角色外观锚点的契约"""
    contract = GlobalConsistencyContract(script_id="s1", task_id="t1")
    contract.register_scene(
        SceneContract(
            scene_num=1,
            location="公寓客厅",
            time_of_day="night",
            characters_in_scene=["小明"],
        )
    )
    contract.characters["小明"].appearance_anchors = {"clothing": "黑色羽绒服"}
    return contract


def _shot_sequence():
    return ShotSequence(
        shots=[
            ShotInfo(
                id="shot_001",
                scene_id="scene_001",
                description="客厅全景",
                duration=3.0,
                main_character="小明",
            )
        ]
    )


def _fragment_sequence():
    return FragmentSequence(
        fragments=[
            VideoFragment(
                id="frag_001",
                shot_id="shot_001",
                duration=3.0,
                description="小明起身走向窗边",
                continuity_notes={"main_character": "小明"},
            )
        ]
    )


def test_build_fragment_anchor_query():
    """查询包含角色、外观锚点、场景与片段描述"""
    query = build_fragment_anchor_query(
        _fragment_sequence().fragments[0], _shot_sequence(), _contract_with_anchor()
    )
    assert "角色: 小明" in query
    assert "外观: clothing: 黑色羽绒服" in query
    assert "场景: 公寓客厅（night）" in query
    assert "片段: 小明起身走向窗边" in query


def test_build_fragment_anchor_query_without_contract():
    """无契约时不产生锚点查询（由调用方回退）"""
    assert (
        build_fragment_anchor_query(
            _fragment_sequence().fragments[0], _shot_sequence(), None
        )
        == ""
    )


def test_build_issue_anchor_query_includes_problem_and_anchors():
    """连续性问题查询在问题描述基础上补充锚点"""
    issue = SimpleNamespace(
        id="issue_1",
        description="角色服装在片段间发生突变",
        fragment_id="frag_001",
        shot_id=None,
        scene_id=None,
    )
    query = build_issue_anchor_query(
        issue,
        _fragment_sequence(),
        _shot_sequence(),
        _contract_with_anchor(),
    )
    assert "问题: 角色服装在片段间发生突变" in query
    assert "角色: 小明" in query
    assert "场景: 公寓客厅（night）" in query


# ---------------------------------------------------------------------------
# 工作流锚点召回
# ---------------------------------------------------------------------------


class _FakeKnowledgeManager:
    """记录锚点查询并返回结构化诊断的知识库桩"""

    def __init__(self, prompt_text="A young woman in a black coat sits on a sofa."):
        self.prompt_text = prompt_text
        self.queries = []
        self.kb = {
            "template_count": 3,
            "active_template_count": 3,
            "index_docs": 3,
            "legacy_templates": 0,
            "global_template_count": 0,
            "global_scripts": {},
            "has_index": True,
            "storage_dir": "memory://prompt_templates/s1",
        }

    def get_recall_diagnostics(self, script_id=None, include_global=True):
        return dict(self.kb)

    def search_similar_detailed(
        self, query, script_id=None, top_k=None, include_global=True
    ):
        self.queries.append(query)
        return (
            [
                {
                    "prompt": self.prompt_text,
                    "score": 0.9,
                    "source_scope": "script",
                    "source_script_id": script_id,
                }
            ],
            {
                "status": "hit",
                "attempted": 1,
                "retrieved": 1,
                "hits": 1,
                "local_hits": 1,
                "global_hits": 0,
                "min_score": 0.9,
                "max_score": 0.9,
                "top_k": top_k,
                "error": "",
                "kb": dict(self.kb),
            },
        )


def test_build_fragment_anchor_query_requires_anchor():
    """AC-043：无主角色且无场景锚点时不构造查询（描述不再单独兜底）"""
    fragment = VideoFragment(
        id="frag_009",
        shot_id="shot_404",
        duration=3.0,
        description="空镜头：窗帘被风吹起",
        continuity_notes={},
    )
    assert (
        build_fragment_anchor_query(fragment, _shot_sequence(), _contract_with_anchor())
        == ""
    )


def test_build_fragment_anchor_query_keeps_scene_only_anchor():
    """只有场景锚点（无主角色）仍构造查询"""
    fragment = VideoFragment(
        id="frag_009",
        shot_id="shot_001",
        duration=3.0,
        description="空镜头：窗帘被风吹起",
        continuity_notes={},
    )
    query = build_fragment_anchor_query(
        fragment, _shot_sequence(), _contract_with_anchor()
    )
    assert query.startswith("场景: 公寓客厅（night）")
    assert "角色:" not in query
    assert "片段: 空镜头：窗帘被风吹起" in query


def test_build_issue_anchor_query_keeps_problem_without_anchor():
    """无锚点的问题查询仍保留问题描述，不因收紧而丢失召回入口"""
    issue = SimpleNamespace(
        id="issue_2",
        description="道具在片段间消失",
        fragment_id="frag_404",
        shot_id=None,
        scene_id=None,
    )
    assert (
        build_issue_anchor_query(
            issue, _fragment_sequence(), _shot_sequence(), _contract_with_anchor()
        )
        == "问题: 道具在片段间消失"
    )


def test_workflow_recall_patterns_by_anchors():
    """工作流按角色/场景锚点召回提示词，并去重"""
    nodes = object.__new__(WorkflowNodes)
    nodes.knowledge_manager = _FakeKnowledgeManager()

    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = _contract_with_anchor()
    state.domain.shot_sequence = _shot_sequence()
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[
            _fragment_sequence().fragments[0],
            VideoFragment(
                id="frag_002",
                shot_id="shot_001",
                duration=3.0,
                description="小明拿起电话",
                continuity_notes={"main_character": "小明"},
            ),
        ]
    )

    patterns, anchor_recall = nodes._recall_patterns_by_anchors(state)

    assert patterns == [nodes.knowledge_manager.prompt_text]
    assert len(nodes.knowledge_manager.queries) == 2
    assert all("角色: 小明" in query for query in nodes.knowledge_manager.queries)
    assert anchor_recall["fragments"] == 2
    assert anchor_recall["queries"] == 2
    assert anchor_recall["queries_skipped"] == 0
    assert anchor_recall["attempted"] == 2
    assert anchor_recall["hits"] == 1
    assert anchor_recall["injected"] == 1
    assert anchor_recall["status"] == "hit"
    assert anchor_recall["max_score"] == 0.9


def test_workflow_recall_counts_skipped_fragments():
    """AC-043：无锚点片段计入 queries_skipped，不冒充查询数"""
    nodes = object.__new__(WorkflowNodes)
    nodes.knowledge_manager = _FakeKnowledgeManager()

    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = _contract_with_anchor()
    state.domain.shot_sequence = _shot_sequence()
    state.domain.fragment_sequence = FragmentSequence(
        fragments=[
            _fragment_sequence().fragments[0],
            VideoFragment(
                id="frag_002",
                shot_id="shot_404",
                duration=3.0,
                description="空镜头：窗帘被风吹起",
                continuity_notes={},
            ),
        ]
    )

    patterns, anchor_recall = nodes._recall_patterns_by_anchors(state)

    assert len(patterns) == 1
    assert len(nodes.knowledge_manager.queries) == 1
    assert anchor_recall["fragments"] == 2
    assert anchor_recall["queries"] == 1
    assert anchor_recall["queries_skipped"] == 1
    assert anchor_recall["attempted"] == 1


def test_workflow_recall_empty_kb_status_is_first_run():
    """AC-040：空知识库下节点统计给出 first_run_no_history 与真实 kb"""
    nodes = object.__new__(WorkflowNodes)
    manager = _FakeKnowledgeManager()
    manager.kb.update(
        {
            "template_count": 0,
            "active_template_count": 0,
            "index_docs": 0,
            "has_index": False,
        }
    )

    def _empty_search(query, script_id=None, top_k=None, include_global=True):
        manager.queries.append(query)
        return [], {
            "status": "first_run_no_history",
            "attempted": 0,
            "retrieved": 0,
            "hits": 0,
            "min_score": 0.0,
            "max_score": 0.0,
            "error": "",
            "kb": dict(manager.kb),
        }

    manager.search_similar_detailed = _empty_search
    nodes.knowledge_manager = manager

    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = _contract_with_anchor()
    state.domain.shot_sequence = _shot_sequence()
    state.domain.fragment_sequence = _fragment_sequence()

    patterns, anchor_recall = nodes._recall_patterns_by_anchors(state)

    assert patterns == []
    assert anchor_recall["status"] == "first_run_no_history"
    assert anchor_recall["queries"] == 1
    assert anchor_recall["attempted"] == 0
    assert anchor_recall["hits"] == 0
    assert anchor_recall["kb"]["template_count"] == 0
    assert anchor_recall["kb"]["has_index"] is False


def test_workflow_recall_records_retrieval_exception():
    """检索抛异常时不阻断流程，统计如实记录 retrieval_error"""
    nodes = object.__new__(WorkflowNodes)
    manager = _FakeKnowledgeManager()

    def _boom(query, script_id=None, top_k=None, include_global=True):
        raise RuntimeError("向量检索不可用")

    manager.search_similar_detailed = _boom
    nodes.knowledge_manager = manager

    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = _contract_with_anchor()
    state.domain.shot_sequence = _shot_sequence()
    state.domain.fragment_sequence = _fragment_sequence()

    patterns, anchor_recall = nodes._recall_patterns_by_anchors(state)

    assert patterns == []
    assert anchor_recall["status"] == "retrieval_error"
    assert anchor_recall["queries"] == 1
    assert anchor_recall["attempted"] == 1
    assert anchor_recall["error"] == "向量检索不可用"


def test_workflow_recall_patterns_without_contract():
    """无契约时不做锚点召回"""
    nodes = object.__new__(WorkflowNodes)
    nodes.knowledge_manager = _FakeKnowledgeManager()

    state = WorkflowState.from_raw_script("测试剧本内容")
    state.domain.contract = None
    state.domain.fragment_sequence = _fragment_sequence()

    patterns, anchor_recall = nodes._recall_patterns_by_anchors(state)

    assert patterns == []
    assert nodes.knowledge_manager.queries == []
    assert anchor_recall["queries"] == 0
    assert anchor_recall["queries_skipped"] == 1
    assert anchor_recall["attempted"] == 0
    # 未执行任何检索时不得伪造 first_run_no_history（FR-043），也不伪造 kb 快照
    assert anchor_recall["status"] == ""
    assert anchor_recall["kb"] == {}
