"""
@FileName: migrate_prompt_templates_044.py
@Description: 0.4.4 提示词模板一次性迁移（默认 dry-run，--apply 才写入）
@Author: HiPeng
@Time: 2026/11/10

用途：
    把 0.4.3 已入库的缺陷模板移入隔离清单、把缺少 schema_version 的旧模板
    标记为 legacy，使召回只使用符合 0.4.4 契约的活跃模板（FR-065..068）。

用法：
    python scripts/migrate_prompt_templates_044.py                    # 全库 dry-run
    python scripts/migrate_prompt_templates_044.py --script-id SID     # 单剧本 dry-run
    python scripts/migrate_prompt_templates_044.py --apply             # 全库写入
    python scripts/migrate_prompt_templates_044.py --script-id SID --apply

约束：
    - 默认 dry-run：只打印统计，不写任何文件（AC-063）；
    - 每个被写入的剧本先备份 templates_cache.json 与 index_store/ 到
      backups/044_<时间戳>/<剧本ID>/（FR-065）；
    - 隔离模板只是从活跃缓存移出并完整写入 quarantine_044.json，
      不删除底层数据（FR-066）；
    - 未被隔离且缺少 schema_version 的模板标记 legacy + audit_status=unknown
      （FR-067）；索引重建属于后续任务，本脚本不触发嵌入调用。
"""

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    LIGHTING_FAMILY_MARKERS,
)

DEFAULT_ROOT = "data/embedding/prompt_templates"
CACHE_FILENAME = "templates_cache.json"
INDEX_DIR_NAME = "index_store"
BACKUP_DIR_NAME = "backups"
QUARANTINE_FILENAME = "quarantine_044.json"
REPORT_FILENAME = "migration_044_report.json"
SCHEMA_VERSION = "0.4.4"

# FR-066 的确定性内容签名：污染锚点命中任一关键词即隔离
POLLUTION_MARKERS: Tuple[str, ...] = ("手持手帕和湿漉", "神情焦急", "湿漉]")
SIGNATURE_POLLUTION = "pollution_anchor"
SIGNATURE_LIGHTING = "lighting_conflict"
SIGNATURE_REASONS: Dict[str, str] = {
    SIGNATURE_POLLUTION: "污染锚点（情绪/动作词混入外观锚点）",
    SIGNATURE_LIGHTING: "风格前缀并存互斥打光家族",
}

# 旧模板辅助判定：仅写入原因说明，不单独构成隔离条件
LEGACY_AUX_SOURCE = "quality_audit_passed"
LEGACY_SCHEMA_VERSION = "legacy"
AUDIT_STATUS_UNKNOWN = "unknown"

EXIT_OK = 0
EXIT_ERROR = 2

_STYLE_PREFIX_RE = re.compile(r"\[\s*style\s*:([^\]]*)\]", re.IGNORECASE)


class MigrationError(Exception):
    """迁移前置或执行异常（不写半成品）"""


@dataclass
class ScriptMigration:
    """单个剧本的迁移计划与结果"""

    script_id: str
    cache_path: Path
    template_count_before: int
    cache_after: List[Dict[str, Any]] = field(default_factory=list)
    quarantine: List[Dict[str, Any]] = field(default_factory=list)
    legacy_marked: int = 0
    legacy_count: int = 0
    active_count: int = 0
    backup_dir: str = ""

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantine)

    @property
    def changed(self) -> bool:
        return bool(self.quarantine) or self.legacy_marked > 0

    def counts(self) -> Dict[str, int]:
        return {
            "template_count_before": self.template_count_before,
            "quarantined_count": self.quarantined_count,
            "legacy_count": self.legacy_count,
            "active_count": self.active_count,
        }


def _style_prefix(prompt: str) -> str:
    """取出提示词开头的 `[Style: ...]` 前缀（无则返回空串）"""
    match = _STYLE_PREFIX_RE.search(prompt or "")
    return match.group(1).strip().lower() if match else ""


def detect_signatures(entry: Dict[str, Any]) -> List[str]:
    """按 FR-066 内容签名判定缺陷模板，返回命中的签名列表

    污染锚点在全文匹配；互斥打光只检查风格前缀，避免场景自身打光误判。
    """
    prompt = str(entry.get("prompt") or "")
    signatures: List[str] = []
    if any(marker in prompt for marker in POLLUTION_MARKERS):
        signatures.append(SIGNATURE_POLLUTION)
    prefix = _style_prefix(prompt)
    families = [marker for marker in LIGHTING_FAMILY_MARKERS if marker in prefix]
    if len(families) >= 2:
        signatures.append(SIGNATURE_LIGHTING)
    return signatures


