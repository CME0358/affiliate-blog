#!/bin/bash
# launchd 用: automation_state.json で JOB_ID が停止中ならコマンドを実行しない。
# 用法: run_if_enabled.sh JOB_ID -- command [args...]
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
  echo "usage: run_if_enabled.sh JOB_ID -- command [args...]" >&2
  exit 2
fi

JOB_ID="$1"
shift 2
FAS_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! /usr/bin/python3 "$FAS_DIR/automation_control.py" check "$JOB_ID"; then
  LOG_DIR="$FAS_DIR/logs"
  mkdir -p "$LOG_DIR"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $JOB_ID skipped (paused)" >> "$LOG_DIR/automation_skip.log"
  exit 0
fi

exec "$@"
