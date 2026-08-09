#!/bin/bash
# 2026-05-20 10:00 一回限り retry_errors を launchd 登録
set -euo pipefail

FAS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$FAS_DIR/launchd/com.coaretail.retry-0519.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.coaretail.retry-0519.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# 既に登録済みなら一度外す
launchctl unload "$PLIST_DST" 2>/dev/null || true

launchctl load "$PLIST_DST"

echo "登録完了: $PLIST_DST"
echo "実行予定: 2026-05-20 10:00（1回のみ・完了後に自動 unload）"
echo ""
echo "確認:"
echo "  launchctl list | grep retry-0519"
echo "  tail -f \"$FAS_DIR/logs/retry_2026-05-19.log\""
