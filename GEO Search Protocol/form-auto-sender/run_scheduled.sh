#!/bin/bash
# launchd から form-auto-sender を起動するラッパー。
set -euo pipefail
FAS_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$FAS_DIR/run_if_enabled.sh" form-auto-sender -- /usr/bin/python3 "$FAS_DIR/main.py" "$@"
