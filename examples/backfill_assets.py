"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: backfill_assets.py
@Description: 资产回填示例：把已有的本地图片 / URL 写进 asset_manifest，
              供 PenShot 在默认工作流中消费（不触发生图调用，0.4.5 任务 1）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/12

用法：
    # 1) 只为两个资产回填引用，产出 manifest
    python examples/backfill_assets.py data/asset_plan.json \
        --set char_001=assets/li_ming.png \
        --set scene_001=https://cdn.example.com/scene_001.png

    # 2) 同时离线写入计划副本，便于核对最终状态
    python examples/backfill_assets.py data/asset_plan.json \
        --set char_001=assets/li_ming.png --apply -o asset_plan_filled.json

约束：
    - 只读计划文件，只写显式输出；不实例化任何文生图客户端、不发起网络请求；
    - 本地文件自动计算 sha256（--no-checksum 可关闭），写进清单供管线二次校验。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

# scripts/ 不是包，示例通过路径加载复用的清单工具（与 tests 口径一致）
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import asset_manifest_tool as tool  # noqa: E402

from penshot.neopen.agent.asset_generator.asset_ref_validation import (  # noqa: E402
    compute_sha256,
    resolve_local_path,
)

MANIFEST_OUTPUT_NAME = "asset_plan.manifest.json"


def _parse_pairs(values: Optional[Sequence[str]], label: str) -> dict[str, str]:
    """解析 ASSET_ID=VALUE 形式的参数；格式错误立即报错"""
    pairs: dict[str, str] = {}
    for raw in values or []:
        asset_id, sep, value = str(raw).partition("=")
        if not sep or not asset_id.strip() or not value.strip():
            raise tool.ToolError(f"{label} 参数格式应为 ASSET_ID=VALUE: {raw}")
        pairs[asset_id.strip()] = value.strip()
    return pairs


def build_manifest(
    plan: dict,
    refs: dict[str, str],
    checksums: dict[str, str],
    source: str,
    generated_at: str,
    auto_checksum: bool = True,
) -> tool.AssetManifest:
    """把 ASSET_ID=VALUE 写入基于计划的回填清单，本地文件自动补校验和"""
    template = tool.AssetManifest.model_validate(tool.build_template(plan))
    bindings = []
    for binding in template.bindings:
        ref = refs.get(binding.asset_id, "")
        if not ref:
            bindings.append(binding)
            continue
        checksum = checksums.get(binding.asset_id, "")
        if not checksum and auto_checksum:
            path = resolve_local_path(ref)
            if path is not None and path.is_file():
                checksum = f"sha256:{compute_sha256(path)}"
        bindings.append(
            binding.model_copy(
                update={
                    "asset_ref": ref,
                    "checksum": checksum,
                    "source": source,
                    "generated_at": generated_at,
                }
            )
        )
    return template.model_copy(update={"bindings": bindings})


def _write_json(path: Path, payload: dict) -> None:
    """先写临时文件再替换，避免中断留下半截 JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp_path.replace(path)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把已有图片路径/URL 回填进 asset_manifest（不触发生成）"
    )
    parser.add_argument("plan", help="asset_plan.json 路径")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="ASSET_ID=REF",
        help="单个资产引用，可重复，如 char_001=assets/char_001.png",
    )
    parser.add_argument(
        "--checksum",
        action="append",
        default=[],
        metavar="ASSET_ID=SHA256",
        help="显式指定校验和，可重复；本地文件默认自动计算",
    )
    parser.add_argument("--source", default="external", help="产出该引用的来源标识")
    parser.add_argument(
        "--generated-at",
        default="",
        help="产出时间戳，默认使用当前 UTC 时间",
    )
    parser.add_argument(
        "--no-checksum", action="store_true", help="不为本地文件自动计算 sha256"
    )
    parser.add_argument(
        "--apply", action="store_true", help="校验通过后同时写出回填后的计划副本"
    )
    parser.add_argument("-o", "--output", default=None, help="输出路径")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    plan_path = Path(args.plan)
    try:
        plan = tool.load_plan(plan_path)
        refs = _parse_pairs(args.set, "--set")
        if not refs:
            raise tool.ToolError("至少提供一个 --set ASSET_ID=REF")
        checksums = _parse_pairs(args.checksum, "--checksum")
        generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()

        manifest = build_manifest(
            plan,
            refs,
            checksums,
            source=args.source,
            generated_at=generated_at,
            auto_checksum=not args.no_checksum,
        )
        result = tool.validate(plan, manifest, strict=False)
        for message in result.warnings:
            print(f"警告: {message}", file=sys.stderr)
        if not result.ok:
            for message in result.errors:
                print(f"错误: {message}", file=sys.stderr)
            print("校验未通过，未写入任何输出", file=sys.stderr)
            return tool.EXIT_INVALID

        output = (
            Path(args.output)
            if args.output
            else plan_path.with_name(MANIFEST_OUTPUT_NAME)
        )
        _write_json(output, manifest.to_dict())
        print(f"已生成回填清单: {output}（已绑定 {len(result.covered)} 个资产）")

        if args.apply:
            filled, applied, failed = tool.apply_manifest(plan, manifest)
            filled_path = (
                output.with_name("asset_plan_filled.json")
                if args.output
                else plan_path.with_name(tool.APPLY_OUTPUT_NAME)
            )
            _write_json(filled_path, filled)
            print(
                f"已写出回填后的计划副本: {filled_path}（成功 {applied}，失败 {failed}）"
            )
        return tool.EXIT_OK
    except tool.ToolError as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return tool.EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
