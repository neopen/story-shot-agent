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
      （FR-067）；写入后按迁移结果重建索引，无活跃模板时清空索引目录（FR-067）。
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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from penshot.neopen.agent.continuity_guardian.style_anchors import (
    LIGHTING_FAMILY_MARKERS,
)

if TYPE_CHECKING:
    from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager

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
EXIT_WRITE_FAILED = 3

_STYLE_PREFIX_RE = re.compile(r"\[\s*style\s*:([^\]]*)\]", re.IGNORECASE)


class MigrationError(Exception):
    """迁移前置或执行异常（不写半成品）"""


class MigrationWriteError(MigrationError):
    """写入失败且已尝试从备份回滚（FR-068 / AC-067）"""


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
    quarantined_prior_count: int = 0
    index_docs_before: int = 0
    index_docs_after: Optional[int] = None
    backup_dir: str = ""

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantine) + self.quarantined_prior_count

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


def _is_legacy_template(entry: Dict[str, Any]) -> bool:
    """判定缓存条目是否 legacy（与 PromptTemplateManager 同口径）"""
    if entry.get("legacy") is True:
        return True
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        if metadata.get("legacy") is True:
            return True
        return metadata.get("schema_version") == LEGACY_SCHEMA_VERSION
    return False


def count_index_docs(index_dir: Path) -> int:
    """统计已持久化索引的文档数（只读文件，不加载索引、不触发嵌入）"""
    vector_path = index_dir / "default__vector_store.json"
    try:
        store = json.loads(vector_path.read_text(encoding="utf-8"))
        embeddings = store.get("embedding_dict")
        if isinstance(embeddings, dict):
            return len(embeddings)
    except (OSError, json.JSONDecodeError):
        pass
    docstore_path = index_dir / "docstore.json"
    try:
        store = json.loads(docstore_path.read_text(encoding="utf-8"))
        data = store.get("docstore/data")
        if isinstance(data, dict):
            return len(data)
    except (OSError, json.JSONDecodeError):
        pass
    return 0


def _build_manager(script_dir: Path, script_id: str) -> "PromptTemplateManager":
    """按目录布局构造模板管理器（仅 apply 且存在活跃模板时使用）"""
    from penshot.neopen.client.client_factory import get_default_embedding
    from penshot.neopen.prompts.prompt_template_manager import PromptTemplateManager

    # 管理器按 <base>/prompt_templates/<script_id> 定位存储目录
    storage_dir = script_dir.parent.parent
    manager = PromptTemplateManager(
        embedding_model=get_default_embedding(),
        script_id=script_id,
        storage_dir=str(storage_dir),
    )
    expected = script_dir / INDEX_DIR_NAME
    actual = Path(manager._get_index_dir(script_id))
    if actual.resolve() != expected.resolve():
        raise MigrationError(f"存储目录布局与模板管理器不一致: {actual} != {expected}")
    return manager


def _rebuild_index(
    script_dir: Path, script_id: str, entries: Sequence[Dict[str, Any]]
) -> int:
    """从迁移后的活跃缓存重建索引（FR-067），返回重建后文档数

    无活跃模板时清空索引目录（内容已在备份中），避免残留旧索引继续参与召回。
    """
    index_dir = script_dir / INDEX_DIR_NAME
    active_entries = [entry for entry in entries if not _is_legacy_template(entry)]
    if not active_entries:
        if index_dir.is_dir():
            shutil.rmtree(index_dir)
        return 0

    manager = _build_manager(script_dir, script_id)
    rebuilt_docs = manager.rebuild_index_from_entries(script_id, active_entries)
    return rebuilt_docs


def _restore_from_backup(migration: ScriptMigration) -> bool:
    """用备份恢复单个剧本的缓存与索引（FR-068）"""
    backup_dir = Path(migration.backup_dir)
    backup_cache = backup_dir / CACHE_FILENAME
    if not backup_cache.is_file():
        return False
    shutil.copy2(backup_cache, migration.cache_path)
    index_dir = migration.cache_path.parent / INDEX_DIR_NAME
    backup_index = backup_dir / INDEX_DIR_NAME
    if index_dir.is_dir():
        shutil.rmtree(index_dir)
    if backup_index.is_dir():
        shutil.copytree(backup_index, index_dir)
    return True


def _print_rollback(
    migrations: Sequence[ScriptMigration], restored: Sequence[bool]
) -> None:
    """输出回滚结果与手动恢复指令（写入失败时调用）"""
    print("迁移写入失败，已尝试从备份回滚：", file=sys.stderr)
    for migration, ok in zip(migrations, restored):
        state = "已回滚" if ok else "回滚失败，请手工恢复"
        print(
            f"  {migration.script_id}: {state}；备份目录 {migration.backup_dir}",
            file=sys.stderr,
        )
    print("手动恢复指令（单个剧本）：", file=sys.stderr)
    for migration in migrations:
        backup_dir = Path(migration.backup_dir)
        script_dir = migration.cache_path.parent
        print(
            f'  cp "{backup_dir / CACHE_FILENAME}" '
            f'"{migration.cache_path}" && rm -rf "{script_dir / INDEX_DIR_NAME}" '
            f'&& cp -r "{backup_dir / INDEX_DIR_NAME}" '
            f'"{script_dir / INDEX_DIR_NAME}"',
            file=sys.stderr,
        )


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


