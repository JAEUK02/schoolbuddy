"""Run this synthetic demo with its own light theme and loopback binding."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def command(port):
    return [sys.executable, "-m", "streamlit", "run", str(ROOT / "demo_notice.py"),
            "--server.address", "127.0.0.1", "--server.port", str(port),
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
            "--server.fileWatcherType", "none", "--theme.base", str(ROOT / "demo_theme.toml")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8512)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port between 1024 and 65535")
    raise SystemExit(subprocess.call(command(args.port), cwd=ROOT))
