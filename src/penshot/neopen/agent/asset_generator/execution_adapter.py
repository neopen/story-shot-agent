"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: execution_adapter.py
@Description: 资产执行器扩展点（M0.4.2）：PenShot 仅产出声明式计划，真实生图/生视频由下游适配器实现
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, List, Optional, Protocol

from penshot.logger import debug
from penshot.neopen.agent.asset_generator.asset_models import (
    AssetBinding,
    AssetManifest,
    AssetPlanDocument,
)
from penshot.neopen.client.image_generation import (
    BaseImageGenerationClient,
    ImageGenerationRequest,
)


class AssetExecutionAdapter(Protocol):
    """资产执行器协议

    PenShot 默认不实现任何真实生成；下游可注入本协议的实现，把声明式
    ``AssetPlanDocument`` 转换为带真实引用的 ``AssetManifest``，或消费
    ``RoutePlan`` 生成视频。协议只约束输入输出，不约束具体供应商。
    """

    def generate_assets(
        self, plan: AssetPlanDocument, context: Dict[str, Any]
    ) -> AssetManifest:
        """按资产计划生成静态资产，并回填 asset_id -> asset_ref 绑定"""
        ...

    def generate_videos(
        self,
        route_plan: Dict[str, Any],
        manifest: Optional[AssetManifest],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按路由计划生成视频，返回下游自定义的可序列化结果"""
        ...


class ImageClientExecutionAdapter:
    """内置可选执行器：复用现有文生图客户端生成静态资产

    仅当显式注入或配置开启文生图时才启用；默认工作流不会实例化该执行器。
    """

    source = "image_client"

    def __init__(self, client: BaseImageGenerationClient):
        self._client = client

    def generate_assets(
        self, plan: AssetPlanDocument, context: Dict[str, Any]
    ) -> AssetManifest:
        """调用文生图客户端批量生成资产，并把结果转换为资产回填清单"""
        task_id = str(context.get("task_id") or plan.task_id or "")
        requests: List[ImageGenerationRequest] = [
            ImageGenerationRequest(
                asset_id=spec.asset_id,
                prompt=spec.image_prompt,
                negative_prompt=spec.negative_prompt,
                size=spec.size,
                seed=spec.consistency.seed,
                metadata={
                    "asset_type": spec.asset_type.value,
                    "owner_name": spec.owner_name,
                    "task_id": task_id,
                    **spec.metadata,
                },
            )
            for spec in plan.assets
        ]

        results = self._client.generate_batch(requests)
        result_map = {result.asset_id: result for result in results}
        bindings: List[AssetBinding] = []
        for spec in plan.assets:
            result = result_map.get(spec.asset_id)
            if result is not None and result.success and result.image_path:
                bindings.append(
                    AssetBinding(
                        asset_id=spec.asset_id,
                        view=spec.consistency.preferred_view,
                        asset_ref=result.image_path,
                        model=result.model_name,
                        seed=spec.consistency.seed,
                        source=self.source,
                        error="",
                    )
                )
            else:
                error = result.error if result is not None else "image_generation_no_result"
                bindings.append(
                    AssetBinding(
                        asset_id=spec.asset_id,
                        source=self.source,
                        error=error,
                    )
                )

        debug(
            f"文生图执行器完成: 计划={len(plan.assets)}, "
            f"成功={sum(1 for b in bindings if b.asset_ref)}"
        )
        return AssetManifest(
            task_id=task_id,
            bindings=bindings,
        )

    def generate_videos(
        self,
        route_plan: Dict[str, Any],
        manifest: Optional[AssetManifest],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """内置执行器不负责视频生成，显式返回未支持，避免静默降级"""
        return {
            "supported": False,
            "reason": "内置文生图执行器只生成静态资产，视频生成交给下游节点",
        }
