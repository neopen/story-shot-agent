#!/usr/bin/env python
"""
@FileName: entrypoint.py
@Description: Docker entrypoint script.
    - Typical usage inside a container (CMD or ENTRYPOINT):
        python -m scripts.entrypoint
      or
        scripts/entrypoint.py start

    Supported commands:
      start         Start the application (default). Delegates to `python main.py --host <host> --port <port>`.
      install-deps  Install dependencies from requirements.txt using the container Python.
      check-deps    Quick import check for core packages.
      help          Show this help message.

    Environment variables used:
      API__HOST     Host to bind (default: 0.0.0.0)
      API__PORT     Port to bind (default: 8000)
      UVCORN_WORKERS Number of workers to pass through to main.py (if applicable)

    The entrypoint uses os.execv to replace the current process when starting the app so that signals
    from Docker are delivered to the Python/uvicorn process correctly.
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/30 15:39
"""


import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
MAIN_PY = ROOT / "main.py"


def log(msg: str):
    print(msg, flush=True)


def install_deps():
    """Install dependencies using the current Python interpreter."""
    if not REQUIREMENTS.exists():
        log(f"[entrypoint] requirements.txt not found at {REQUIREMENTS}")
        return 1

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    log("[entrypoint] Installing dependencies: " + " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode


def check_deps():
    """Quickly check imports used by the project to detect missing deps.

    Mirrors the lightweight check in scripts/setup_env.py
    """
    test_imports = "import fastapi, requests, json, os, sys"
    cmd = [sys.executable, "-c", test_imports]
    log("[entrypoint] Checking core dependencies...")
    result = subprocess.run(cmd)
    return result.returncode


def start_app():
    """Start the application by exec-ing `python main.py` with host/port from env.

    Using exec replaces the current process so PID 1 in the container will be the app process,
    allowing proper signal handling.
    """
    if not MAIN_PY.exists():
        log(f"[entrypoint] main.py not found at {MAIN_PY}")
        return 1

    host = os.environ.get("API__HOST") or os.environ.get("HOST") or "0.0.0.0"
    port = os.environ.get("API__PORT") or os.environ.get("PORT") or "8000"

    # Allow callers to pass extra uvicorn args via UVCORN_ARGS if needed
    uvicorn_args = os.environ.get("UVCORN_ARGS", "").strip()
    # Construct argv: python main.py --host <host> --port <port>
    argv = [sys.executable, str(MAIN_PY), "--host", str(host), "--port", str(port)]

    if uvicorn_args:
        # Split on spaces; this is simple but sufficient for common use
        argv.extend(uvicorn_args.split())

    log(f"[entrypoint] Starting application: {' '.join(argv)}")

    # Replace the current process with the application process
    os.execv(sys.executable, argv)


def usage():
    print(__doc__)


def main():
    # Default command is 'start'
    cmd = "start"
    if len(sys.argv) >= 2:
        cmd = sys.argv[1].strip().lower()

    if cmd in ("-h", "--help", "help"):
        usage()
        return 0

    if cmd == "install-deps":
        return install_deps()

    if cmd == "check-deps":
        return check_deps()

    if cmd == "start":
        start_app()
        return 0

    # Unknown command
    log(f"[entrypoint] Unknown command: {cmd}\n")
    usage()
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("[entrypoint] Interrupted by user")
        raise
