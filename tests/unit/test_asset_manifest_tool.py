"""
@FileName: test_asset_manifest_tool.py
@Description: 资产回填清单工具单测（模板生成 / 校验 / 离线回填）
@Author: HiPeng
@Time: 2026/11/12
"""

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "asset_manifest_tool.py"
)


def _load_script() -> Any:
    """按文件路径加载脚本，避免依赖 scripts 成为包"""
    spec = importlib.util.spec_from_file_location("asset_manifest_tool", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_script()


def _plan() -> Dict[str, Any]:
    """最小资产计划：1 个角色 + 1 个道具 + 1 个场景"""
    return {
        "schema_version": "0.4.4",
        "task_id": "T1",
        "script_id": "S1",
        "assets": [
            {
                "asset_id": "char_001",
                "asset_type": "character_sheet",
                "owner_name": "李明",
                "image_prompt": "portrait of 李明",
                "status": "pending",
                "asset_ref": "",
                "consistency": {"preferred_view": "front"},
                "metadata": {"role": "identity_anchor"},
            },
            {
                "asset_id": "prop_001",
                "asset_type": "prop",
                "owner_name": "便利贴",
                "image_prompt": "product still of 便利贴",
                "status": "pending",
                "asset_ref": "",
            },
            {
                "asset_id": "scene_001",
                "asset_type": "scene",
                "owner_name": "教室",
                "image_prompt": "establishing shot of 教室",
                "status": "pending",
                "asset_ref": "",
            },
        ],
    }


def _write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _image(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"fake-image")
    return str(path)


def _binding(asset_id: str, asset_ref: str = "", error: str = "") -> Dict[str, Any]:
    return {"asset_id": asset_id, "asset_ref": asset_ref, "error": error}


def _manifest(bindings: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema_version": "0.4.4",
        "task_id": "T1",
        "bindings": bindings,
        "asset_id_map": {},
    }
    payload.update(kwargs)
    return payload


def test_template_covers_all_assets(tmp_path):
    """模板为每个资产生成一条空绑定，角色带优先视角"""
    template = tool.build_template(_plan())

    assert template["schema_version"] == "0.4.4"
    assert template["task_id"] == "T1"
    assert template["asset_id_map"] == {}
    assert [b["asset_id"] for b in template["bindings"]] == [
        "char_001",
        "prop_001",
        "scene_001",
    ]
    assert all(b["asset_ref"] == "" for b in template["bindings"])
    assert template["bindings"][0]["view"] == "front"
    assert template["bindings"][1]["view"] == ""


def test_template_rejects_plan_without_assets():
    """空计划无法生成有意义的模板"""
    with pytest.raises(tool.ToolError):
        tool.build_template({"schema_version": "0.4.4", "assets": []})


def test_validate_accepts_filled_manifest(tmp_path):
    """本地文件与 URL 两种引用均可通过校验"""
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                _binding("char_001", _image(tmp_path, "char_001.png")),
                _binding("prop_001", "https://example.com/prop_001.png"),
                _binding("scene_001", _image(tmp_path, "scene_001.png")),
            ]
        )
    )

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == ["char_001", "prop_001", "scene_001"]
    assert result.missing == []


def test_validate_accepts_failed_binding_with_error(tmp_path):
    """失败项只要带 error 即可通过；未出现的资产计入待回填"""
    manifest = tool.AssetManifest.model_validate(
        _manifest([_binding("char_001", error="provider_timeout")])
    )

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == []
    assert result.failed == ["char_001"]
    assert result.missing == ["prop_001", "scene_001"]


def test_validate_allows_partially_filled_template(tmp_path):
    """整份模板只填两个资产时应通过，其余记为待回填"""
    template = tool.build_template(_plan())
    refs = {
        "char_001": _image(tmp_path, "char_001.png"),
        "scene_001": "https://example.com/scene_001.png",
    }
    for binding in template["bindings"]:
        binding["asset_ref"] = refs.get(binding["asset_id"], "")
    manifest = tool.AssetManifest.model_validate(template)

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == ["char_001", "scene_001"]
    assert result.missing == ["prop_001"]
    assert any("未回填" in message for message in result.warnings)


def test_validate_strict_requires_every_asset_resolved(tmp_path):
    """--strict 下计划内每个资产都必须有回填结果"""
    manifest = tool.AssetManifest.model_validate(
        _manifest([_binding("char_001", _image(tmp_path, "c.png"))])
    )

    result = tool.validate(_plan(), manifest, strict=True)

    assert not result.ok
    assert any("缺少回填结果" in message for message in result.errors)


