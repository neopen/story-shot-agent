"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 08_asset_handoff.py
@Description: 下游节点接入示例：消费 asset_plan / route_plan references，
              或将生成的 asset_manifest 回填给 PenShot。
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/5
"""

import json

from penshot.neopen.agent.asset_generator import (
    AssetBinding,
    AssetGeneratorAgent,
    AssetManifest,
    backfill_usage,
)
from penshot.neopen.agent.continuity_guardian.consistency_contract import (
    GlobalConsistencyContract,
)
from penshot.neopen.agent.model_adapter import (
    RouteDecision,
    RoutePlan,
    adapt_instructions,
    apply_image_to_video_routing,
    get_capability,
)
from penshot.neopen.agent.prompt_converter.prompt_converter_models import (
    AIVideoInstructions,
    AIVideoPrompt,
)


def build_demo_output() -> dict:
    """
    构造一份与真实任务一致的输出（离线、不调用 LLM / 图片 / 视频 API）。

    真实任务中这些字段由 GENERATE_ASSETS 节点和 convert_prompt 节点写入
    result.data.asset_plan、result.data.instructions.route_plan。
    """
    contract = GlobalConsistencyContract(script_id="demo-script", task_id="demo-task")
    contract.style_anchor = {"genre": "neo-noir", "description": "cinematic, moody lighting"}
    contract.register_character("林然", 1, "他穿着黑色西装，戴金丝眼镜")

    instructions = AIVideoInstructions(
        fragments=[
            AIVideoPrompt(
                fragment_id="f1",
                prompt="Lin Ran walks into the rainy alley",
                duration=3.0,
                main_character="林然",
                style="cinematic",
            )
        ]
    )
    instructions.metadata["video_model"] = "runway_gen2"

    agent = AssetGeneratorAgent()
    plan = agent.plan_assets(
        None, contract, task_id="demo-task", script_id="demo-script"
    )
    # 默认没有执行器，只把 pending 资产计划挂到契约，不生成真实图片
    agent.generate_assets(None, contract, task_id="demo-task", plan=plan)

    packages = adapt_instructions(instructions, "runway_gen2")
    apply_image_to_video_routing(packages, instructions, contract, None)
    route_plan = RoutePlan(
        source_model="runway_gen2",
        decisions=[
            RouteDecision(
                fragment_id=pkg.fragment_id,
                target_model=pkg.target_model,
                reason="m0.4.2_image_to_video"
                if pkg.mode.value == "image_to_video"
                else "m0.4.0_inline",
                mode=pkg.mode,
                asset_ref=pkg.asset_ref,
                capability=get_capability(pkg.target_model),
            )
            for pkg in packages
        ],
        adapted_packages=packages,
    )

    instructions.route_plan = route_plan.model_dump(mode="json")

    # 回填 usage.fragments：路由显式引用的片段会并入使用范围，
    # 下游据此按片段按需生成，质量审查也据此校验引用声明（FR-063）
    plan = backfill_usage(
        plan,
        fragments=instructions.fragments,
        contract=contract,
        route_plan=instructions.route_plan,
    )
    instructions.asset_plan = plan.to_dict()

    return {
        "success": True,
        "data": {
            "asset_plan": plan.to_dict(),
            "asset_manifest": None,
            "instructions": instructions.to_dict(),
        },
    }


def resolve_downstream_ref(
    asset_id: str,
    manifest: dict,
    generated: dict[str, str],
) -> str | None:
    """
    下游解析规范 asset_id -> 真实图片引用。

    优先使用回填清单的 asset_id_map（下游可能改名），
    其次使用本地刚生成的引用。
    """
    downstream_id = manifest.get("asset_id_map", {}).get(asset_id, asset_id)
    for binding in manifest.get("bindings", []):
        if binding.get("asset_id") == downstream_id:
            return binding.get("asset_ref")
    return generated.get(asset_id)


class StubImageService:
    """占位生图服务：真实场景替换为 Flux / Ideogram / 自建服务"""

    model_name = "stub-image"

    def generate(self, asset: dict) -> str:
        view = asset["consistency"]["preferred_view"]
        return f"/cdn/{asset['asset_id']}_{view}.png"


class StubVideoService:
    """占位视频服务：真实场景替换为 Runway / Kling / Sora"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def text_to_video(self, prompt: str) -> None:
        self.calls.append({"mode": "text_to_video", "prompt": prompt})

    def image_to_video(self, prompt: str, first_frame: str, duration: float) -> None:
        self.calls.append(
            {
                "mode": "image_to_video",
                "prompt": prompt,
                "first_frame": first_frame,
                "duration": duration,
            }
        )


