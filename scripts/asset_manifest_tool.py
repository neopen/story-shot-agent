"""
@FileName: asset_manifest_tool.py
@Description: 资产回填清单工具（模板生成 / 校验 / 离线回填），不触发任何生成调用
@Author: HiPeng
@Time: 2026/11/12

用途：
    PenShot 只产出声明式资产计划（asset_plan.json），真实资产由下游生成后按
    ``AssetManifest`` 回填。本脚本提供三个子命令，让下游无需手写 JSON：

    - template：为计划中每个 asset_id 生成空绑定骨架，供人工/下游填写；
    - validate：校验填好的清单（ID 存在、不重复、引用可用、失败项带原因）；
    - apply：离线把绑定写回计划副本，供无生成环境验证回填链路。

用法：
    python scripts/asset_manifest_tool.py template asset_plan.json
    python scripts/asset_manifest_tool.py template asset_plan.json -o manifest.json
    python scripts/asset_manifest_tool.py validate asset_plan.json manifest.json
    python scripts/asset_manifest_tool.py apply asset_plan.json manifest.json
    python scripts/asset_manifest_tool.py apply asset_plan.json manifest.json -o filled.json

约束：
    - 只读输入文件，只写显式输出文件；输出路径与任一输入相同直接拒绝；
    - 不实例化任何文生图客户端，不发起网络请求（离线可用）；
    - apply 复用 validate 的判定，校验不通过时不写输出。
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from penshot.neopen.agent.asset_generator.asset_models import (
    ASSET_SCHEMA_VERSION,
    AssetBinding,
    AssetManifest,
    AssetStatus,
    AssetType,
)
from penshot.neopen.agent.asset_generator.asset_ref_validation import (
    split_ref_warnings,
    validate_asset_ref,
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ERROR = 2

TEMPLATE_OUTPUT_NAME = "asset_plan.manifest.template.json"
APPLY_OUTPUT_NAME = "asset_plan_filled.json"


class ToolError(Exception):
    """输入缺失或格式非法等无法继续的异常"""


@dataclass
class ValidationResult:
    """一次清单校验的结果；errors 非空即视为不可用"""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """是否存在阻断性错误"""
        return not self.errors


def _load_json(path: Path, label: str) -> Any:
    """读取 JSON；缺失或解析失败统一转为 ToolError"""
    if not path.is_file():
        raise ToolError(f"{label}不存在: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ToolError(f"{label}不是合法 JSON: {path} ({exc})") from exc


def load_plan(path: Path) -> Dict[str, Any]:
    """读取资产计划并做最小结构校验"""
    payload = _load_json(path, "资产计划")
    if not isinstance(payload, dict):
        raise ToolError(f"资产计划根节点必须是对象: {path}")
    assets = payload.get("assets")
    if assets is None:
        assets = []
    if not isinstance(assets, list):
        raise ToolError(f"资产计划 assets 必须是数组: {path}")
    return payload


def load_manifest(path: Path) -> AssetManifest:
    """读取回填清单并校验契约结构"""
    payload = _load_json(path, "回填清单")
    if not isinstance(payload, dict):
        raise ToolError(f"回填清单根节点必须是对象: {path}")
    try:
        return AssetManifest.model_validate(payload)
    except Exception as exc:
        raise ToolError(f"回填清单结构非法: {path} ({exc})") from exc


def _plan_asset_ids(plan: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """按出现顺序收集计划中的 asset_id，并报告缺失/重复项"""
    ids: List[str] = []
    errors: List[str] = []
    seen: set[str] = set()
    for index, spec in enumerate(plan.get("assets") or []):
        if not isinstance(spec, dict):
            errors.append(f"assets[{index}] 不是对象")
            continue
        asset_id = str(spec.get("asset_id") or "").strip()
        if not asset_id:
            errors.append(f"assets[{index}] 缺少 asset_id")
            continue
        if asset_id in seen:
            errors.append(f"资产计划中 asset_id 重复: {asset_id}")
            continue
        seen.add(asset_id)
        ids.append(asset_id)
    return ids, errors


def _canonical_id(
    asset_id: str, manifest: AssetManifest, plan_ids: Sequence[str]
) -> Optional[str]:
    """把下游实际 ID 还原为计划中的规范 asset_id"""
    if asset_id in plan_ids:
        return asset_id
    for canonical, alias in manifest.asset_id_map.items():
        if alias == asset_id:
            return canonical
    return None


def build_template(plan: Dict[str, Any]) -> Dict[str, Any]:
    """按资产计划生成回填模板（全部 asset_ref 为空，等待填写）"""
    ids, errors = _plan_asset_ids(plan)
    if errors:
        raise ToolError("；".join(errors))
    if not ids:
        raise ToolError("资产计划中没有任何资产，无需生成回填模板")

    specs = {
        str(spec.get("asset_id") or "").strip(): spec
        for spec in plan.get("assets") or []
        if isinstance(spec, dict)
    }
    bindings: List[AssetBinding] = []
    for asset_id in ids:
        spec = specs.get(asset_id) or {}
        # 角色三视图沿用优先视角，其余资产不限定视角
        view = ""
        if spec.get("asset_type") == AssetType.CHARACTER_SHEET.value:
            view = str((spec.get("consistency") or {}).get("preferred_view") or "")
        bindings.append(AssetBinding(asset_id=asset_id, view=view))

    manifest = AssetManifest(
        schema_version=str(plan.get("schema_version") or ASSET_SCHEMA_VERSION),
        task_id=str(plan.get("task_id") or ""),
        bindings=bindings,
        asset_id_map={},
    )
    return manifest.to_dict()


def validate(
    plan: Dict[str, Any], manifest: AssetManifest, strict: bool = False
) -> ValidationResult:
    """校验回填清单与资产计划是否一致、引用是否可用

    未填写的绑定默认视为“待回填”（warning），便于按需分批回填；``strict=True``
    时要求计划内每个资产都有明确结果（成功引用或失败原因）。
    """
    result = ValidationResult()
    plan_ids, plan_errors = _plan_asset_ids(plan)
    result.errors.extend(plan_errors)
    plan_id_set = set(plan_ids)

    plan_version = str(plan.get("schema_version") or "").strip()
    if plan_version and manifest.schema_version != plan_version:
        result.errors.append(
            f"schema_version 不一致: plan={plan_version} manifest={manifest.schema_version}"
        )
    plan_task = str(plan.get("task_id") or "").strip()
    if plan_task and manifest.task_id and plan_task != manifest.task_id:
        result.warnings.append(
            f"task_id 不一致: plan={plan_task} manifest={manifest.task_id}"
        )

    for canonical_key in manifest.asset_id_map:
        if canonical_key not in plan_id_set:
            result.errors.append(f"asset_id_map 键不在资产计划中: {canonical_key}")

    seen: Dict[str, int] = {}
    bound: set[str] = set()
    declared_failed: set[str] = set()
    known_ids = plan_id_set | set(manifest.asset_id_map.values())
    for index, binding in enumerate(manifest.bindings):
        label = binding.asset_id or f"bindings[{index}]"
        if not binding.asset_id:
            result.errors.append(f"bindings[{index}] 缺少 asset_id")
            continue
        canonical = _canonical_id(binding.asset_id, manifest, plan_ids)
        if canonical is None and binding.asset_id not in known_ids:
            result.errors.append(f"{label}: asset_id 不在资产计划中")
        elif canonical is not None:
            if canonical in seen:
                result.errors.append(
                    f"{label}: 与 bindings[{seen[canonical]}] 重复绑定 {canonical}"
                )
            else:
                seen[canonical] = index

        if binding.asset_ref:
            for message in validate_asset_ref(
                binding.asset_ref, binding.checksum, require_local_file=True
            ):
                result.errors.append(f"{label}: {message}")
            result.warnings.extend(
                split_ref_warnings(binding.asset_ref, binding.checksum)
            )
            if binding.error:
                result.warnings.append(
                    f"{label}: 同时包含 asset_ref 与 error，按成功处理"
                )
            if canonical is not None:
                bound.add(canonical)
        elif binding.error:
            if canonical is not None:
                declared_failed.add(canonical)
        elif strict:
            result.errors.append(f"{label}: 缺少 asset_ref（失败项必须填写 error）")
        else:
            result.warnings.append(f"{label}: 未回填（将保持 pending）")

    result.covered = [asset_id for asset_id in plan_ids if asset_id in bound]
    result.failed = [asset_id for asset_id in plan_ids if asset_id in declared_failed]
    result.missing = [
        asset_id
        for asset_id in plan_ids
        if asset_id not in bound and asset_id not in declared_failed
    ]
    if not manifest.bindings:
        result.errors.append("回填清单没有任何绑定")
    if strict and result.missing:
        result.errors.append(f"以下资产缺少回填结果: {', '.join(result.missing)}")
    return result


def apply_manifest(
    plan: Dict[str, Any], manifest: AssetManifest
) -> Tuple[Dict[str, Any], int, int]:
    """把绑定写回计划副本，返回（副本, 成功数, 失败数）

    与工作流 ``AssetGeneratorAgent._apply_manifest`` 保持同一口径：
    跳过 ``skipped`` 资产，成功项置 ``generated``，带 error 项置 ``failed``。
    """
    document = json.loads(json.dumps(plan))
    applied = 0
    failed = 0
    for spec in document.get("assets") or []:
        if not isinstance(spec, dict):
            continue
        if spec.get("status") == AssetStatus.SKIPPED.value:
            continue
        asset_id = str(spec.get("asset_id") or "").strip()
        binding = manifest.get_binding(asset_id) if asset_id else None
        if binding is None:
            continue
        if binding.asset_ref:
            spec["status"] = AssetStatus.GENERATED.value
            spec["asset_ref"] = binding.asset_ref
            metadata = dict(spec.get("metadata") or {})
            metadata.update(
                {
                    "provider": binding.source or "manifest",
                    "model_name": binding.model,
                    "checksum": binding.checksum,
                    "seed": binding.seed,
                    "revision": binding.revision,
                    "generated_at": binding.generated_at,
                }
            )
            spec["metadata"] = metadata
            applied += 1
        elif binding.error:
            spec["status"] = AssetStatus.FAILED.value
            failed += 1
    return document, applied, failed


def _write_json(path: Path, payload: Any) -> None:
    """先写临时文件再替换，避免中断留下半截 JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def _ensure_distinct(output: Path, inputs: Sequence[Path]) -> None:
    """输出不得覆盖任何输入文件"""
    target = output.resolve()
    for item in inputs:
        if target == item.resolve():
            raise ToolError(f"输出路径不能与输入相同: {output}")


