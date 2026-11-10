"""
@FileName: test_prompt_template_migration.py
@Description: 0.4.4 模板迁移脚本单测（FR-065..067 / AC-063/064）
@Author: HiPeng
@Time: 2026/11/10
"""

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "migrate_prompt_templates_044.py"
)
_SAMPLE_ROOT = (
    Path(__file__).resolve().parents[2] / "tmp" / "embedding" / "prompt_templates"
)
_SAMPLE_SCRIPT_ID = "SN2183078837410690460926"


def _load_script() -> Any:
    """按文件路径加载迁移脚本，避免依赖 scripts 成为包"""
    spec = importlib.util.spec_from_file_location(
        "migrate_prompt_templates_044", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_script()

POLLUTED_PROMPT = "特写镜头：她手持手帕和湿漉，雨水顺着发梢滑落"
CLEAN_PROMPT = (
    "[Style: soft warm lighting, muted palette] medium shot, she turns around"
)
CONFLICT_PROMPT = (
    "[Style: soft warm lighting, high contrast lighting] close-up, rainy alley"
)
SCENE_LIGHTING_PROMPT = (
    "[Style: muted palette, tense atmosphere] wide shot, "
    "natural overcast lighting and high contrast shadows"
)


def _entry(
    prompt: str,
    *,
    source: str = "convert_prompt",
    audit_status: Optional[str] = None,
    added_at: str = "2026-11-08T10:00:00",
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"fragment_id": "frag_001", "source": source}
    if audit_status is not None:
        metadata["audit_status"] = audit_status
    return {
        "prompt": prompt,
        "hash": prompt[:8],
        "metadata": metadata,
        "added_at": added_at,
    }


def _write_cache(root: Path, script_id: str, entries: List[Dict[str, Any]]) -> Path:
    script_dir = root / script_id
    script_dir.mkdir(parents=True, exist_ok=True)
    cache_path = script_dir / migration.CACHE_FILENAME
    cache_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cache_path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_detect_signatures_only_counts_style_prefix_lighting():
    """互斥打光只认风格前缀，场景自身的打光描述不算缺陷"""
    assert migration.detect_signatures({"prompt": POLLUTED_PROMPT}) == [
        migration.SIGNATURE_POLLUTION
    ]
    assert migration.detect_signatures({"prompt": CONFLICT_PROMPT}) == [
        migration.SIGNATURE_LIGHTING
    ]
    assert migration.detect_signatures({"prompt": SCENE_LIGHTING_PROMPT}) == []
    assert migration.detect_signatures({"prompt": CLEAN_PROMPT}) == []


def test_detect_signatures_can_hit_both(tmp_path):
    """同一模板可同时命中污染锚点与互斥打光，原因全部保留"""
    both = f"[Style: soft warm lighting, high contrast lighting] {POLLUTED_PROMPT}"
    assert migration.detect_signatures({"prompt": both}) == [
        migration.SIGNATURE_POLLUTION,
        migration.SIGNATURE_LIGHTING,
    ]


def test_dry_run_does_not_write_anything(tmp_path, capsys):
    """AC-063：dry-run 只输出统计，不建备份、不改缓存与索引"""
    root = tmp_path / "prompt_templates"
    entries = [
        _entry(POLLUTED_PROMPT),
        _entry(CLEAN_PROMPT),
        _entry(SCENE_LIGHTING_PROMPT),
    ]
    cache_path = _write_cache(root, "SN1", entries)
    before = cache_path.read_bytes()

    assert migration.main(["--root", str(root)]) == 0

    assert cache_path.read_bytes() == before
    assert not (root / migration.BACKUP_DIR_NAME).exists()
    assert not (root / migration.QUARANTINE_FILENAME).exists()
    assert not (root / migration.REPORT_FILENAME).exists()
    out = capsys.readouterr().out
    assert "[DRY-RUN]" in out
    assert "隔离 1" in out
    assert "legacy 2" in out
    assert "dry-run 未写入任何文件" in out


def test_apply_scopes_to_requested_script(tmp_path):
    """--script-id 只迁移目标剧本，其他目录内容与备份均不变化"""
    root = tmp_path / "prompt_templates"
    target_cache = _write_cache(
        root, "SN1", [_entry(POLLUTED_PROMPT), _entry(CLEAN_PROMPT)]
    )
    other_cache = _write_cache(root, "SN2", [_entry(POLLUTED_PROMPT)])
    other_before = other_cache.read_bytes()

    assert migration.main(["--root", str(root), "--script-id", "SN1", "--apply"]) == 0

    remaining = _read_json(target_cache)
    assert len(remaining) == 1
    assert remaining[0]["metadata"]["schema_version"] == "legacy"
    assert remaining[0]["metadata"]["audit_status"] == "unknown"
    assert other_cache.read_bytes() == other_before

    report = _read_json(root / migration.REPORT_FILENAME)
    assert list(report["scripts"]) == ["SN1"]
    quarantine = _read_json(root / migration.QUARANTINE_FILENAME)
    assert list(quarantine["scripts"]) == ["SN1"]

    backup_dirs = list((root / migration.BACKUP_DIR_NAME).glob("044_*/SN1"))
    assert len(backup_dirs) == 1
    assert (backup_dirs[0] / migration.CACHE_FILENAME).is_file()
    assert not list((root / migration.BACKUP_DIR_NAME).glob("044_*/SN2"))


def test_apply_keeps_conservation_and_writes_manifest(tmp_path):
    """FR-066/067：隔离 + legacy + 活跃 = 迁移前，隔离清单保留原始条目与原因"""
    root = tmp_path / "prompt_templates"
    entries = [
        _entry(POLLUTED_PROMPT, source="quality_audit_passed"),
        _entry(POLLUTED_PROMPT),
        _entry(CONFLICT_PROMPT),
        _entry(CLEAN_PROMPT),
        _entry(SCENE_LIGHTING_PROMPT),
    ]
    cache_path = _write_cache(root, "SN1", entries)

    assert migration.main(["--root", str(root), "--apply"]) == 0

    report = _read_json(root / migration.REPORT_FILENAME)
    counts = report["scripts"]["SN1"]
    assert counts["template_count_before"] == 5
    assert counts["quarantined_count"] == 3
    assert counts["legacy_count"] == 2
    assert counts["active_count"] == 0
    assert (
        counts["quarantined_count"] + counts["legacy_count"] + counts["active_count"]
        == counts["template_count_before"]
    )
    assert report["dry_run"] is False

    quarantine = _read_json(root / migration.QUARANTINE_FILENAME)
    records = quarantine["scripts"]["SN1"]["quarantined"]
    assert len(records) == 3
    first = records[0]
    assert first["signatures"] == [migration.SIGNATURE_POLLUTION]
    assert first["template"]["prompt"] == POLLUTED_PROMPT
    assert any("旧模板辅助判定" in reason for reason in first["reasons"])
    assert records[2]["signatures"] == [migration.SIGNATURE_LIGHTING]

    remaining = _read_json(cache_path)
    assert len(remaining) == 2
    assert {item["prompt"] for item in remaining} == {
        CLEAN_PROMPT,
        SCENE_LIGHTING_PROMPT,
    }
    assert all(
        item["metadata"]["schema_version"] == "legacy"
        and item["metadata"]["audit_status"] == "unknown"
        for item in remaining
    )


def test_apply_backs_up_cache_and_index(tmp_path):
    """FR-065：写入前备份缓存与索引目录"""
    root = tmp_path / "prompt_templates"
    cache_path = _write_cache(root, "SN1", [_entry(POLLUTED_PROMPT)])
    before = cache_path.read_bytes()
    index_dir = root / "SN1" / migration.INDEX_DIR_NAME
    index_dir.mkdir()
    (index_dir / "docstore.json").write_text("{}", encoding="utf-8")

    assert migration.main(["--root", str(root), "--apply"]) == 0

    backup_dir = next((root / migration.BACKUP_DIR_NAME).glob("044_*/SN1"))
    assert (backup_dir / migration.CACHE_FILENAME).read_bytes() == before
    assert (backup_dir / migration.INDEX_DIR_NAME / "docstore.json").is_file()


@pytest.mark.skipif(
    not (_SAMPLE_ROOT / _SAMPLE_SCRIPT_ID / migration.CACHE_FILENAME).is_file(),
    reason="缺少 0.4.3 缺陷样本缓存（tmp/embedding/prompt_templates）",
)
def test_sample_script_union_signature_counts(tmp_path):
    """AC-064 签名并集：样本剧本隔离 71 条、legacy 56 条、活跃 0，11-09 的 11 条全部在内"""
    root = tmp_path / "prompt_templates"
    source_cache = _SAMPLE_ROOT / _SAMPLE_SCRIPT_ID / migration.CACHE_FILENAME
    target_dir = root / _SAMPLE_SCRIPT_ID
    target_dir.mkdir(parents=True)
    shutil.copy2(source_cache, target_dir / migration.CACHE_FILENAME)

    report = migration.run_migration(root, script_id=_SAMPLE_SCRIPT_ID, apply=False)
    counts = report["scripts"][_SAMPLE_SCRIPT_ID]
    assert counts["template_count_before"] == 127
    assert counts["quarantined_count"] == 71
    assert counts["legacy_count"] == 56
    assert counts["active_count"] == 0
    assert (
        counts["quarantined_count"] + counts["legacy_count"] + counts["active_count"]
        == counts["template_count_before"]
    )

    planned = migration.collect_migrations(root, _SAMPLE_SCRIPT_ID)[0]
    latest_run = [
        record
        for record in planned.quarantine
        if str(record.get("added_at", "")).startswith("2026-11-09")
    ]
    assert len(latest_run) == 11
