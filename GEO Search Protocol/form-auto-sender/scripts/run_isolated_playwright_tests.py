"""Run unittest discovery with a disposable, system-Chrome-backed browser cache."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright_environment import isolated_playwright_env


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ari-playwright-") as temp:
        env = isolated_playwright_env(Path(temp))
        command = [sys.executable, "-m", "unittest", *sys.argv[1:]]
        return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
