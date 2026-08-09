#!/bin/bash
# com.coaretail.form-auto-sender を LaunchAgents に登録（停止フラグ対応ラッパー経由）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FAS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.coaretail.form-auto-sender.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.coaretail.form-auto-sender.plist"
GUI_DOMAIN="gui/$(id -u)"

chmod +x "$FAS_DIR/run_scheduled.sh"

cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootout "$GUI_DOMAIN/com.coaretail.form-auto-sender" 2>/dev/null || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_DST"
launchctl enable "$GUI_DOMAIN/com.coaretail.form-auto-sender" 2>/dev/null || true

echo ""
echo "登録完了: com.coaretail.form-auto-sender（毎日 10:00 · run_scheduled.sh 経由）"
echo "停止: cd \"$FAS_DIR\" && python3 automation_control.py pause form-auto-sender"
echo "再開: cd \"$FAS_DIR\" && python3 automation_control.py resume form-auto-sender"
echo "確認: launchctl print $GUI_DOMAIN/com.coaretail.form-auto-sender"