def downstream_node(
    output: dict, image_service: StubImageService, video_service: StubVideoService
) -> dict:
    """
    模式 A：直接消费本次输出，生成资产后调用视频服务，再把清单回填给 PenShot。

    Returns:
        dict: 可提交给 PenShot 的 asset_manifest
    """
    data = output["data"]
    instructions = data["instructions"]
    plan = data.get("asset_plan") or instructions.get("asset_plan")
    manifest = data.get("asset_manifest") or instructions.get("asset_manifest") or {}

    if not plan:
        raise ValueError("输出中缺少 asset_plan，无法生成资产")

    # 1) 只为尚未回填的资产生成图片
    generated: dict[str, str] = {}
    bindings: list[AssetBinding] = []
    asset_id_map: dict[str, str] = {}

    for asset in plan["assets"]:
        canonical_id = asset["asset_id"]
        downstream_id = f"ds_{canonical_id}"
        asset_id_map[canonical_id] = downstream_id

        existing = resolve_downstream_ref(canonical_id, manifest, {})
        if existing:
            generated[canonical_id] = existing
            continue
        if asset["status"] != "pending":
            continue

        ref = image_service.generate(asset)
        generated[canonical_id] = ref
        bindings.append(
            AssetBinding(
                asset_id=downstream_id,
                view=asset["consistency"]["preferred_view"],
                asset_ref=ref,
                model=image_service.model_name,
                source="downstream_image_service",
                revision=1,
            )
        )

    new_manifest = AssetManifest(
        task_id=plan["task_id"],
        bindings=bindings,
        asset_id_map=asset_id_map,
    ).to_dict()

    # 2) 按 references 调用视频服务
    for package in instructions["route_plan"]["adapted_packages"]:
        first_ref = next(
            (ref for ref in package.get("references", []) if ref.get("as_first_frame")),
            None,
        )
        if first_ref is None:
            video_service.text_to_video(package["prompt"])
            continue

        resolved = resolve_downstream_ref(
            first_ref["asset_id"], new_manifest, generated
        )
        if not resolved:
            # 资产未就绪时保留声明式提示词，交给下游继续生成
            video_service.text_to_video(package["prompt"])
            continue

        video_service.image_to_video(
            prompt=package["prompt"],
            first_frame=resolved,
            duration=package["duration"],
        )

    return new_manifest


def main() -> None:
    output = build_demo_output()
    plan = output["data"]["asset_plan"]
    package = output["data"]["instructions"]["route_plan"]["adapted_packages"][0]

    print("== PenShot 输出的资产提示词 ==")
    for asset in plan["assets"]:
        print(
            f"- {asset['asset_id']} [{asset['status']}] "
            f"usage.fragments={asset['usage']['fragments']} "
            f"{asset['image_prompt'][:70]}..."
        )

    print("\n== 片段引用（只有 as_first_frame=true 的引用用于首帧）==")
    print(json.dumps(package["references"], ensure_ascii=False, indent=2))
    print("first_frame_instruction:", package["first_frame_instruction"][:90] + "...")

    video_service = StubVideoService()
    manifest = downstream_node(output, StubImageService(), video_service)

    print("\n== 下游调用视频服务 ==")
    print(json.dumps(video_service.calls, ensure_ascii=False, indent=2))

    print("\n== 回填清单 asset_manifest ==")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    print(
        "\n模式 B：将上面的 manifest 作为 asset_manifest 参数重新提交，"
        "PenShot 会自动解析引用：\n"
        "  agent.breakdown_script(script_text, asset_manifest=manifest)"
    )


if __name__ == "__main__":
    main()
