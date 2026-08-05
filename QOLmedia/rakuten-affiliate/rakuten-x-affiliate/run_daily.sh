#!/bin/bash
# 日次パイプライン: QOL 7ch 予約投入（楽天アフィは 2026-06-06 停止）
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"

# --- 楽天アフィ（停止: archive/deprecated/rakuten-x-affiliate/）---
echo "=== rakuten pipeline SKIPPED (deprecated 2026-06-06) ==="
echo "  generate_daily / promote_to_draft / upload_buffer_drafts は実行しません"

echo "=== upload_qol_x (fatigue/focus/pet/stress/factoring/sleep/haircare → 08-23 予約) ==="
/usr/bin/python3 "$DIR/upload_qol_x_buffer.py" --sleep 30 2>&1 | tee "$LOG_DIR/upload_qol_${STAMP}.log"

echo "Done. QOL: qol_x_upload_log.csv を確認"
