#!/usr/bin/env python3
"""既存 error.csv から .failure_cooldown.csv を生成する（P0 初回移行）。"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from log_manager import seed_failure_cooldown_from_error_csv  # noqa: E402


def main() -> None:
    n = seed_failure_cooldown_from_error_csv()
    print(f"✅  failure_cooldown 索引に {n} 社を登録しました（logs/.failure_cooldown.csv）")


if __name__ == "__main__":
    main()
