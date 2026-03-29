#!/usr/bin/env python3
"""
CSVのアフィリエイトURLを記事ファイルに一括置換するスクリプト
実行: python3 replace_affiliate_links.py
"""

import csv
import os
import re
import glob

POSTS_DIR = "content/posts"
CSV_PATH = "affiliate_link_list.csv"
ORIGINAL_URL = "https://biodiversityexplorer.org/"

def main():
    # CSV読み込み
    if not os.path.exists(CSV_PATH):
        print(f"❌ {CSV_PATH} が見つかりません")
        return

    # slug → アフィリエイトURL のマッピングを作成
    # 1記事に複数商品がある場合は最初のURLを使用
    slug_to_url = {}
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            slug = row['slug'].strip()
            affiliate_url = row['アフィリエイトURL'].strip()
            # 未記入・デフォルト値はスキップ
            if not affiliate_url or '未記入' in affiliate_url or '← ' in affiliate_url:
                continue
            # slugごとに最初の1件だけ使う
            if slug not in slug_to_url:
                slug_to_url[slug] = affiliate_url

    print(f"✓ CSV読み込み完了: {len(slug_to_url)}記事分のURLを取得")

    # 各記事ファイルを処理
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    updated = 0
    skipped = 0

    for filepath in files:
        slug = os.path.basename(filepath).replace('.md', '')

        if slug not in slug_to_url:
            print(f"  [スキップ] {slug} - CSVにURLなし")
            skipped += 1
            continue

        affiliate_url = slug_to_url[slug]

        with open(filepath, encoding='utf-8') as f:
            content = f.read()

        # 置換パターン：わんにゃん薬局のURLをアフィリエイトURLに置換
        new_content = content.replace(ORIGINAL_URL, affiliate_url)

        if new_content == content:
            print(f"  [変更なし] {slug}")
            skipped += 1
            continue

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"  ✓ 置換完了: {slug}")
        updated += 1

    print(f"\n=== 完了 ===")
    print(f"置換済み: {updated}記事")
    print(f"スキップ: {skipped}記事")
    print(f"\n次のコマンドでデプロイしてください:")
    print("git add .")
    print('git commit -m "replace affiliate links"')
    print("git push")

if __name__ == "__main__":
    main()
