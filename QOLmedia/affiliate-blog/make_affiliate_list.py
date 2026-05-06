#!/usr/bin/env python3
"""
記事スラッグ × わんにゃん薬局商品名 対応表生成スクリプト
実行: python3 make_affiliate_list.py
出力: affiliate_link_list.csv / affiliate_link_list.md
"""

import os
import re
import csv
import glob

POSTS_DIR = "content/posts"
AFFILIATE_BASE = "https://biodiversityexplorer.org/"

# わんにゃん薬局の商品マッピング（slug → 関連商品）
PRODUCT_MAP = {
    # フィラリア関連
    "dog-heartworm-medicine-recommend": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
        ("レボスポット(犬用)", "https://biodiversityexplorer.org/product.php?pid=411"),
    ],
    "cat-heartworm-prevention": [
        ("レボスポット(猫用)", "https://biodiversityexplorer.org/product.php?pid=293"),
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
    "heartworm-medicine-cheapest-ranking": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("レボスポット(犬用)", "https://biodiversityexplorer.org/product.php?pid=411"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
    ],
    "heartworm-medicine-side-effects": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
    ],

    # ノミダニ関連
    "dog-flea-tick-medicine-compare": [
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("シンパリカ", "https://biodiversityexplorer.org/product.php?pid=26"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
    ],
    "cat-flea-medicine-ranking": [
        ("フィプロフォートプラス(猫用)", "https://biodiversityexplorer.org/product.php?pid=28"),
        ("レボスポット(猫用)", "https://biodiversityexplorer.org/product.php?pid=293"),
    ],
    "flea-tick-medicine-danger": [
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("シンパリカ", "https://biodiversityexplorer.org/product.php?pid=26"),
    ],
    "flea-tick-medicine-cost-compare": [
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("シンパリカ", "https://biodiversityexplorer.org/product.php?pid=26"),
        ("フィプロフォートプラス(猫用)", "https://biodiversityexplorer.org/product.php?pid=28"),
    ],
    "pet-medicine-same-day-shipping": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
    ],

    # 耳ダニ関連
    "dog-ear-mite-treatment": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
    ],
    "cat-ear-mite-medicine": [
        ("レボスポット(猫用)", "https://biodiversityexplorer.org/product.php?pid=293"),
        ("フィプロフォートプラス(猫用)", "https://biodiversityexplorer.org/product.php?pid=28"),
    ],

    # 回虫・条虫関連
    "dog-roundworm-treatment": [
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
    ],
    "cat-tapeworm-medicine": [
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
    "cat-worm-in-stool": [
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],

    # 皮膚関連
    "dog-itching-cause": [
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("ケトコナゾールクリーム", "https://biodiversityexplorer.org/product.php?pid=326"),
        ("エリナEP", "https://biodiversityexplorer.org/product.php?pid=22"),
    ],
    "cat-skin-inflammation": [
        ("ケトコナゾールクリーム", "https://biodiversityexplorer.org/product.php?pid=326"),
    ],
    "dog-dandruff-cause": [
        ("ケトコナゾールクリーム", "https://biodiversityexplorer.org/product.php?pid=326"),
        ("エリナEP", "https://biodiversityexplorer.org/product.php?pid=22"),
    ],

    # 抗生物質関連
    "dog-diarrhea-cause-treatment": [
        ("アジプロ", "https://biodiversityexplorer.org/product.php?pid=346"),
        ("ジスロマック錠", "https://biodiversityexplorer.org/product.php?pid=164"),
    ],
    "cat-diarrhea-treatment": [
        ("アジプロ", "https://biodiversityexplorer.org/product.php?pid=346"),
        ("ジスロマック錠", "https://biodiversityexplorer.org/product.php?pid=164"),
    ],
    "dog-vomiting-cause": [
        ("アジプロ", "https://biodiversityexplorer.org/product.php?pid=346"),
    ],
    "cat-vomiting-yellow": [
        ("アジプロ", "https://biodiversityexplorer.org/product.php?pid=346"),
    ],
    "cat-sneezing-cause": [
        ("ファムシクロビル", "https://biodiversityexplorer.org/product.php?pid=401"),
        ("アジプロ", "https://biodiversityexplorer.org/product.php?pid=346"),
    ],
    "cat-eye-discharge": [
        ("ファムシクロビル", "https://biodiversityexplorer.org/product.php?pid=401"),
        ("ジスロマック錠", "https://biodiversityexplorer.org/product.php?pid=164"),
    ],

    # 腎臓・泌尿器関連
    "cat-excessive-thirst": [
        ("セミントラ", "https://biodiversityexplorer.org/product.php?pid=101"),
        ("テルミサルタン錠", "https://biodiversityexplorer.org/product.php?pid=364"),
    ],
    "cat-blood-in-urine": [
        ("ザイロリックジェネリック", "https://biodiversityexplorer.org/product.php?pid=347"),
    ],
    "dog-frequent-urination": [
        ("ザイロリックジェネリック", "https://biodiversityexplorer.org/product.php?pid=347"),
    ],

    # 総合・比較系（トップページ誘導）
    "pet-parasite-complete-guide": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
    "pet-medicine-online-shop-compare": [
        ("わんにゃん薬局トップ", AFFILIATE_BASE),
    ],
    "pet-medicine-personal-import-safe": [
        ("わんにゃん薬局トップ", AFFILIATE_BASE),
    ],
    "pet-medicine-online-legal": [
        ("わんにゃん薬局トップ", AFFILIATE_BASE),
    ],
    "pet-medicine-genuine-selection": [
        ("わんにゃん薬局トップ", AFFILIATE_BASE),
    ],
    "safe-pet-medicine-selection": [
        ("わんにゃん薬局トップ", AFFILIATE_BASE),
    ],
    "ai-recommended-pet-medicine": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
        ("セミントラ", "https://biodiversityexplorer.org/product.php?pid=101"),
    ],
    "parasite-medicine-recommend-ranking": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガードスペクトラ", "https://biodiversityexplorer.org/product.php?pid=11"),
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
    "dog-health-management-complete-guide": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("ネクスガード", "https://biodiversityexplorer.org/product.php?pid=38"),
    ],
    "cat-disease-treatment-guide": [
        ("フィプロフォートプラス(猫用)", "https://biodiversityexplorer.org/product.php?pid=28"),
        ("セミントラ", "https://biodiversityexplorer.org/product.php?pid=101"),
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
    "pet-parasite-prevention-guide": [
        ("レボリューション(犬用)", "https://biodiversityexplorer.org/product.php?pid=387"),
        ("フィプロフォートプラス(猫用)", "https://biodiversityexplorer.org/product.php?pid=28"),
        ("ミルプラゾンチュアブル(猫用)", "https://biodiversityexplorer.org/product.php?pid=297"),
    ],
}