def _load_quarantine_scripts(root: Path) -> Dict[str, Dict[str, Any]]:
    """读取既有隔离清单的逐剧本记录（用于重复执行时保持统计一致）"""
    path = root / QUARANTINE_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {
        script_id: record
        for script_id, record in scripts.items()
        if isinstance(record, dict)
    }


def _merge_prior_quarantine(
    migration: ScriptMigration, prior: Optional[Dict[str, Any]]
) -> None:
    """把首次迁移的隔离统计并入本次计划（AC-065：重复执行计数不变）

    隔离模板已从活跃缓存移除，重复执行时无法再次检出；模板总数改为
    “当前缓存 + 累计隔离”，守恒式对累计口径仍然成立。
    """
    if not prior:
        return
    migration.quarantined_prior_count = int(prior.get("quarantined_count") or 0)
    migration.template_count_before = (
        len(migration.cache_after) + migration.quarantined_count
    )
    if (
        migration.quarantined_count + migration.legacy_count + migration.active_count
        != migration.template_count_before
    ):
        raise MigrationError(f"累计守恒式不成立: {migration.script_id}")


def collect_migrations(
    root: Path, script_id: Optional[str] = None
) -> List[ScriptMigration]:
    """收集所有目标剧本的迁移计划（dry-run 与 apply 共用）"""
    prior_scripts = _load_quarantine_scripts(root)
    migrations: List[ScriptMigration] = []
    for name in discover_script_ids(root, script_id):
        cache_path = root / name / CACHE_FILENAME
        migration = build_script_migration(name, cache_path, _read_cache(cache_path))
        _merge_prior_quarantine(migration, prior_scripts.get(name))
        migration.index_docs_before = count_index_docs(
            cache_path.parent / INDEX_DIR_NAME
        )
        migrations.append(migration)
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
        prior = payload["scripts"].get(migration.script_id)
        prior_records = prior.get("quarantined") if isinstance(prior, dict) else None
        records = (
            prior_records if isinstance(prior_records, list) else []
        ) + migration.quarantine
        payload["scripts"][migration.script_id] = {
            "template_count_before": migration.template_count_before,
            "quarantined_count": len(records),
            "quarantined": records,
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
            "index_docs_before": migration.index_docs_before,
            "index_docs_after": migration.index_docs_after,
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
        "changed_scripts": sum(1 for migration in migrations if migration.changed),
        "scripts": scripts,
        "totals": totals,
    }


def run_migration(
    root: Path, script_id: Optional[str] = None, apply: bool = False
) -> Dict[str, Any]:
    """执行迁移：dry-run 不写文件；apply 先备份、再改写缓存并重建索引

    任一写入或重建失败都会从备份恢复已处理的剧本（FR-068），并输出回滚指令。
    """
    migrations = collect_migrations(root, script_id)
    stamp = _timestamp()
    quarantine_path = str(root / QUARANTINE_FILENAME)

    if not apply:
        return _build_report(root, migrations, True, quarantine_path, stamp)

    written: List[ScriptMigration] = []
    try:
        for migration in migrations:
            if not migration.changed:
                continue
            _backup_script(root, migration, stamp)
            written.append(migration)
            _write_json(migration.cache_path, migration.cache_after)
            migration.index_docs_after = _rebuild_index(
                migration.cache_path.parent,
                migration.script_id,
                migration.cache_after,
            )

        # 未变更的剧本不重建索引，报告中的“迁移后”沿用磁盘现状
        for migration in migrations:
            if not migration.changed:
                migration.index_docs_after = migration.index_docs_before

        if written:
            quarantine_path = _write_quarantine(root, written)
        report = _build_report(root, migrations, False, quarantine_path, stamp)
        _write_json(root / REPORT_FILENAME, report)
        return report
    except Exception as exc:
        restored = [_restore_from_backup(migration) for migration in written]
        _print_rollback(written, restored)
        raise MigrationWriteError(f"迁移写入失败（已回滚）: {exc}") from exc


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
            f"活跃 {counts['active_count']}（本次标记 {counts['legacy_marked']}），"
            f"索引 {counts['index_docs_before']} → {counts['index_docs_after']}"
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
        print(f"本次变更剧本: {report['changed_scripts']} 个")
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
    except MigrationWriteError as exc:
        print(f"迁移失败: {exc}", file=sys.stderr)
        return EXIT_WRITE_FAILED
    except MigrationError as exc:
        print(f"迁移失败: {exc}", file=sys.stderr)
        return EXIT_ERROR
    _print_summary(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
