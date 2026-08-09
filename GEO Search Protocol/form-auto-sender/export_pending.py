#!/usr/bin/env python3
"""
export_pending.py — 本日の reCAPTCHA 手動確認キューを Markdown に出力（P0）

実行:
    python export_pending.py
    python export_pending.py --date 2026-05-18
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from config import LOG_DIR, VAULT_ROOT
from log_manager import vault_today

OUTPUT_DIR = VAULT_ROOT / "70_outputs" / "営業"


def _parse_pending_blocks(content: str) -> list[dict]:
    """## ⚠️ 手動確認 セクションから ### ブロックを抽出。"""
    marker = "## ⚠️ 手動確認（reCAPTCHA）"
    err_marker = "## ❌ エラー"
    start = content.find(marker)
    if start == -1:
        return []
    end = content.find(err_marker, start + len(marker))
    chunk = content[start:end] if end != -1 else content[start:]

    blocks = re.split(r"\n(?=### )", chunk)
    out: list[dict] = []
    for block in blocks:
        if not block.strip().startswith("### "):
            continue
        m_name = re.match(r"### (.+)", block)
        if not m_name:
            continue
        name = m_name.group(1).strip()
        form = ""
        mf = re.search(r"- フォーム: (.+)", block)
        if mf:
            form = mf.group(1).strip()
        industry = ""
        mi = re.search(r"- 業種: (.+?) /", block)
        if mi:
            industry = mi.group(1).strip()
        message = ""
        mm = re.search(r"```\n([\s\S]*?)```", block)
        if mm:
            message = mm.group(1).strip()
        out.append({
            "company_name": name,
            "form_url": form,
            "industry_name": industry,
            "message": message,
        })
    return out


def export_pending(target_date: date | None = None) -> Path | None:
    d = target_date or vault_today()
    log_path = LOG_DIR / f"{d.isoformat()}.md"
    if not log_path.exists():
        print(f"ログなし: {log_path}")
        return None

    items = _parse_pending_blocks(log_path.read_text(encoding="utf-8"))
    if not items:
        print(f"{d.isoformat()}: 手動確認（reCAPTCHA）0 件")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{d.isoformat()}_reCAPTCHA手動送信キュー.md"

    lines = [
        f"# reCAPTCHA 手動送信キュー（{d.isoformat()}）",
        "",
        f"- 件数: {len(items)}",
        f"- 所要目安: 約 {len(items) * 2} 分（1件2分）",
        f"- 出典: `10_Projects/GEO Search Protocol/form-auto-sender/logs/{d.isoformat()}.md`",
        "",
        "## 手順",
        "1. 各フォームURLをブラウザで開く",
        "2. 送信予定文面をコピペ",
        "3. reCAPTCHA を手動完了 → 送信",
        "4. 送信後は `logs/.sent_index.csv` に手動追記するか、翌日の重複チェックに注意",
        "",
        "## キュー",
        "",
    ]

    for i, item in enumerate(items, 1):
        lines.append(f"### {i}. {item['company_name']}")
        if item.get("industry_name"):
            lines.append(f"- 業種: {item['industry_name']}")
        lines.append(f"- フォーム: {item['form_url']}")
        lines.append("- [ ] 送信完了")
        if item.get("message"):
            lines.append("")
            lines.append("**送信文面:**")
            lines.append("```")
            lines.append(item["message"])
            lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅  {len(items)} 件 → {out_path}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="reCAPTCHA 手動確認キューを Markdown 出力")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="対象日（省略時は本日）")
    args = ap.parse_args()
    d = date.fromisoformat(args.date) if args.date else None
    path = export_pending(d)
    sys.exit(0 if path else 1)


if __name__ == "__main__":
    main()
