"""提示词模板元数据裁剪测试。

验证提示词原文只写入文档正文，metadata 仅保留索引字段，避免超过向量库块大小。
"""

from pathlib import Path

import yaml

import penshot.neopen.prompts.prompt_template_manager as manager_module
from penshot.neopen.constants.rag import MAX_METADATA_LENGTH
from penshot.neopen.knowledge.metadata_policy import (
    PROMPT_TEMPLATE_METADATA_POLICY,
)
from penshot.neopen.prompts.prompt_load_manager import PromptManager
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager
from penshot.neopen.shot_language import ShotLanguage

_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "penshot"
    / "neopen"
    / "prompts"
    / "v1.x"
)
_CONVERTER_FILE = "prompt_converter_prompt.yaml"


def test_prompt_template_metadata_policy():
    """元数据策略应移除提示词原文并截断长字段"""
    safe = PROMPT_TEMPLATE_METADATA_POLICY.sanitize(
        {
            "type": "wrong_type",
            "prompt": "x" * 600,
            "negative_prompt": "y" * 600,
            "scene": "z" * 400,
            "fragment_id": "f1",
            "description": "d" * 600,
            "nested": {"a": 1},
        }
    )

    assert safe["type"] == "prompt_template"
    assert "prompt" not in safe
    assert "negative_prompt" not in safe
    assert "description" not in safe
    assert "nested" not in safe
    assert safe["fragment_id"] == "f1"
    assert len(safe["scene"]) <= MAX_METADATA_LENGTH


def test_manager_doc_metadata_excludes_prompt(monkeypatch):
    """管理器写入向量库的 metadata 不应包含完整提示词"""
    captured = {}

    class FakeDocument:
        def __init__(self, text=None, metadata=None, **kwargs):
            captured["text"] = text
            captured["metadata"] = metadata

    monkeypatch.setattr(manager_module, "Document", FakeDocument)

    manager = object.__new__(PromptTemplateManager)
    manager._current_script_id = "s1"
    manager._processing_stack = set()
    manager._caches = {"s1": []}
    manager._cache_loaded = {"s1"}
    manager._indices = {}
    manager.max_metadata_length = 256
    manager.memory_manager = None
    manager.metadata_policy = PROMPT_TEMPLATE_METADATA_POLICY

    monkeypatch.setattr(manager, "_is_duplicate", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        manager, "_create_index_for_script", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(manager, "_save_cache_for_script", lambda *args, **kwargs: None)

    long_prompt = "cinematic shot, " * 60
    assert manager.add_template(
        long_prompt,
        {
            "fragment_id": "f1",
            "scene": "霓虹街道" * 80,
            "prompt": long_prompt,
            "description": "x" * 800,
            "quality_score": 90,
        },
        script_id="s1",
        save_to_memory=False,
    )

    metadata = captured["metadata"]
    assert captured["text"] == long_prompt
    assert "prompt" not in metadata
    assert "description" not in metadata
    assert metadata["type"] == "prompt_template"
    assert metadata["fragment_id"] == "f1"
    assert metadata["quality_score"] == 90
    assert len(metadata["scene"]) <= MAX_METADATA_LENGTH


def _load_converter_template(language: str) -> dict:
    """读取指定语言的提示词转换模板"""
    path = _TEMPLATE_ROOT / language / _CONVERTER_FILE
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_converter_templates_require_dialogue_language():
    """FR-084/AC-074：中英文模板版本升到 1.6，且都要求输出 dialogue_language"""
    for language in ("zh", "en"):
        data = _load_converter_template(language)
        system = data["prompt_converter_system"]["template"]
        user = data["prompt_converter_user"]["template"]

        assert data["version"] == "1.6"
        assert "dialogue_language" in system
        assert "dialogue_language" in user


def test_zh_template_requires_chinese_dialogue_and_voice():
    """FR-086：中文模板要求台词与 voice_description 使用中文"""
    user = _load_converter_template("zh")["prompt_converter_user"]["template"]

    assert "台词原文与 voice_description 必须为中文" in user
    assert "英文只允许出现在 negative_prompt、audio_style 等非台词字段" in user


def test_en_template_limits_chinese_to_comment_section():
    """FR-087：英文模板写明中文对照只进 \\n\\n 之后的注释段"""
    user = _load_converter_template("en")["prompt_converter_user"]["template"]

    assert "may only appear in the comment section after a blank line" in user
    assert "never in the dialogue description section" in user
    assert "\\n\\n" in user


def test_converter_templates_still_load_through_prompt_manager():
    """模板结构保持兼容，旧读取链路仍可召回两份模板"""
    for language in (ShotLanguage.ZH, ShotLanguage.EN):
        manager = PromptManager(language=language)
        system = manager.get_prompt("prompt_converter_system")
        user = manager.get_prompt("prompt_converter_user")

        assert "dialogue_language" in system
        assert "dialogue_language" in user