def test_validate_rejects_unknown_asset_id(tmp_path):
    """绑定引用了计划里不存在的 asset_id"""
    manifest = tool.AssetManifest.model_validate(
        _manifest([_binding("char_999", _image(tmp_path, "x.png"))])
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("char_999" in message for message in result.errors)


def test_validate_rejects_duplicate_bindings(tmp_path):
    """同一资产不得重复绑定"""
    ref = _image(tmp_path, "char_001.png")
    manifest = tool.AssetManifest.model_validate(
        _manifest([_binding("char_001", ref), _binding("char_001", ref)])
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("重复绑定" in message for message in result.errors)


def test_validate_requires_ref_or_error_strict():
    """空绑定在 strict 模式下视为未完成"""
    manifest = tool.AssetManifest.model_validate(_manifest([_binding("char_001")]))

    result = tool.validate(_plan(), manifest, strict=True)

    assert not result.ok
    assert any("缺少 asset_ref" in message for message in result.errors)


def test_validate_rejects_missing_local_file(tmp_path):
    """本地路径不存在时不可通过（模板默认值常踩此坑）"""
    manifest = tool.AssetManifest.model_validate(
        _manifest([_binding("char_001", str(tmp_path / "missing.png"))])
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("asset_ref 不可用" in message for message in result.errors)


def test_validate_rejects_schema_version_mismatch(tmp_path):
    """清单与计划的契约版本不一致"""
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [_binding("char_001", _image(tmp_path, "c.png"))],
            schema_version="0.4.3",
        )
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("schema_version" in message for message in result.errors)


def test_validate_accepts_alias_mapping(tmp_path):
    """下游改名后按 asset_id_map 还原规范 ID"""
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [_binding("downstream_42", _image(tmp_path, "c.png"))],
            asset_id_map={"char_001": "downstream_42"},
        )
    )

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == ["char_001"]


def test_apply_writes_generated_status_only_for_bound_assets(tmp_path):
    """回填只改命中的资产，未绑定资产保持 pending"""
    plan = _plan()
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                _binding(
                    "char_001",
                    _image(tmp_path, "c.png"),
                ),
                _binding("scene_001", "https://example.com/scene_001.png"),
            ]
        )
    )

    document, applied, failed = tool.apply_manifest(plan, manifest)
    by_id = {spec["asset_id"]: spec for spec in document["assets"]}

    assert (applied, failed) == (2, 0)
    assert by_id["char_001"]["status"] == "generated"
    assert by_id["char_001"]["asset_ref"].endswith("c.png")
    assert by_id["char_001"]["metadata"]["provider"] == "manifest"
    assert by_id["scene_001"]["status"] == "generated"
    assert by_id["prop_001"]["status"] == "pending"
    # 输入计划本身不被修改
    assert plan["assets"][0]["status"] == "pending"
    assert plan["assets"][0]["asset_ref"] == ""


def test_apply_marks_failed_binding(tmp_path):
    """带 error 的绑定写回 failed，且不改动 skipped 资产"""
    plan = _plan()
    plan["assets"][1]["status"] = "skipped"
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                _binding("char_001", error="provider_timeout"),
                _binding("prop_001", _image(tmp_path, "p.png")),
            ]
        )
    )

    document, applied, failed = tool.apply_manifest(plan, manifest)
    by_id = {spec["asset_id"]: spec for spec in document["assets"]}

    assert (applied, failed) == (0, 1)
    assert by_id["char_001"]["status"] == "failed"
    assert by_id["prop_001"]["status"] == "skipped"
    assert by_id["prop_001"]["asset_ref"] == ""


def test_cli_validate_exit_codes(tmp_path):
    """校验失败退出码为 1，通过为 0"""
    plan_path = _write(tmp_path / "asset_plan.json", _plan())
    bad_path = _write(
        tmp_path / "bad.json",
        _manifest([_binding("char_001", str(tmp_path / "missing.png"))]),
    )
    good_path = _write(
        tmp_path / "good.json",
        _manifest([_binding("char_001", _image(tmp_path, "c.png"))]),
    )

    assert tool.main(["validate", str(plan_path), str(bad_path)]) == 1
    assert tool.main(["validate", str(plan_path), str(good_path)]) == 0


