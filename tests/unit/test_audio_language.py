"""T-010 剧本语言推断与音频语言归一测试（FR-084~087、AC-074）。

覆盖元数据/正文 CJK 占比推断优先级、中文剧本英文台词剥离与音色兜底、
英文剧本中文对照注释段约束。
"""

from types import SimpleNamespace
from typing import Optional

from penshot.neopen.agent.prompt_converter.llm_prompt_converter import (
    LLMPromptConverter,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIAudioPrompt,
    AIVideoInstructions,
    AIVideoPrompt,
)
from penshot.neopen.agent.prompt_converter.script_language import (
    detect_script_language,
    normalize_audio_language,
)


def _script(*texts: str, language: str = "") -> SimpleNamespace:
    elements = [SimpleNamespace(content=text, description=None) for text in texts]
    metadata = {"language": language} if language else {}
    return SimpleNamespace(
        metadata=metadata,
        title=None,
        scenes=[SimpleNamespace(location="", description="", elements=elements)],
        characters=[],
    )


def _audio(
    prompt: str,
    *,
    voice_type: str = "character_dialogue",
    voice_description: Optional[str] = None,
    emotion: str = "neutral",
) -> AIAudioPrompt:
    return AIAudioPrompt(
        audio_id="frag_001",
        prompt=prompt,
        voice_type=voice_type,
        voice_description=voice_description,
        emotion=emotion,
    )


def test_detect_prefers_explicit_metadata_language():
    """FR-085：元数据显式语言优先于正文占比"""
    script = _script("林晚独自站在站台等待", language="en")

    assert detect_script_language(script) == "en"


def test_detect_accepts_language_aliases():
    """元数据语言常见写法都能归一为 zh/en"""
    assert detect_script_language(_script("迟到", language="zh-CN")) == "zh"
    assert detect_script_language(_script("late", language="English")) == "en"


def test_detect_chinese_body():
    """中文正文 CJK 占比超过阈值时判定为 zh"""
    script = _script("林晚独自站在黄色安全线后等待末班车")

    assert detect_script_language(script) == "zh"


def test_detect_english_body():
    """英文正文几乎不含 CJK 时判定为 en"""
    script = _script("Lin Wan waits behind the yellow safety line for the last train")

    assert detect_script_language(script) == "en"


def test_detect_empty_script_defaults_to_zh():
    """没有正文可判断时默认中文"""
    assert detect_script_language(_script()) == "zh"


def test_detect_ambiguous_ratio_stays_chinese():
    """CJK 占比介于阈值与可忽略值之间时按默认中文处理"""
    script = _script("林" + " a" * 10)

    assert detect_script_language(script) == "zh"


def test_zh_drops_english_segment_when_chinese_translation_exists():
    """FR-086：中文剧本优先保留中文台词段，英文台词原文不残留"""
    prompt = (
        "mechanical female voice announcement: "
        "'The last train to South Station is arriving.' "
        "Echoing in the empty platform.\n\n"
        "机械女声广播：“开往南站的末班车即将进站。”声音在空旷站台中回荡。"
    )
    audio = _audio(
        prompt,
        voice_type="announcer",
        voice_description="Mechanical, clear, neutral female voice",
    )

    result = normalize_audio_language(audio, "zh")

    assert result.prompt.startswith("机械女声广播")
    assert "last train" not in result.prompt
    assert "announcement" not in result.prompt


def test_zh_strips_english_quote_without_translation():
    """没有中文对照段时按子句剔除英文台词原文，保留环境音描述"""
    prompt = (
        "low-frequency ambient hum, male voice speaking in a flat tone: "
        "'Miss, it's the last train, are you getting on?'"
    )

    result = normalize_audio_language(_audio(prompt), "zh")

    assert result.prompt == "low-frequency ambient hum"
    assert "last train" not in result.prompt


def test_zh_keeps_chinese_dialogue_quote():
    """中文台词引号句不因归一被删除"""
    prompt = "地铁站低频环境嗡鸣声，男声说道：“姑娘，末班车了，上不上？”"

    result = normalize_audio_language(_audio(prompt), "zh")

    assert result.prompt == prompt


def test_zh_maps_english_voice_description_to_chinese():
    """FR-086：英文 voice_description 按 voice_type + emotion 映射中文"""
    audio = _audio(
        "机械女声广播：“末班车即将进站。”",
        voice_type="announcer",
        voice_description="Mechanical, clear, neutral female voice with reverb",
        emotion="neutral",
    )

    result = normalize_audio_language(audio, "zh")

    assert result.voice_description == "播报，平静的语调"


