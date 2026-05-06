#!/usr/bin/env python3
"""
shindan page.tsx メタタイトル修正スクリプト v2
シングルクォートによるSyntax Errorを修正

Before: {都道府県}の'おすすめ業者'検索で、AIに無視されていませんか？  ← エラー
After : {都道府県}の'おすすめ業者'検索で、AIに無視されていませんか？  ← 全角クォート
"""

import re
from pathlib import Path

BASE_DIR = Path.home() / "Downloads" / "geo-lp" / "app" / "area"
SHINDAN_GLOB = "*/shindan/page.tsx"

# シングルクォート版（エラー）→ 全角クォート版
BEFORE_PATTERN = re.compile(r"の'おすすめ業者'検索で、AIに無視されていませんか？")
AFTER_TEXT     = "の\u2018おすすめ業者\u2019検索で、AIに無視されていませんか？"
# \u2018 = ' (LEFT SINGLE QUOTATION MARK)
# \u2019 = ' (RIGHT SINGLE QUOTATION MARK)

def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated  = BEFORE_PATTERN.sub(AFTER_TEXT, original)
    if original == updated:
        return False
    path.write_text(updated, encoding="utf-8")
    return True

def main():
    targets = sorted(BASE_DIR.glob(SHINDAN_GLOB))
    if not targets:
        print(f"[ERROR] 対象ファイルが見つかりません")
        return

    print(f"対象ファイル数: {len(targets)}")
    print("-" * 50)

    modified, skipped = [], []
    for path in targets:
        prefecture = path.parts[-3]
        if fix_file(path):
            modified.append(path)
            print(f"[修正] {prefecture}/shindan/page.tsx")
        else:
            skipped.append(path)
            print(f"[スキップ] {prefecture}/shindan/page.tsx")

    print("-" * 50)
    print(f"修正完了: {len(modified)}件 / スキップ: {len(skipped)}件")

if __name__ == "__main__":
    main()