def test_cli_apply_writes_plan_copy_and_keeps_input(tmp_path):
    """apply 只写输出副本，输入计划保持原样"""
    plan_path = _write(tmp_path / "asset_plan.json", _plan())
    manifest_path = _write(
        tmp_path / "manifest.json",
        _manifest(
            [
                _binding("char_001", _image(tmp_path, "c.png")),
                _binding("scene_001", "https://example.com/s.png"),
            ]
        ),
    )
    output_path = tmp_path / "filled.json"

    assert (
        tool.main(
            [
                "apply",
                str(plan_path),
                str(manifest_path),
                "-o",
                str(output_path),
            ]
        )
        == 0
    )

    filled = json.loads(output_path.read_text(encoding="utf-8"))
    by_id = {spec["asset_id"]: spec for spec in filled["assets"]}
    assert by_id["char_001"]["status"] == "generated"
    assert by_id["scene_001"]["asset_ref"] == "https://example.com/s.png"
    assert by_id["prop_001"]["status"] == "pending"

    original = json.loads(plan_path.read_text(encoding="utf-8"))
    assert all(spec["status"] == "pending" for spec in original["assets"])


def test_cli_apply_refuses_invalid_manifest(tmp_path):
    """校验不通过时不产生输出文件"""
    plan_path = _write(tmp_path / "asset_plan.json", _plan())
    manifest_path = _write(
        tmp_path / "manifest.json",
        _manifest([_binding("char_001", str(tmp_path / "missing.png"))]),
    )
    output_path = tmp_path / "filled.json"

    code = tool.main(
        ["apply", str(plan_path), str(manifest_path), "-o", str(output_path)]
    )

    assert code == 1
    assert not output_path.exists()


def test_cli_apply_refuses_to_overwrite_input(tmp_path):
    """输出路径与输入相同直接失败，输入不被改写"""
    plan_path = _write(tmp_path / "asset_plan.json", _plan())
    manifest_path = _write(
        tmp_path / "manifest.json",
        _manifest([_binding("char_001", _image(tmp_path, "c.png"))]),
    )

    code = tool.main(
        ["apply", str(plan_path), str(manifest_path), "-o", str(plan_path)]
    )

    assert code == 2
    original = json.loads(plan_path.read_text(encoding="utf-8"))
    assert original["assets"][0]["status"] == "pending"


def test_cli_template_default_output_path(tmp_path):
    """未指定 -o 时写到计划同目录的模板文件名"""
    plan_path = _write(tmp_path / "asset_plan.json", _plan())

    assert tool.main(["template", str(plan_path)]) == 0

    output = plan_path.with_name("asset_plan.manifest.template.json")
    assert output.is_file()
    template = json.loads(output.read_text(encoding="utf-8"))
    assert len(template["bindings"]) == 3


def test_cli_missing_plan_reports_error(tmp_path):
    """输入文件缺失属于工具错误，退出码 2"""
    manifest_path = _write(tmp_path / "manifest.json", _manifest([]))

    code = tool.main(["validate", str(tmp_path / "nope.json"), str(manifest_path)])

    assert code == 2


def test_validate_accepts_v3_assets_alias(tmp_path):
    """v3 清单用 assets 字段、script_id、generated_at，且仅回填部分资产"""
    manifest = tool.AssetManifest.model_validate(
        {
            "task_id": "T1",
            "script_id": "S1",
            "generated_at": "2026-11-12T15:00:00Z",
            "assets": [
                {
                    "asset_id": "char_001",
                    "asset_ref": _image(tmp_path, "char_001.png"),
                    "generated_at": "2026-11-12T15:00:00Z",
                    "source": "external",
                },
                {
                    "asset_id": "scene_001",
                    "asset_ref": "https://example.com/scene_001.png",
                    "source": "external",
                },
            ],
        }
    )

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == ["char_001", "scene_001"]
    assert result.missing == ["prop_001"]


def test_validate_accepts_matching_checksum(tmp_path):
    """sha256 一致时通过校验"""
    import hashlib

    image = Path(_image(tmp_path, "char_001.png"))
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                {
                    "asset_id": "char_001",
                    "asset_ref": str(image),
                    "checksum": f"sha256:{digest}",
                }
            ]
        )
    )

    result = tool.validate(_plan(), manifest)

    assert result.ok, result.errors
    assert result.covered == ["char_001"]


def test_validate_rejects_checksum_mismatch(tmp_path):
    """校验和不一致时不可通过"""
    image = _image(tmp_path, "char_001.png")
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                {
                    "asset_id": "char_001",
                    "asset_ref": image,
                    "checksum": "sha256:" + "0" * 64,
                }
            ]
        )
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("校验和不匹配" in message for message in result.errors)


def test_validate_rejects_missing_file_uri(tmp_path):
    """显式 file:// 缺失时不可通过（裸路径仍兼容下游自定义标识）"""
    manifest = tool.AssetManifest.model_validate(
        _manifest(
            [
                {
                    "asset_id": "char_001",
                    "asset_ref": (tmp_path / "missing.png").as_uri(),
                }
            ]
        )
    )

    result = tool.validate(_plan(), manifest)

    assert not result.ok
    assert any("asset_ref 不可用" in message for message in result.errors)
