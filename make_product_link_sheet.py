#!/usr/bin/env python3
"""
記事内の商品名 × わんにゃん薬局URL の作業表を生成
実行: python3 make_product_link_sheet.py
出力: product_link_sheet.csv
"""

import csv
import os

# わんにゃん薬局の全商品リスト（商品名 → 商品ページURL）
PRODUCTS = [
    # フィラリア予防（犬）
    ("レボリューション(犬用)",          "https://biodiversityexplorer.org/product.php?pid=387"),
    ("レボスポット(犬用)",              "https://biodiversityexplorer.org/product.php?pid=411"),
    ("ネクスガードスペクトラ",           "https://biodiversityexplorer.org/product.php?pid=11"),
    ("ハートガードプラス",              "https://biodiversityexplorer.org/product.php?pid=1"),
    ("カルドメック",                   "https://biodiversityexplorer.org/product.php?pid=1"),
    ("ミルベマイシン",                  "https://biodiversityexplorer.org/product.php?pid=2"),

    # フィラリア予防（猫）
    ("レボリューション(猫用)",          "https://biodiversityexplorer.org/product.php?pid=3"),
    ("レボスポット(猫用)",              "https://biodiversityexplorer.org/product.php?pid=293"),
    ("ミルプラゾンチュアブル(猫用)",    "https://biodiversityexplorer.org/product.php?pid=297"),
    ("ブロードライン",                  "https://biodiversityexplorer.org/product.php?pid=4"),

    # ノミダニ（犬）
    ("ネクスガード",                    "https://biodiversityexplorer.org/product.php?pid=38"),
    ("シンパリカ",                      "https://biodiversityexplorer.org/product.php?pid=26"),
    ("ブラベクト錠(犬用)",             "https://biodiversityexplorer.org/product.php?pid=5"),
    ("フロントラインプラス",            "https://biodiversityexplorer.org/product.php?pid=6"),
    ("エリナEP",                       "https://biodiversityexplorer.org/product.php?pid=22"),

    # ノミダニ（猫）
    ("フィプロフォートプラス(猫用)",    "https://biodiversityexplorer.org/product.php?pid=28"),

    # 寄生虫駆除
    ("ドロンタール",                    "https://biodiversityexplorer.org/product.php?pid=7"),
    ("ミルベマックス",                  "https://biodiversityexplorer.org/product.php?pid=8"),

    # 抗生物質
    ("アジプロ",                       "https://biodiversityexplorer.org/product.php?pid=346"),
    ("ジスロマック錠",                  "https://biodiversityexplorer.org/product.php?pid=164"),
    ("ファムシクロビル",                "https://biodiversityexplorer.org/product.php?pid=401"),
    ("ケトコナゾールクリーム",          "https://biodiversityexplorer.org/product.php?pid=326"),

    # 腎臓・泌尿器
    ("セミントラ",                      "https://biodiversityexplorer.org/product.php?pid=101"),
    ("テルミサルタン錠",               "https://biodiversityexplorer.org/product.php?pid=364"),
    ("ザイロリックジェネリック",        "https://biodiversityexplorer.org/product.php?pid=347"),
]

OUTPUT = "product_link_sheet.csv"

def main():
    with open(OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            "商品名",
            "わんにゃん薬局URL（確認用）",
            "アフィリエイトURL（マネートラックで発行）",
            "記事内での表記パターン（記事内に含まれる可能性のある文字列）",
        ])
        for name, url in PRODUCTS:
            writer.writerow([
                name,
                url,
                "",  # マネートラックで発行後に記入
                name,  # 記事内の表記と一致させる
            ])

    print(f"✓ 作業表を出力しました: {OUTPUT}")
    print(f"  商品数: {len(PRODUCTS)}")
    print()
    print("【次の手順】")
    print("1. product_link_sheet.csv をExcelで開く")
    print("2. 各商品のわんにゃん薬局URLにアクセスして商品を確認")
    print("3. マネートラックで各商品のアフィリエイトURLを発行")
    print("4. 「アフィリエイトURL」欄に記入して保存")
    print("5. python3 replace_product_links.py を実行")

if __name__ == "__main__":
    main()
