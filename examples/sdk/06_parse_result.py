"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 06_parse_result.py
@Description: SDK 结果解析示例：data.instructions 结构讲解与遍历
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from penshot import ShotLanguage
from penshot.api import PenshotFunction

SAMPLE_RESULT_JSON = Path(__file__).resolve().parents[1] / "data" / "results" / "function_calls_data.json"


def explain_schema() -> None:
    """讲解 result.data 的保证契约。

    说明：默认（非 debug）运行时，成功结果 result.data 顶层只有一个键 "instructions"，
    它是 AIVideoInstructions 的输出结构：
      data["instructions"]["project_info"]  项目统计（total_fragments / total_duration）
      data["instructions"]["fragments"][]   分镜提示词列表，每个片段含：
        fragment_id / prompt / negative_prompt / duration / model / style / audio(可选)
      data["instructions"]["metadata"]       生成时间 / 版本 / 视频模型 / 音频模型
    """
    print(
        "result.data 顶层仅含 instructions（AIVideoInstructions）键。\n"
        "即：data['instructions']['fragments'][i]['prompt'] 等。\n"
        "片段级音频字段为 'audio'（注意不是旧版本的 'audio_prompt'）。"
    )


def walk_instructions(instructions: Dict[str, Any]) -> int:
    """遍历并打印 instructions 关键字段，返回片段数。"""
    project_info = instructions.get("project_info", {})
    metadata = instructions.get("metadata", {})
    fragments = instructions.get("fragments", [])

    print(f"  项目: {project_info.get('title', '(未命名)')}")
    print(f"  片段总数: {project_info.get('total_fragments', len(fragments))}")
    print(f"  总时长: {project_info.get('total_duration', 0.0):.1f} 秒")
    print(f"  视频模型: {metadata.get('video_model')}, 音频模型: {metadata.get('audio_model')}")

    for i, frag in enumerate(fragments, 1):
        audio = frag.get("audio")
        print(
            f"  [{i}] {frag.get('fragment_id')} "
            f"duration={frag.get('duration')}s model={frag.get('model')} "
            f"audio={'有' if audio else '无'}"
        )
        print(f"      prompt: {str(frag.get('prompt', ''))[:90]}...")
    return len(fragments)


def parse_offline_sample() -> None:
    """离线运行：解析仓库自带的 function_calls_data.json 样例，展示相同读取逻辑。"""
    print(f"\n>>> 离线样例解析：{SAMPLE_RESULT_JSON.name}")
    data = json.loads(SAMPLE_RESULT_JSON.read_text(encoding="utf-8"))
    # 该文件顶层即 PenshotResult 的序列化：task_id/success/status/data
    payload = data.get("data", {})
    instructions = payload.get("instructions", {})
    walk_instructions(instructions)


def parse_real_result(out_path: Optional[str]) -> None:
    """在线运行：真实调用一次并解析 result.data。"""
    api_key = os.getenv("PENSHOT_LLM__DEFAULT__API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未配置 LLM API key，跳过真实调用（可改用离线样例）。")

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)
    try:
        result = agent.breakdown_script("雨夜街角，一个青年撑着伞等待未归的朋友。", wait_timeout=600.0)
        if not result:
            print("未返回结果")
            return
        print(f"任务: {result.task_id}, 成功: {result.success}, 状态: {result.status.value}")
        if not result.success:
            print(f"错误: {result.error}")
            return
        data = result.data or {}
        instructions = data.get("instructions", {})
        count = walk_instructions(instructions)

        if out_path:
            Path(out_path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"已将 result.data 保存到: {out_path}")
        else:
            print(f"\n（提示：可用 --out 将 result.data 保存为 JSON 文件；共 {count} 个片段）")
    finally:
        agent.shutdown()


def main():
    parser = argparse.ArgumentParser(description="解析 Penshot 分镜结果 data.instructions")
    parser.add_argument("--offline", action="store_true", help="仅解析仓库自带样例，不调用 LLM")
    parser.add_argument("--out", help="将真实调用的 result.data 保存到指定 JSON 文件")
    args = parser.parse_args()

    explain_schema()
    if args.offline:
        parse_offline_sample()
    else:
        try:
            parse_real_result(args.out)
        except SystemExit as exc:
            print(exc)
            parse_offline_sample()  # 未配置时退回离线样例，保持示例可运行


if __name__ == "__main__":
    main()