def _legacy_aux_reason(entry: Dict[str, Any]) -> str:
    """旧模板辅助判定说明（只记录原因，不参与隔离决策）"""
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    if metadata.get("source") != LEGACY_AUX_SOURCE:
        return ""
    if metadata.get("audit_status"):
        return ""
    return "旧模板辅助判定：source=quality_audit_passed 且无 audit_status"


def _read_cache(cache_path: Path) -> List[Dict[str, Any]]:
    """读取模板缓存并校验结构（列表 + 元素为对象）"""
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"读取模板缓存失败: {cache_path} ({exc})") from exc
    if not isinstance(data, list):
        raise MigrationError(f"模板缓存格式异常（应为列表）: {cache_path}")
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise MigrationError(f"模板缓存第 {index} 条不是对象: {cache_path}")
    return data


def build_script_migration(
    script_id: str, cache_path: Path, entries: Sequence[Dict[str, Any]]
) -> ScriptMigration:
    """生成单剧本迁移计划（纯内存计算，不写文件）"""
    migration = ScriptMigration(
        script_id=script_id,
        cache_path=cache_path,
        template_count_before=len(entries),
    )

    for index, entry in enumerate(entries):
        signatures = detect_signatures(entry)
        if signatures:
            metadata = entry.get("metadata")
            reasons = [SIGNATURE_REASONS[signature] for signature in signatures]
            aux_reason = _legacy_aux_reason(entry)
            if aux_reason:
                reasons.append(aux_reason)
            migration.quarantine.append(
                {
                    "index": index,
                    "hash": entry.get("hash", ""),
                    "added_at": entry.get("added_at", ""),
                    "signatures": signatures,
                    "reasons": reasons,
                    "template": entry,
                }
            )
            continue

        metadata = entry.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            entry["metadata"] = metadata
        if not metadata.get("schema_version"):
            metadata["schema_version"] = LEGACY_SCHEMA_VERSION
            metadata["audit_status"] = AUDIT_STATUS_UNKNOWN
            migration.legacy_marked += 1

        if metadata.get("schema_version") == LEGACY_SCHEMA_VERSION:
            migration.legacy_count += 1
        else:
            migration.active_count += 1
        migration.cache_after.append(entry)

    if (
        migration.quarantined_count + migration.legacy_count + migration.active_count
        != migration.template_count_before
    ):
        raise MigrationError(
            f"守恒式不成立: {migration.script_id} "
            f"{migration.quarantined_count}+{migration.legacy_count}"
            f"+{migration.active_count} != {migration.template_count_before}"
        )
    return migration


def discover_script_ids(root: Path, script_id: Optional[str]) -> List[str]:
    """列出待处理剧本目录；限定剧本不存在时报错而不是静默跳过"""
    if not root.is_dir():
        raise MigrationError(f"模板根目录不存在: {root}")
    if script_id:
        if not (root / script_id / CACHE_FILENAME).is_file():
            raise MigrationError(f"指定剧本不存在或缺少缓存: {root / script_id}")
        return [script_id]
    discovered = [
        child.name
        for child in sorted(root.iterdir())
        if child.is_dir()
        and child.name != BACKUP_DIR_NAME
        and (child / CACHE_FILENAME).is_file()
    ]
    if not discovered:
        raise MigrationError(f"模板根目录下没有可迁移剧本: {root}")
    return discovered


def collect_migrations(
    root: Path, script_id: Optional[str] = None
) -> List[ScriptMigration]:
    """收集所有目标剧本的迁移计划（dry-run 与 apply 共用）"""
    migrations: List[ScriptMigration] = []
    for name in discover_script_ids(root, script_id):
        cache_path = root / name / CACHE_FILENAME
        migrations.append(
            build_script_migration(name, cache_path, _read_cache(cache_path))
        )
    return migrations


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _backup_script(root: Path, migration: ScriptMigration, stamp: str) -> str:
    """备份单个剧本的缓存与索引目录（FR-065）"""
    target = root / BACKUP_DIR_NAME / f"044_{stamp}" / migration.script_id
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(migration.cache_path, target / CACHE_FILENAME)
    index_dir = migration.cache_path.parent / INDEX_DIR_NAME
    if index_dir.is_dir():
        shutil.copytree(index_dir, target / INDEX_DIR_NAME, dirs_exist_ok=True)
    migration.backup_dir = str(target)
    return migration.backup_dir


