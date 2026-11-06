"""提示词模板元数据裁剪测试。

验证提示词原文只写入文档正文，metadata 仅保留索引字段，避免超过向量库块大小。
"""

import penshot.neopen.prompts.prompt_template_manager as manager_module
from penshot.neopen.constants.rag import MAX_METADATA_LENGTH
from penshot.neopen.knowledge.metadata_policy import (
    PROMPT_TEMPLATE_METADATA_POLICY,
)
from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager


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