def _print_validation(result: ValidationResult) -> None:
    """打印校验结论：错误到 stderr，其余到 stdout"""
    for message in result.warnings:
        print(f"警告: {message}", file=sys.stderr)
    if result.errors:
        for message in result.errors:
            print(f"错误: {message}", file=sys.stderr)
        return
    summary = f"校验通过: 已绑定 {len(result.covered)} 个资产"
    if result.failed:
        summary += f"，声明失败 {len(result.failed)} 个"
    if result.missing:
        summary += f"，待回填 {len(result.missing)} 个（{', '.join(result.missing)}）"
    print(summary)


def _cmd_template(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    output = (
        Path(args.output) if args.output else plan_path.with_name(TEMPLATE_OUTPUT_NAME)
    )
    _ensure_distinct(output, [plan_path])
    payload = build_template(plan)
    _write_json(output, payload)
    print(
        f"已生成回填模板: {output} "
        f"（{len(payload['bindings'])} 条绑定；填写 asset_ref 后运行 validate）"
    )
    return EXIT_OK


def _cmd_validate(args: argparse.Namespace) -> int:
    plan = load_plan(Path(args.plan))
    manifest = load_manifest(Path(args.manifest))
    result = validate(plan, manifest, strict=args.strict)
    _print_validation(result)
    return EXIT_OK if result.ok else EXIT_INVALID


def _cmd_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    manifest_path = Path(args.manifest)
    plan = load_plan(plan_path)
    manifest = load_manifest(manifest_path)
    result = validate(plan, manifest, strict=args.strict)
    _print_validation(result)
    if not result.ok:
        print("校验未通过，未写入输出", file=sys.stderr)
        return EXIT_INVALID

    output = (
        Path(args.output) if args.output else plan_path.with_name(APPLY_OUTPUT_NAME)
    )
    _ensure_distinct(output, [plan_path, manifest_path])
    document, applied, failed = apply_manifest(plan, manifest)
    _write_json(output, document)
    print(
        f"已回填资产计划: {output} "
        f"（成功 {applied}，失败 {failed}，未回填 {len(result.missing)}）"
    )
    return EXIT_OK


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="资产回填清单工具：生成模板、校验清单、离线回填资产计划"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template", help="按资产计划生成空回填模板")
    template.add_argument("plan", help="asset_plan.json 路径")
    template.add_argument("-o", "--output", default=None, help="输出路径")
    template.set_defaults(handler=_cmd_template)

    checker = subparsers.add_parser("validate", help="校验回填清单与资产计划")
    checker.add_argument("plan", help="asset_plan.json 路径")
    checker.add_argument("manifest", help="回填清单 JSON 路径")
    checker.add_argument(
        "--strict",
        action="store_true",
        help="要求计划内每个资产都有成功引用或失败原因（默认允许待回填）",
    )
    checker.set_defaults(handler=_cmd_validate)

    applier = subparsers.add_parser("apply", help="离线把清单写回计划副本")
    applier.add_argument("plan", help="asset_plan.json 路径")
    applier.add_argument("manifest", help="回填清单 JSON 路径")
    applier.add_argument("-o", "--output", default=None, help="输出路径")
    applier.add_argument(
        "--strict",
        action="store_true",
        help="要求计划内每个资产都有成功引用或失败原因（默认允许待回填）",
    )
    applier.set_defaults(handler=_cmd_apply)

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        return int(args.handler(args))
    except ToolError as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
