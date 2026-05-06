#!/usr/bin/env python3
"""
shindan page.tsx メタタイトル一括修正スクリプト
対象: ~/Downloads/geo-lp/app/area/*/shindan/page.tsx（47都道府県）

修正内容:
  Before: {都道府県}の__none__、AIに無視されていませんか？
  After : {都道府県}の'おすすめ業者'検索で、AIに無視されていませんか？
"""

import os
import re
from pathlib import Path

BASE_DIR = Path.home() / "Downloads" / "geo-lp" / "app" / "area"
SHINDAN_GLOB = "*/shindan/page.tsx"

# 修正前後のパターン
BEFORE_PATTERN = re.compile(r"の__none__、AIに無視されていませんか？")
AFTER_TEXT     = "の'おすすめ業者'検索で、AIに無視されていませんか？"

def fix_file(path: Path) -> bool:
    """1ファイルを修正。変更があった場合Trueを返す"""
    original = path.read_text(encoding="utf-8")
    updated  = BEFORE_PATTERN.sub(AFTER_TEXT, original)

    if original == updated:
        return False

    path.write_text(updated, encoding="utf-8")
    return True

def main():
    targets = sorted(BASE_DIR.glob(SHINDAN_GLOB))

    if not targets:
        print(f"[ERROR] 対象ファイルが見つかりません: {BASE_DIR / SHINDAN_GLOB}")
        return

    print(f"対象ファイル数: {len(targets)}")
    print("-" * 50)

    modified = []
    skipped  = []

    for path in targets:
        if fix_file(path):
            modified.append(path)
            # 都道府県名をprefectureスラッグから取得して表示
            prefecture = path.parts[-3]
            print(f"[修正] {prefecture}/shindan/page.tsx")
        else:
            skipped.append(path)
            prefecture = path.parts[-3]
            print(f"[スキップ] {prefecture}/shindan/page.tsx（対象文字列なし）")

    print("-" * 50)
    print(f"修正完了: {len(modified)}件 / スキップ: {len(skipped)}件")

    if skipped:
        print("\n[注意] スキップされたファイルを手動確認してください:")
        for p in skipped:
            print(f"  {p}")

if __name__ == "__main__":
    main()
