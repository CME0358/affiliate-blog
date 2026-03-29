#!/usr/bin/env python3
"""
product_link_sheet.csv のアフィリエイトURLを使って
記事内の商品名テキストをMarkdownリンクに一括置換するスクリプト
実行: python3 replace_product_links.py
"""

import csv
import os
import glob
import re

POSTS_DIR = "content/posts"
SHEET_CSV = "product_link_sheet.csv"

def load_product_map():
    """CSVから 商品名 → アフィリエイトURL のマッピングを読み込む"""
    product_map = {}
    with open(SHEET_CSV, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['商品名'].strip()
            url = row['アフィリエイトURL（マネートラックで発行）'].strip()
            pattern = row['記事内での表記パターン（記事内に含まれる可能性のある文字列）'].strip()
            if url and name:
                # 商品名と表記パターン両方登録
                product_map[name] = url
                if pattern and pattern != name:
                    product_map[pattern] = url
    return product_map

def replace_product_names(content: str, product_map: dict) -> tuple[str, list]:
    """
    記事本文内の商品名をMarkdownリンクに置換する
    - すでにリンクになっている箇所はスキップ
    - frontmatter内はスキップ
    - 各商品名は記事内で最初の1回だけリンク化（重複リンク防止）
    """
    # frontmatterを分離
    fm_match = re.match(r'^(---\n.*?\n---\n)', content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        body = content[len(frontmatter):]
    else:
        frontmatter = ''
        body = content

    replaced_items = []

    # 商品名を長い順にソート（部分一致の誤置換防止）
    sorted_products = sorted(product_map.keys(), key=len, reverse=True)

    for product_name in sorted_products:
        url = product_map[product_name]

        # すでにリンクになっている場合はスキップするパターン
        already_linked = re.search(
            r'\[' + re.escape(product_name) + r'\]\(',
            body
        )
        if already_linked:
            continue

        # 商品名が本文中に存在するか確認
        if product_name not in body:
            continue

        # 最初の1箇所だけリンク化
        new_body = body.replace(
            product_name,
            f'[{product_name}]({url})',
            1  # 最初の1回だけ
        )

        if new_body != body:
            replaced_items.append(product_name)
            body = new_body

    return frontmatter + body, replaced_items

def main():
    if not os.path.exists(SHEET_CSV):
        print(f"❌ {SHEET_CSV} が見つかりません")
        print("先に make_product_link_sheet.py を実行してCSVを作成してください")
        return

    product_map = load_product_map()
    if not product_map:
        print("❌ アフィリエイトURLが1件も入力されていません")
        print(f"{SHEET_CSV} の「アフィリエイトURL」欄を記入してください")
        return

    print(f"✓ 商品マッピング読み込み: {len(product_map)}件")
    print()

    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    total_replaced = 0
    updated_files = 0

    for filepath in files:
        slug = os.path.basename(filepath).replace('.md', '')

        with open(filepath, encoding='utf-8') as f:
            content = f.read()

        new_content, replaced_items = replace_product_names(content, product_map)

        if replaced_items:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✓ {slug}")
            for item in replaced_items:
                print(f"   → [{item}] をリンク化")
            total_replaced += len(replaced_items)
            updated_files += 1
        else:
            print(f"  [変更なし] {slug}")

    print()
    print(f"=== 完了 ===")
    print(f"更新ファイル数: {updated_files}記事")
    print(f"リンク化した商品名: {total_replaced}件")
    print()
    print("次のコマンドでデプロイしてください:")
    print("git add .")
    print('git commit -m "add product links to articles"')
    print("git push")

if __name__ == "__main__":
    main()
