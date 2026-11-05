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
from typing import Any, List, Optional

from penshot.logger import debug, info, warning
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetGenerationReport,
    AssetManifest,
    AssetPlanDocument,
    AssetSpec,
    AssetStatus,
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

    def generate_assets(
        self,
        parsed_script: Any,
        contract: Optional[GlobalConsistencyContract],
        task_id: Optional[str] = None,
        skip_generated: bool = True,
        manifest: Optional[Any] = None,
        plan: Optional[AssetPlanDocument] = None,
        script_id: Optional[str] = None,
    ) -> AssetGenerationReport:
        """产出资产计划，按需消费回填清单或调用执行器，并挂载到契约

        优先级：
        1. 输入 ``manifest``：以下游回填为唯一事实来源，不重复调用生成；
        2. 无 manifest 且执行器可用：调用执行器生成，产出新的 manifest；
        3. 其余情况：仅保留 ``pending`` 计划，等待下游执行。
        """
        plan = plan or self.plan_assets(
            parsed_script, contract, task_id=task_id, script_id=script_id
        )
        specs = plan.assets
        if not specs:
            return AssetGenerationReport.from_specs(
                [],
                enabled=self.execution_adapter is not None,
                mode="plan",
                plan=plan,
            )

        coerced_manifest = self._coerce_manifest(manifest)
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
