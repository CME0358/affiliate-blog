#!/bin/bash
# com.coaretail.ops-dashboard を LaunchAgents に登録し、即時にダッシュボードを1回生成する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FAS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.coaretail.ops-dashboard.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.coaretail.ops-dashboard.plist"
GUI_DOMAIN="gui/$(id -u)"

cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootout "$GUI_DOMAIN/com.coaretail.ops-dashboard" 2>/dev/null || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_DST"
launchctl enable "$GUI_DOMAIN/com.coaretail.ops-dashboard" 2>/dev/null || true

cd "$FAS_DIR"
/usr/bin/python3 build_ops_dashboard.py

echo ""
echo "登録完了: com.coaretail.ops-dashboard（1時間ごと + ログイン時 RunAtLoad）"
echo "確認: launchctl print $GUI_DOMAIN/com.coaretail.ops-dashboard"
echo "ログ: $FAS_DIR/logs/ops_dashboard_launchd_stdout.log"
