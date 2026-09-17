"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: 01_sync_breakdown.py
@Description: SDK 直调示例：同步分镜拆分（等待结果返回）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import os
import sys
from pathlib import Path

from penshot import ShotLanguage
from penshot.api import PenshotFunction
from penshot.neopen.agent.base_models import VideoStyle

# 脚本内容：任意格式的剧本（自然语言 / 标准剧本 / 结构化场景均可）
SAMPLE_SCRIPT = """
下午放学，空荡荡的教室只剩下李明一个人。他对着毕业同学录发呆，
手里拿着笔，却怎么也写不出一个字。他觉得高中三年自己像个透明人。
语文老师走进来，看穿了他的心思，温和地说了句：
“痕迹不一定非得写在纸上，去走廊看看吧。”
"""


def llm_env_configured() -> bool:
    """粗略判断 LLM 是否已配置（直接环境变量或仓库根目录 .env），避免无配置时长时间空转。"""
    if any(k.startswith("PENSHOT_LLM") for k in os.environ):
        return True
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("PENSHOT_LLM") and not line.strip().endswith("="):
                return True
    return False


def print_result_summary(result):
    """打印 SDK 返回的 data.instructions 摘要（result.data 的保证契约）。"""
    if not result:
        print("未返回结果（可能超时或任务不存在）")
        return
    print(f"任务ID: {result.task_id}")
    print(f"成功: {result.success}, 状态: {result.status.value}")
    if result.error:
        print(f"错误: {result.error}")
        return

    data = result.data or {}
    instructions = data.get("instructions", {})
    fragments = instructions.get("fragments", [])
    project_info = instructions.get("project_info", {})

    print(f"片段数: {project_info.get('total_fragments', len(fragments))}")
    print(f"总时长: {project_info.get('total_duration', 0.0):.1f} 秒")

    # 逐片段展示提示词与音频提示
    for i, frag in enumerate(fragments[:3], 1):
        print(f"\n--- 片段 {i} [{frag.get('fragment_id')}] ---")
        print(f"时长: {frag.get('duration', 0)}s | 模型: {frag.get('model')}")
        print(f"正向: {str(frag.get('prompt', ''))[:120]}...")
        print(f"负向: {str(frag.get('negative_prompt', ''))[:80]}...")
        audio = frag.get("audio")
        if audio:
            print(f"音频: {str(audio.get('prompt', ''))[:100]}...")
    return result


def main():
    """同步方式调用 breakdown_script，等待任务完成后打印结果。"""
    if not llm_env_configured():
        print("尚未配置 LLM：请先复制 .env.example 为 .env 并填写 PENSHOT_LLM__DEFAULT__API_KEY 等。")
        print("示例仅演示 API 用法，配置后可再次运行。")
        sys.exit(0)

    # PenshotFunction 使用 TaskFactory 统一管理任务队列、并发与生命周期
    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)
    try:
        result = agent.breakdown_script(
            SAMPLE_SCRIPT,
            script_id="sdk-sync-001",        # 同属一个剧本的多次请求可传相同 ID，便于关联
            language=ShotLanguage.ZH,        # 输出双语提示词，中文注释部分使用中文
            style=VideoStyle.CINEMATIC,      # 视频风格（可选）
            wait_timeout=600.0,              # 同步等待超时（秒）
        )
        print_result_summary(result)
    except Exception as exc:                 # noqa: BLE001 - 示例中统一兜底打印
        print(f"调用失败: {exc}")
    finally:
        agent.shutdown()                     # 释放后台任务线程/事件循环


if __name__ == "__main__":
    main()
