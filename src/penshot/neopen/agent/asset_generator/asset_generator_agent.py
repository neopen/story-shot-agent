"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: asset_generator_agent.py
@Description: 资产锚点生成智能体（工作流包装：产出声明式资产计划，可选消费/产出回填清单）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from penshot.logger import debug, info, warning
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetGenerationReport,
    AssetManifest,
    AssetPlanDocument,
    AssetPromptEdit,
    AssetSpec,
    AssetStatus,
    AssetType,
)
from penshot.neopen.agent.asset_generator.character_sheet_generator import (
    build_character_sheet_specs,
)
from penshot.neopen.agent.asset_generator.execution_adapter import (
    AssetExecutionAdapter,
    ImageClientExecutionAdapter,
)
from penshot.neopen.agent.asset_generator.prop_scene_asset_generator import (
    build_prop_specs,
    build_scene_specs,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.client.image_generation import (
    BaseImageGenerationClient,
    get_default_image_client,
)


def _field(source: Any, name: str, default: Any = None) -> Any:
    """读取 dataclass / Pydantic / 字典字段"""
    if source is None:
        return default
    value = getattr(source, name, None)
    if value is None and isinstance(source, Mapping):
        value = source.get(name)
    return default if value is None else value


def _fragment_rows(fragments: Sequence[Any], shots: Any) -> List[Dict[str, str]]:
    """把片段序列归一为「片段 -> 镜头 -> 场景」扁平行"""
    if isinstance(shots, Mapping):
        shot_index = {str(key): value for key, value in shots.items()}
    else:
        shot_index = {
            str(_field(shot, "id", "")): shot
            for shot in shots or []
            if _field(shot, "id", "")
        }

    rows: List[Dict[str, str]] = []
    for fragment in fragments or []:
        fragment_id = str(
            _field(fragment, "id", "") or _field(fragment, "fragment_id", "") or ""
        )
        if not fragment_id:
            continue
        shot = shot_index.get(str(_field(fragment, "shot_id", "") or ""))
        notes = _field(fragment, "continuity_notes", {}) or {}
        main_character = _field(shot, "main_character", None) or _field(
            fragment, "main_character", None
        )
        if not main_character and isinstance(notes, Mapping):
            main_character = notes.get("main_character")
        rows.append(
            {
                "id": fragment_id,
                "scene_id": str(_field(shot, "scene_id", "") or ""),
                "location": str(_field(shot, "location", "") or ""),
                "main_character": str(main_character or "").strip(),
            }
        )
    return rows


def _scene_locations(contract: Any, parsed_script: Any) -> Dict[str, str]:
    """构建场景ID -> 地点映射；契约优先，解析结果补齐"""
    locations: Dict[str, str] = {}
    for scene in getattr(parsed_script, "scenes", None) or []:
        scene_id = str(_field(scene, "id", "") or "")
        location = str(_field(scene, "location", "") or "").strip()
        if scene_id and location:
            locations[scene_id] = location

    scenes = getattr(contract, "scenes", None) or {}
    if isinstance(scenes, Mapping):
        for scene_num, scene in scenes.items():
            location = str(getattr(scene, "location", "") or "").strip()
            if not location:
                continue
            if str(scene_num).isdigit():
                locations[f"scene_{int(scene_num):03d}"] = location
            else:
                locations[str(scene_num)] = location
    return locations


def _prop_scene_map(parsed_script: Any) -> Dict[str, set[str]]:
    """道具名 -> 出现场景ID集合（来自 global_metadata.key_props.appears_in）"""
    metadata = getattr(parsed_script, "global_metadata", None)
    result: Dict[str, set[str]] = {}
    for prop in getattr(metadata, "key_props", None) or []:
        name = str(_field(prop, "name", "") or "").strip()
        scenes = {
            str(scene_id)
            for scene_id in (_field(prop, "appears_in", None) or [])
            if scene_id
        }
        if name and scenes:
            result[name] = scenes
    return result


def _references_by_asset(route_plan: Any) -> Dict[str, List[str]]:
    """汇总路由计划中每个片段引用的资产（用于 FR-013 覆盖校验）"""
    packages = _field(route_plan, "adapted_packages", None)
    if packages is None and isinstance(route_plan, Mapping):
        packages = route_plan.get("adapted_packages")
    result: Dict[str, List[str]] = {}
    for package in packages or []:
        fragment_id = str(_field(package, "fragment_id", "") or "")
        for reference in _field(package, "references", None) or []:
            asset_id = str(_field(reference, "asset_id", "") or "")
            if fragment_id and asset_id:
                result.setdefault(asset_id, []).append(fragment_id)
    return result


def backfill_usage(
    plan: Any,
    fragments: Optional[Sequence[Any]] = None,
    shots: Any = None,
    contract: Optional[GlobalConsistencyContract] = None,
    route_plan: Any = None,
    parsed_script: Any = None,
) -> AssetPlanDocument:
    """回填资产计划的使用范围（FR-012/013、AC-012..016）

    - 角色三视图：所有以该角色为主角的片段；
    - 场景锚点：所有位于该场景地点下的片段；
    - 道具静帧：所有位于该道具 ``appears_in`` 场景下的片段；
    - ``route_plan`` 中显式引用的片段强制并入使用范围（引用集合必须是
      使用范围的子集）。

    Args:
        plan: 资产计划文档；字典输入会先校验为 ``AssetPlanDocument``
        fragments: 片段序列（``VideoFragment`` 或含 ``fragment_id`` 的提示词）
        shots: 镜头序列或 ``{shot_id: shot}`` 映射
        contract: 全局一致性契约；提供场景地点
        route_plan: 路由计划；提供每片段的资产引用
        parsed_script: 剧本解析结果；提供场景地点与道具 ``appears_in``

    Returns:
        原地回填后的资产计划文档
    """
    if not isinstance(plan, AssetPlanDocument):
        plan = AssetPlanDocument.model_validate(plan)

    rows = _fragment_rows(fragments or [], shots)
    scene_locations = _scene_locations(contract, parsed_script)
    for row in rows:
        row["location"] = scene_locations.get(row["scene_id"], "")
    fragment_order = {row["id"]: index for index, row in enumerate(rows)}
    prop_scenes = _prop_scene_map(parsed_script)
    referenced = _references_by_asset(route_plan)

    for spec in plan.assets:
        if spec.asset_type == AssetType.CHARACTER_SHEET:
            used = [
                row["id"] for row in rows if row["main_character"] == spec.owner_name
            ]
        elif spec.asset_type == AssetType.SCENE:
            used = [
                row["id"]
                for row in rows
                if row["location"] and row["location"] == spec.owner_name
            ]
        elif spec.asset_type == AssetType.PROP:
            scene_ids = prop_scenes.get(spec.owner_name, set())
            used = [row["id"] for row in rows if row["scene_id"] in scene_ids]
        else:
            used = []

        for fragment_id in referenced.get(spec.asset_id, []):
            if fragment_id in fragment_order and fragment_id not in used:
                used.append(fragment_id)

        spec.usage.fragments = sorted(
            dict.fromkeys(used),
            key=lambda fragment_id: fragment_order.get(
                fragment_id, len(fragment_order)
            ),
        )

    debug(
        "资产使用范围回填完成: "
        + ", ".join(
            f"{spec.asset_id}={len(spec.usage.fragments)}" for spec in plan.assets
        )
    )
    return plan


class AssetGeneratorAgent:
    """资产生成智能体

    职责：
    1. 从剧本解析结果与契约构建角色三视图/道具/场景资产规格，产出声明式
       ``AssetPlanDocument``（默认不触发任何外部调用）；
    2. 优先消费下游回填的 ``AssetManifest``，把 ``asset_ref`` 挂回契约；
    3. 仅在显式注入执行器且具备生成条件时调用真实生成器；
    4. 任何情况下都保留 ``pending`` 资产与 ``image_prompt``，不阻断主工作流。
    """

    def __init__(
        self,
        image_client: Optional[BaseImageGenerationClient] = None,
        output_dir: Optional[str] = None,
        execution_adapter: Optional[AssetExecutionAdapter] = None,
    ):
        self._image_client = image_client
        self._output_dir = output_dir
        self._client_resolved = image_client is not None
        self._execution_adapter = execution_adapter

    @property
    def image_client(self) -> Optional[BaseImageGenerationClient]:
        """惰性获取默认可用的文生图客户端（default -> fallback）"""
        if not self._client_resolved:
            self._image_client = get_default_image_client()
            self._client_resolved = True
            if self._image_client and self._output_dir:
                self._image_client.config.output_dir = self._output_dir
        return self._image_client

    @property
    def execution_adapter(self) -> Optional[AssetExecutionAdapter]:
        """解析执行器：显式注入优先，其次按配置启用内置文生图执行器"""
        if self._execution_adapter is not None:
            return self._execution_adapter
        client = self.image_client
        if client and client.is_configured():
            return ImageClientExecutionAdapter(client)
        return None

    def is_enabled(self) -> bool:
        """是否具备真实生成能力"""
        return self.execution_adapter is not None

    def build_specs(
        self, parsed_script: Any, contract: Optional[GlobalConsistencyContract]
    ) -> List[AssetSpec]:
        """汇总角色三视图、关键道具与场景锚点规格"""
        if contract is None:
            return []
        return [
            *build_character_sheet_specs(parsed_script, contract),
            *build_prop_specs(parsed_script, contract),
            *build_scene_specs(parsed_script, contract),
        ]

    def plan_assets(
        self,
        parsed_script: Any,
        contract: Optional[GlobalConsistencyContract],
        task_id: Optional[str] = None,
        script_id: Optional[str] = None,
    ) -> AssetPlanDocument:
        """产出声明式资产计划；无论是否启用生成都始终可用"""
        specs = self.build_specs(parsed_script, contract)
        if not specs:
            debug("无可生成的资产锚点")
        return AssetPlanDocument(
            task_id=str(task_id or getattr(contract, "task_id", "") or ""),
            script_id=str(script_id or getattr(contract, "script_id", "") or ""),
            style_anchor=dict(getattr(contract, "style_anchor", {}) or {}),
            assets=specs,
        )

    def apply_prompt_edits(
        self,
        plan: AssetPlanDocument,
        contract: Optional[GlobalConsistencyContract],
        edits: List[Any],
    ) -> List[str]:
        """把人工编辑的资产提示词写回计划与契约

        只允许修改 ``image_prompt`` / ``negative_prompt``；提示词变化后旧资产
        视为失效，状态回到 ``pending`` 并清空 ``asset_ref``，确保下游按新提示词
        重新生成。返回实际修改的 asset_id 列表。
        """
        by_id = {spec.asset_id: spec for spec in plan.assets}
        changed: List[str] = []

        for raw_edit in edits or []:
            try:
                edit = (
                    raw_edit
                    if isinstance(raw_edit, AssetPromptEdit)
                    else AssetPromptEdit.model_validate(raw_edit)
                )
            except Exception as e:
                warning(f"资产提示词编辑记录解析失败（忽略）: {e}")
                continue

            spec = by_id.get(edit.asset_id)
            if spec is None:
                warning(f"人工编辑的资产不存在，已忽略: {edit.asset_id}")
                continue

            updated = False
            if edit.image_prompt and edit.image_prompt.strip() != spec.image_prompt:
                spec.image_prompt = edit.image_prompt.strip()
                updated = True
            if (
                edit.negative_prompt is not None
                and edit.negative_prompt.strip() != spec.negative_prompt
            ):
                spec.negative_prompt = edit.negative_prompt.strip()
                updated = True

            if not updated:
                continue

            # 提示词已变化，旧资产引用必须失效，等待下游重新生成
            if spec.asset_ref:
                spec.asset_ref = ""
                spec.status = AssetStatus.PENDING

            spec.metadata.update(
                {
                    "human_edited": True,
                    "edit_source": edit.source,
                    "edit_revision": edit.revision_id,
                }
            )

            asset = (
                getattr(contract, "assets", {}).get(edit.asset_id) if contract else None
            )
            if asset is not None:
                asset.image_prompt = spec.image_prompt
                if spec.status == AssetStatus.PENDING:
                    asset.status = AssetStatus.PENDING.value
                    asset.asset_ref = ""

            changed.append(edit.asset_id)
            info(
                f"人工编辑资产提示词: {edit.asset_id} "
                f"(来源={edit.source}, 修订={edit.revision_id or '未指定'})"
            )

        return changed

    def invalidate_manifest(
        self, manifest: Optional[AssetManifest], asset_ids: List[str]
    ) -> Optional[AssetManifest]:
        """移除指定资产的回填绑定，强制下游按人工编辑后的提示词重新生成"""
        if manifest is None or not asset_ids:
            return manifest

        drop_ids = set(asset_ids)
        for asset_id in asset_ids:
            mapped = manifest.asset_id_map.get(asset_id)
            if mapped:
                drop_ids.add(mapped)

        bindings = [b for b in manifest.bindings if b.asset_id not in drop_ids]
        id_map = {
            key: value
            for key, value in manifest.asset_id_map.items()
            if key not in asset_ids and value not in drop_ids
        }
        return manifest.model_copy(
            update={"bindings": bindings, "asset_id_map": id_map}
        )

    def generate_assets(
        self,
        parsed_script: Any,
        contract: Optional[GlobalConsistencyContract],
        task_id: Optional[str] = None,
        skip_generated: bool = True,
        manifest: Optional[Any] = None,
        plan: Optional[AssetPlanDocument] = None,
        script_id: Optional[str] = None,
        prompt_edits: Optional[List[Any]] = None,
    ) -> AssetGenerationReport:
        """产出资产计划，按需消费回填清单或调用执行器，并挂载到契约

        优先级：
        1. 输入 ``manifest``：以下游回填为唯一事实来源，不重复调用生成；
        2. 无 manifest 且执行器可用：调用执行器生成，产出新的 manifest；
        3. 其余情况：仅保留 ``pending`` 计划，等待下游执行。

        传入 ``prompt_edits`` 时，先应用人工编辑，再让对应资产的旧回填绑定失效，
        确保下游按新提示词重新生成。
        """
        plan = plan or self.plan_assets(
            parsed_script, contract, task_id=task_id, script_id=script_id
        )
        changed_ids = self.apply_prompt_edits(plan, contract, prompt_edits or [])
        specs = plan.assets
        if not specs:
            return AssetGenerationReport.from_specs(
                [],
                enabled=self.execution_adapter is not None,
                mode="plan",
                plan=plan,
            )

        coerced_manifest = self._coerce_manifest(manifest)
        # 人工编辑过的资产，旧回填引用已失效，需要下游重新生成
        if coerced_manifest is not None and changed_ids:
            coerced_manifest = self.invalidate_manifest(coerced_manifest, changed_ids)
        errors: List[str] = []
        applied = 0
        mode = "plan"

        if coerced_manifest is not None:
            mode = "manifest"
            applied, errors = self._apply_manifest(specs, coerced_manifest)
            # 下游尚未回填的资产，若契约中已有可用落盘文件则标记跳过
            if skip_generated:
                specs = self._mark_existing_as_skipped(specs, contract)
        else:
            if skip_generated:
                specs = self._mark_existing_as_skipped(specs, contract)
            adapter = self.execution_adapter
            pending = [s for s in specs if s.status == AssetStatus.PENDING]
            if adapter is not None and pending:
                mode = "generated"
                exec_plan = plan.model_copy(deep=True)
                exec_plan.assets = pending
                coerced_manifest = adapter.generate_assets(
                    exec_plan,
                    {
                        "task_id": task_id or plan.task_id,
                        "script_id": script_id or plan.script_id,
                    },
                )
                applied, errors = self._apply_manifest(specs, coerced_manifest)
            else:
                warning(
                    "未提供下游资产回填清单且未启用生成执行器，"
                    "资产仅保留提示词（pending），不阻断主流程"
                )

        self._attach_to_contract(contract, specs)
        report = AssetGenerationReport.from_specs(
            specs,
            enabled=self.execution_adapter is not None,
            provider=self._provider(coerced_manifest),
            errors=errors,
            mode=mode,
            plan=plan,
            manifest=coerced_manifest,
            manifest_applied=applied,
        )
        info(
            f"资产锚点处理完成: 模式={report.mode}, 总计={report.total}, "
            f"已生成={report.generated}, 失败={report.failed}, "
            f"待生成={report.pending}, 跳过={report.skipped}"
        )
        return report

    def _coerce_manifest(self, manifest: Optional[Any]) -> Optional[AssetManifest]:
        """把字典/模型统一为 AssetManifest；非法输入仅告警不阻断"""
        if manifest is None:
            return None
        if isinstance(manifest, AssetManifest):
            return manifest
        try:
            return AssetManifest.model_validate(manifest)
        except Exception as e:
            warning(f"资产回填清单解析失败（忽略）: {e}")
            return None

    def _apply_manifest(
        self, specs: List[AssetSpec], manifest: AssetManifest
    ) -> tuple[int, List[str]]:
        """把回填清单中的绑定写回资产规格，返回应用数与失败原因"""
        applied = 0
        errors: List[str] = []
        for spec in specs:
            if spec.status == AssetStatus.SKIPPED:
                continue
            binding = manifest.get_binding(spec.asset_id)
            if binding is None:
                continue
            if binding.asset_ref:
                spec.status = AssetStatus.GENERATED
                spec.asset_ref = binding.asset_ref
                spec.metadata.update(
                    {
                        "provider": binding.source or "manifest",
                        "model_name": binding.model,
                        "checksum": binding.checksum,
                        "seed": binding.seed,
                        "revision": binding.revision,
                    }
                )
                applied += 1
            elif binding.error:
                spec.status = AssetStatus.FAILED
                errors.append(f"{spec.asset_id}: {binding.error}")
        return applied, errors

    def _provider(self, manifest: Optional[AssetManifest]) -> str:
        """解析报告中的供应商标识"""
        client = self.image_client
        if client is not None:
            return client.provider
        if manifest is not None:
            for binding in manifest.bindings:
                if binding.asset_ref and binding.source:
                    return binding.source
        return ""

    def _mark_existing_as_skipped(
        self, specs: List[AssetSpec], contract: Optional[GlobalConsistencyContract]
    ) -> List[AssetSpec]:
        """契约中已生成且落盘存在的资产不重复生成"""
        if contract is None:
            return specs
        existing = getattr(contract, "assets", {}) or {}
        for spec in specs:
            if spec.status != AssetStatus.PENDING:
                continue
            asset = existing.get(spec.asset_id)
            if (
                asset is not None
                and getattr(asset, "status", "") == AssetStatus.GENERATED.value
                and getattr(asset, "asset_ref", "")
                and os.path.exists(getattr(asset, "asset_ref", ""))
            ):
                spec.status = AssetStatus.SKIPPED
                spec.asset_ref = asset.asset_ref
        return specs

    def _attach_to_contract(
        self, contract: Optional[GlobalConsistencyContract], specs: List[AssetSpec]
    ) -> None:
        """把资产规格挂载到全局契约（覆盖同ID资产）"""
        if contract is None:
            return
        for spec in specs:
            contract.register_asset(spec.to_contract())