def test_zh_keeps_chinese_voice_description_and_none():
    """已是中文或为空的 voice_description 不做改写"""
    kept = normalize_audio_language(
        _audio("喂", voice_description="中年男性，低沉沙哑"), "zh"
    )
    empty = normalize_audio_language(_audio("喂", voice_description=None), "zh")

    assert kept.voice_description == "中年男性，低沉沙哑"
    assert empty.voice_description is None


def test_zh_does_not_touch_non_dialogue_fields():
    """英文只允许留在 negative_prompt / audio_style 等非台词字段"""
    audio = _audio("男声说：“走吧。”", voice_description="deep male voice")
    original_negative = audio.negative_prompt
    original_style = audio.audio_style

    result = normalize_audio_language(audio, "zh")

    assert result.negative_prompt == original_negative
    assert result.audio_style == original_style


def test_en_moves_chinese_translation_after_blank_line():
    """FR-087：英文剧本中文对照只进 \\n\\n 之后的注释段"""
    prompt = "He says: 'I will wait.' 他说：“我会等。”"

    result = normalize_audio_language(_audio(prompt), "en")

    head, _, comment = result.prompt.partition("\n\n")
    assert head == "He says: 'I will wait.'"
    assert "他说：“我会等。”" in comment
    assert "他" not in head


def test_en_keeps_compliant_prompt_unchanged():
    """台词段已是英文、中文对照已在注释段时不改写"""
    prompt = "He says: 'I will wait.'\n\n他说：“我会等。”"

    result = normalize_audio_language(_audio(prompt), "en")

    assert result.prompt == prompt


def test_normalize_returns_copy_without_mutating_input():
    """归一化返回副本，调用方原对象保持原样"""
    audio = _audio(
        "male voice: 'The last train is arriving.'\n\n男声：“末班车即将进站。”",
        voice_description="deep male voice",
    )
    original_prompt = audio.prompt
    original_description = audio.voice_description

    normalize_audio_language(audio, "zh")

    assert audio.prompt == original_prompt
    assert audio.voice_description == original_description


def test_normalize_does_not_introduce_dialogue_cues():
    """FR-084：0.4.5 不引入 dialogue_cues 结构"""
    result = normalize_audio_language(_audio("喂"), "zh")

    assert "dialogue_cues" not in result.model_dump()


def _converter(script_language: str = "zh") -> LLMPromptConverter:
    """构造只带解析阶段字段的转换器，避免加载LLM与提示词模板"""
    converter = LLMPromptConverter.__new__(LLMPromptConverter)
    converter.script_language = script_language
    converter.last_audio_id = None
    return converter


def _fragment() -> SimpleNamespace:
    return SimpleNamespace(id="frag_001", duration=4.0)


def test_audio_prompt_serializes_dialogue_language():
    """FR-084：音频提示词默认 zh，且随指令集一起序列化"""
    audio = _audio("喂")
    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="frag_001", prompt="a shot", duration=4.0, audio=audio
            )
        ]
    )

    dumped = instructions.to_dict()

    assert audio.dialogue_language == "zh"
    assert dumped["fragments"][0]["audio"]["dialogue_language"] == "zh"


def test_parse_fills_missing_language_with_inferred_value():
    """T-011：LLM未返回dialogue_language时按剧本推断值补齐并归一"""
    converter = _converter("zh")
    result = {
        "audio": {
            "prompt": "male voice: 'The last train is arriving.'\n\n男声：“末班车即将进站。”"
        }
    }

    audio = converter._build_audio_prompt_from_llm_result(result, _fragment())

    assert audio is not None
    assert audio.dialogue_language == "zh"
    assert "last train" not in audio.prompt


def test_parse_uses_llm_declared_language_when_present():
    """T-011：LLM声明合法语言时以其为准，中文对照只进注释段"""
    converter = _converter("zh")
    result = {
        "audio": {
            "prompt": "He says: 'I will wait.' 他说：“我会等。”",
            "dialogue_language": "en",
        }
    }

    audio = converter._build_audio_prompt_from_llm_result(result, _fragment())

    assert audio is not None
    assert audio.dialogue_language == "en"
    head, _, comment = audio.prompt.partition("\n\n")
    assert "他" not in head
    assert "他说：“我会等。”" in comment


def test_parse_ignores_invalid_language_and_falls_back():
    """T-011：LLM返回非法语言取值时回落到剧本推断值"""
    converter = _converter("en")
    result = {
        "audio": {
            "prompt": "He says: 'Wait.'",
            "dialogue_language": "cn",
        }
    }

    audio = converter._build_audio_prompt_from_llm_result(result, _fragment())

    assert audio is not None
    assert audio.dialogue_language == "en"