def _write_json(path: Path, payload: Any) -> None:
    """先写临时文件再替换，避免中断留下半截 JSON"""
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def _write_quarantine(root: Path, migrations: Sequence[ScriptMigration]) -> str:
    """写入/合并隔离清单：保留历史记录，避免重复执行时清空首次结果"""
    path = root / QUARANTINE_FILENAME
    payload: Dict[str, Any] = {"scripts": {}}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("scripts"), dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            # 旧清单损坏时以本次结果重建，原始数据仍在各自备份目录中
            payload = {"scripts": {}}

    for migration in migrations:
        if not migration.quarantine:
            continue
        payload["scripts"][migration.script_id] = {
            "template_count_before": migration.template_count_before,
            "quarantined_count": migration.quarantined_count,
            "quarantined": migration.quarantine,
        }
    payload["schema_version"] = SCHEMA_VERSION
    payload["generated_at"] = datetime.now().isoformat()
    _write_json(path, payload)
    return str(path)


def _build_report(
    root: Path,
    migrations: Sequence[ScriptMigration],
    dry_run: bool,
    quarantine_path: str,
    stamp: str,
) -> Dict[str, Any]:
    scripts: Dict[str, Dict[str, Any]] = {}
    totals = {
        "template_count_before": 0,
        "quarantined_count": 0,
        "legacy_count": 0,
        "active_count": 0,
    }
    for migration in migrations:
        counts = migration.counts()
        scripts[migration.script_id] = {
            **counts,
            "legacy_marked": migration.legacy_marked,
            "changed": migration.changed,
            "backup_dir": migration.backup_dir,
        }
        for key in totals:
            totals[key] += counts[key]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "apply_stamp": stamp,
        "root": str(root),
        "quarantine_file": quarantine_path,
        "scripts": scripts,
        "totals": totals,
    }


def run_migration(
    root: Path, script_id: Optional[str] = None, apply: bool = False
) -> Dict[str, Any]:
    """执行迁移：dry-run 不写文件，apply 先备份再改写缓存并落盘清单与报告"""
    migrations = collect_migrations(root, script_id)
    stamp = _timestamp()
    quarantine_path = str(root / QUARANTINE_FILENAME)

    if not apply:
        return _build_report(root, migrations, True, quarantine_path, stamp)

    written = [migration for migration in migrations if migration.changed]
    for migration in written:
        _backup_script(root, migration, stamp)
        _write_json(migration.cache_path, migration.cache_after)

    if written:
        quarantine_path = _write_quarantine(root, written)
    report = _build_report(root, migrations, False, quarantine_path, stamp)
    _write_json(root / REPORT_FILENAME, report)
    return report


def _print_summary(report: Dict[str, Any]) -> None:
    """打印逐剧本与合计统计（dry-run / apply 共用）"""
    mode = "DRY-RUN" if report["dry_run"] else "APPLY"
    scripts = report["scripts"]
    print(f"[{mode}] 共 {len(scripts)} 个剧本，根目录: {report['root']}")
    for script_id, counts in scripts.items():
        print(
            f"  {script_id}: 模板 {counts['template_count_before']} → "
            f"隔离 {counts['quarantined_count']} / "
            f"legacy {counts['legacy_count']} / "
            f"活跃 {counts['active_count']}（本次标记 {counts['legacy_marked']}）"
        )
    totals = report["totals"]
    print(
        f"合计: 模板 {totals['template_count_before']} → "
        f"隔离 {totals['quarantined_count']} / "
        f"legacy {totals['legacy_count']} / 活跃 {totals['active_count']}"
    )
    if report["dry_run"]:
        print("dry-run 未写入任何文件；核对无误后加 --apply 执行写入。")
    else:
        print(f"报告: {report['root']}/{REPORT_FILENAME}")
        print(f"隔离清单: {report['quarantine_file']}")


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="0.4.4 提示词模板迁移：隔离 0.4.3 缺陷模板并标记 legacy 旧模板"
    )
    parser.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help=f"提示词模板根目录（默认：{DEFAULT_ROOT}）",
    )
    parser.add_argument(
        "--script-id",
        default=None,
        help="只处理指定剧本目录（默认处理全部剧本）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行写入（默认 dry-run，只输出统计）",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_migration(
            Path(args.root), script_id=args.script_id, apply=args.apply
        )
    except MigrationError as exc:
        print(f"迁移失败: {exc}", file=sys.stderr)
        return EXIT_ERROR
    _print_summary(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