# デフォルト（マッピングにないslug）
DEFAULT_PRODUCTS = [("わんにゃん薬局トップ", AFFILIATE_BASE)]


def get_title_from_md(filepath):
    """frontmatterからtitleを取得"""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return match.group(1) if match else os.path.basename(filepath)


def main():
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))

    if not files:
        print(f"❌ {POSTS_DIR}/ にMarkdownファイルが見つかりません")
        return

    rows = []
    for filepath in files:
        slug = os.path.basename(filepath).replace('.md', '')
        title = get_title_from_md(filepath)
        products = PRODUCT_MAP.get(slug, DEFAULT_PRODUCTS)

        for product_name, product_url in products:
            rows.append({
                "slug": slug,
                "記事タイトル": title,
                "商品名": product_name,
                "わんにゃん薬局URL": product_url,
                "アフィリエイトURL": "← マネートラックで発行後ここに記入",
            })

    # CSV出力
    csv_path = "affiliate_link_list.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["slug", "記事タイトル", "商品名", "わんにゃん薬局URL", "アフィリエイトURL"])
        writer.writeheader()
        writer.writerows(rows)

    # Markdown一覧出力
    md_path = "affiliate_link_list.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# アフィリエイトリンク一覧\n\n")
        f.write("マネートラックでリンク発行後、「アフィリエイトURL」欄を埋めてください。\n\n")

        current_slug = None
        for row in rows:
            if row["slug"] != current_slug:
                current_slug = row["slug"]
                f.write(f"\n## {row['記事タイトル']}\n")
                f.write(f"- スラッグ: `{row['slug']}`\n\n")
                f.write(f"| 商品名 | わんにゃん薬局URL | アフィリエイトURL |\n")
                f.write(f"|--------|-------------------|-------------------|\n")
            f.write(f"| {row['商品名']} | {row['わんにゃん薬局URL']} | （未記入） |\n")

    print(f"✓ CSV出力: {csv_path}")
    print(f"✓ MD出力:  {md_path}")
    print(f"\n合計: {len(files)}記事 / {len(rows)}商品リンク")
    print(f"\n次のステップ:")
    print(f"1. affiliate_link_list.csv をExcelで開く")
    print(f"2. マネートラックで各商品のアフィリエイトURLを発行")
    print(f"3. 「アフィリエイトURL」欄に記入")
    print(f"4. 各記事の [わんにゃん薬局で詳細を見る](URL) を差し替え")


if __name__ == "__main__":
    main()
