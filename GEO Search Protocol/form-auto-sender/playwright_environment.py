"""Build an isolated Playwright browser path backed by installed system Chrome.

Playwright 1.62 cannot download its bundled Chromium on macOS 13.  The project
uses a wrapper (not a symlink) so Chrome resolves its Frameworks from the real
application bundle while Playwright retains its normal chromium.launch API.
"""
from __future__ import annotations

import os
from pathlib import Path

SYSTEM_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PLAYWRIGHT_REVISION = "1234"


def prepare_isolated_browser_path(root: Path) -> Path:
    if not SYSTEM_CHROME.is_file():
        raise RuntimeError(f"system Chrome missing: {SYSTEM_CHROME}")
    executable = root / f"chromium_headless_shell-{PLAYWRIGHT_REVISION}" / "chrome-headless-shell-mac-x64" / "chrome-headless-shell"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(
        '#!/bin/sh\nexec "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$@"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return root


def isolated_playwright_env(root: Path) -> dict[str, str]:
    prepare_isolated_browser_path(root)
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(root)
    return env
