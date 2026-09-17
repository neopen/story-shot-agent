"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 02_pipeline_stages_demo.py
@Description: 工作流阶段离线演示：读取各阶段样例产物并映射到 PipelineNode
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:50
"""
import argparse
import json
from pathlib import Path
from typing import Optional

# 纯标准库实现，无网络、无 LLM key 也可运行：
#   python examples/workflow/02_pipeline_stages_demo.py
# data/results/*.json 是历史阶段产物样例；本脚本通用读取，不承诺与最新 schema 逐字段一致。
# 加 --with-penshot 可在装有 penshot 的环境里对照真实 PipelineNode/PipelineState 枚举。

RESULTS_DIR = Path(__file__).resolve().parents[1] / "data" / "results"

# 阶段产物文件 → 工作流节点。节点枚举值来源：src/penshot/neopen/agent/workflow/workflow_models.py。
STAGE_FILES = [
    ("script_parser_result.json", "PARSE_SCRIPT", "剧本解析（解析出场景/角色/对白）"),
    ("shot_segmenter_result.json", "SEGMENT_SHOT", "镜头拆分（叙事单元→镜头序列）"),
    ("video_splitter_result.json", "SPLIT_VIDEO", "片段分隔（镜头→≤5s 片段）"),
    ("prompt_converter_result.json", "CONVERT_PROMPT", "指令转换（片段→AI 视频 prompt）"),
    ("quality_auditor_result.json", "AUDIT_QUALITY", "质量审查（格式/时长/内容合规）"),
]

# PipelineState 源码值（workflow_models.py）：决策函数返回值，用于条件路由。
PIPELINE_STATES = {
    "success": "完全成功，进入下一阶段",
    "valid": "验证通过（有小问题），继续",
    "needs_repair": "需要修复/调整后重试本阶段",
    "needs_retry": "需要重试本阶段",
    "needs_human": "重试超限/严重问题，需要人工干预",
    "failed": "一般失败",
    "abort": "中止整个流程",
}

# 质量审查状态 → PipelineState 的映射（decide_after_audit，见 workflow_decision.py）。
AUDIT_TO_STATE = {
    "passed": "SUCCESS",
    "minor_issues": "VALID",
    "moderate_issues": "NEEDS_REPAIR",
    "major_issues": "NEEDS_REPAIR",
    "critical_issues": "NEEDS_RETRY / NEEDS_HUMAN（取决于剩余重试）",
    "needs_human": "NEEDS_HUMAN",
}


def _truncate(value, limit: int = 40) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_json_summary(data, max_depth: int = 2) -> None:
    """按缩进树打印 JSON 概要（dict 逐键，list 只展开首元素）。"""

    def walk(obj, indent: int, depth: int) -> None:
        pad = "  " * indent
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    if depth < max_depth:
                        kind = f"dict[{len(value)}]" if isinstance(value, dict) else f"list[{len(value)}]"
                        print(f"{pad}{key}: {kind}")
                        walk(value, indent + 1, depth + 1)
                    else:
                        kind = f"dict[{len(value)}]" if isinstance(value, dict) else f"list[{len(value)}]"
                        print(f"{pad}{key}: {kind}")
                else:
                    print(f"{pad}{key}: {_truncate(value)}")
        elif isinstance(obj, list):
            if obj and isinstance(obj[0], (dict, list)):
                print(f"{pad}[0]")
                walk(obj[0], indent + 1, depth + 1)
            else:
                print(f"{pad}{_truncate(obj)}")

    walk(data, 1, 0)


def load_stage(path: Path) -> Optional[dict]:
    if not path.exists():
        print(f"  跳过：未找到 {path.name}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def demo_results():
    """遍历阶段样例，打印每个节点产物概要并映射到 PipelineNode。"""
    print("========== 各阶段产物概要（映射到 PipelineNode） ==========")
    for file_name, node_name, description in STAGE_FILES:
        print(f"\n--- {file_name} → PipelineNode.{node_name}（{description}） ---")
        data = load_stage(RESULTS_DIR / file_name)
        if data is None:
            continue
        print_json_summary(data)
        print(f"  顶层键: {', '.join(data.keys())}")


def demo_decision():
    """演示 PipelineState 决策语义：审计报告状态 → PipelineState 映射。"""
    print("\n========== PipelineState 决策语义 ==========")
    for value, meaning in PIPELINE_STATES.items():
        print(f"  {value:<14} {meaning}")

    print("\n质量审查状态 → PipelineState（源码映射，workflow_decision.py:decide_after_audit）：")
    for audit, state in AUDIT_TO_STATE.items():
        print(f"  {audit:<18} → {state}")

    audit = load_stage(RESULTS_DIR / "quality_auditor_result.json")
    if audit:
        status = audit.get("status")
        mapped = AUDIT_TO_STATE.get(status, "未知")
        print(f"\n样例对照：quality_auditor_result.json status={status} → {mapped}")
        stats = audit.get("stats", {})
        print(f"  质量分: {stats.get('quality_score')}, 通过率: {stats.get('pass_rate')}, "
              f"结论: {audit.get('conclusion')}")


def demo_live_enums() -> None:
    """可选用例：在装有 penshot 的环境里对照真实枚举定义。"""
    try:
        from penshot.neopen.agent.workflow.workflow_models import PipelineNode, PipelineState
    except Exception as exc:  # noqa: BLE001 - 环境缺依赖时提示
        print(f"\n[--with-penshot] 导入 penshot 失败（{exc}），无法对照真实枚举，已跳过。")
        return

    print("\n[--with-penshot] 真实 PipelineNode 成员:")
    print(" ", ", ".join(m.name for m in PipelineNode))
    print("[--with-penshot] 真实 PipelineState 成员:")
    print(" ", ", ".join(m.name for m in PipelineState))
    missing = [
        node_name for _, node_name, _ in STAGE_FILES if not hasattr(PipelineNode, node_name)
    ]
    print("[--with-penshot] 样例映射检查:", "全部命中" if not missing else f"缺失: {missing}")


def main():
    parser = argparse.ArgumentParser(description="工作流阶段离线演示")
    parser.add_argument("--with-penshot", action="store_true", help="装有 penshot 时对照真实枚举")
    args = parser.parse_args()

    print("说明：本演示不触发真实 LLM/工作流，仅基于 data/results 历史产物做阶段映射讲解。\n")
    demo_results()
    demo_decision()
    if args.with_penshot:
        demo_live_enums()


if __name__ == "__main__":
    main()
