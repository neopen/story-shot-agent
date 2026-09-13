"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: cli_runner.py
@Description: CLI 示例：用 Python 子进程依次驱动 `python -m penshot.cli` 各子命令
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/9/6 09:40
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 直接运行：python examples/cli/cli_runner.py
# 前置：pip install -e .，使当前解释器可导入 penshot（本运行器用 sys.executable 调起 CLI）。
# 离线命令（--version / queue-status）无需 LLM key；breakdown/batch 需要 key，未配置时自动跳过。

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SCRIPT = REPO_ROOT / "examples" / "data" / "scripts" / "natural_language_script.txt"

BATCH_SCRIPTS = [
    "男人在海边迎着日出慢跑，浪花拍打沙滩。",
    "两个孩子放学后在操场追逐，笑声不断。",
    "老人坐在公园石桌旁下棋，夕阳拉长影子。",
]


def llm_env_configured() -> bool:
    """检查是否已配置 LLM（环境变量或仓库根目录 .env）。"""
    if any(key.startswith("PENSHOT_LLM") for key in os.environ):
        return True
    root_env = REPO_ROOT / ".env"
    if root_env.exists():
        for line in root_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("PENSHOT_LLM"):
                return True
    return False


def penshot_importable() -> bool:
    """探测当前解释器能否导入 penshot。"""
    probe = subprocess.run(
        [sys.executable, "-c", "import penshot"],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def run_cli(args: list, timeout: float = 60.0, cwd: Path = REPO_ROOT) -> dict:
    """以子进程运行 `python -m penshot.cli <args>`，返回 {ok, returncode, stdout, stderr}。"""
    cmd = [sys.executable, "-m", "penshot.cli", *args]
    print(f"\n$ python -m penshot.cli {' '.join(args)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        print("  [超时] 命令超过设定时间未结束，跳过。")
        return {"ok": False, "reason": "timeout"}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        print(out)
    if err:
        print(f"  [stderr] {err}")
    ok = proc.returncode == 0
    print(f"  -> 返回码 {proc.returncode} ({'OK' if ok else 'FAILED'})")
    return {"ok": ok, "returncode": proc.returncode, "stdout": proc.stdout or "", "stderr": proc.stderr or ""}


def demo_offline() -> list:
    """离线可用的子命令（不触发真实 LLM）。"""
    failures = []
    for args in (["--version"], ["queue-status"]):
        result = run_cli(args)
        if not result["ok"]:
            failures.append(args)
    return failures


def demo_online() -> list:
    """需要 LLM key 的子命令；用一个临时脚本文件演示 -f 与 batch -f。"""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        batch_file = tmp_dir / "scripts.txt"
        batch_file.write_text("\n".join(BATCH_SCRIPTS), encoding="utf-8")
        breakdown_out = tmp_dir / "breakdown.json"

        # 同步单本拆分：读 data/scripts 样例 → 输出 JSON
        result = run_cli(["breakdown", "-f", str(SAMPLE_SCRIPT), "--sync", "-o", str(breakdown_out)], timeout=600.0)
        if result["ok"] and breakdown_out.exists():
            print(f"  -> 已生成输出文件 {breakdown_out}")
        else:
            failures.append(["breakdown", "--sync"])

        # 同步批量拆分：每行一个剧本的临时文件
        batch_out = tmp_dir / "batch.json"
        result = run_cli(["batch", "-f", str(batch_file), "--sync", "-o", str(batch_out)], timeout=600.0)
        if result["ok"]:
            print(f"  -> 已生成输出文件 {batch_out}")
        else:
            failures.append(["batch", "--sync"])
    return failures


def main():
    """依次演示 CLI 各子命令；任何命令失败只记录，不中断后续。"""
    if not penshot_importable():
        print("当前解释器无法导入 penshot，请先执行：pip install -e .")
        sys.exit(2)

    if not SAMPLE_SCRIPT.exists():
        print(f"缺少样例剧本：{SAMPLE_SCRIPT}")
        sys.exit(2)

    failures = demo_offline()

    if llm_env_configured():
        failures += demo_online()
    else:
        print("\n未配置 LLM key：跳过 breakdown / batch 等真实拆分演示。"
              "设置 PENSHOT_LLM__DEFAULT__API_KEY 后重跑可验证完整流程。")

    if failures:
        print("\n以下命令执行失败:", [f"[{' '.join(a)}]" for a in failures])
        sys.exit(1)
    print("\n全部演示命令执行通过。")


if __name__ == "__main__":
    main()
