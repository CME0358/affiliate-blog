#!/bin/bash
# 全 launchd ジョブを run_if_enabled.sh 経由に更新し、default OFF を即時停止する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FAS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WRAP="$FAS_DIR/run_if_enabled.sh"
GUI_DOMAIN="gui/$(id -u)"
VAULT="/Users/takeshisasaki/Downloads/Obsidian_Vault"

chmod +x "$WRAP" "$FAS_DIR/run_scheduled.sh"

_install() {
  local label="$1"
  local src="$2"
  local dst="$HOME/Library/LaunchAgents/${label}.plist"
  cp "$src" "$dst"
  launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$GUI_DOMAIN" "$dst"
  launchctl enable "$GUI_DOMAIN/$label" 2>/dev/null || true
  echo "  ✓ $label"
}

echo "=== launchd 登録（automation_state 連動ラッパー）==="
_install "com.coaretail.form-auto-sender" "$SCRIPT_DIR/com.coaretail.form-auto-sender.plist"
_install "com.coaretail.ops-dashboard" "$SCRIPT_DIR/com.coaretail.ops-dashboard.plist"
_install "com.coaretail.sales.daily_collect" "$VAULT/40_Sales/営業自動化ツール/launchd/com.coaretail.sales.daily_collect.plist"
_install "com.qolmedia.rakuten.daily" "$SCRIPT_DIR/com.qolmedia.rakuten.daily.plist"
_install "com.qolmedia.qol.weekly.mon" "$VAULT/10_Projects/QOLmedia/scripts/launchd/com.qolmedia.qol.weekly.mon.plist"
_install "com.qolmedia.qol.weekly.fri" "$VAULT/10_Projects/QOLmedia/scripts/launchd/com.qolmedia.qol.weekly.fri.plist"
_install "com.coaretail.geo.weekly.mon" "$VAULT/10_Projects/GEO Search Protocol/scripts/launchd/com.coaretail.geo.weekly.mon.plist"
_install "com.coaretail.geo.weekly.fri" "$VAULT/10_Projects/GEO Search Protocol/scripts/launchd/com.coaretail.geo.weekly.fri.plist"
_install "com.coaretail.localgeo.weekly.mon" "$VAULT/10_Projects/Local GEO/scripts/launchd/com.coaretail.localgeo.weekly.mon.plist"
_install "com.coaretail.localgeo.weekly.fri" "$VAULT/10_Projects/Local GEO/scripts/launchd/com.coaretail.localgeo.weekly.fri.plist"
_install "com.coaretail.bumblebee-weekly" "$SCRIPT_DIR/com.coaretail.bumblebee-weekly.plist"

echo ""
echo "=== default OFF 同期 + 即時停止 ==="
cd "$FAS_DIR"
/usr/bin/python3 automation_control.py sync-defaults
/usr/bin/python3 automation_control.py enforce
/usr/bin/python3 build_ops_dashboard.py

echo ""
echo "完了。状態: python3 automation_control.py status"
