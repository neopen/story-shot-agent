"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: 07_script_from_file.py
@Description: SDK 直调示例：读取剧本文件后执行分镜拆分
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:10
"""
import os
import sys
from pathlib import Path

from penshot import ShotLanguage
from penshot.api import PenshotFunction

# examples/data/scripts 下内置多份不同格式的样例剧本
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "scripts"


def load_script(name: str) -> str:
    """按名称加载样例剧本，例如 natural_language_script.txt / standard_script_script.txt。"""
    path = SCRIPTS_DIR / name
    if not path.exists():
        available = ", ".join(p.name for p in SCRIPTS_DIR.glob("*.txt"))
        raise FileNotFoundError(f"未找到 {name}；可用样例：{available}")
    return path.read_text(encoding="utf-8")


def main():
    """读取剧本文件并提交分镜拆分（未配置 LLM 时仅做文件预览）。"""
    script_name = os.getenv("PENSHOT_SAMPLE_SCRIPT", "natural_language_script.txt")
    try:
        script = load_script(script_name)
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(1)

    print(f"已加载剧本: {script_name}（{len(script)} 字符）")
    print(f"内容预览: {script[:120].strip()}...\n")

    api_key = os.getenv("PENSHOT_LLM__DEFAULT__API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("未配置 LLM API key，跳过真实拆分。设置 PENSHOT_LLM__DEFAULT__API_KEY 后可再次运行。")
        sys.exit(0)

    agent = PenshotFunction(language=ShotLanguage.ZH, max_concurrent=5)
    try:
        result = agent.breakdown_script(
            script,
            script_id=f"from-file-{script_name}",
            wait_timeout=900.0,
        )
        if not result:
            print("未返回结果")
            return
        if result.success:
            instructions = (result.data or {}).get("instructions", {})
            project_info = instructions.get("project_info", {})
            print(f"成功: {result.status.value}")
            print(f"片段数: {project_info.get('total_fragments')}, "
                  f"总时长: {project_info.get('total_duration')}s")
        else:
            print(f"失败: {result.error}")
    except Exception as exc:  # noqa: BLE001 - 示例中统一兜底打印
        print(f"调用失败: {exc}")
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
