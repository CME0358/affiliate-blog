#!/usr/bin/env python3
"""
QOL media ─ ペット記事49本にカルーセルを一括挿入するスクリプト

挿入位置: 「わんにゃん薬局で詳細を見る」リンクの直前
使い方:
  cd ~/Downloads/affiliate-blog
  python3 insert_carousel.py
"""

import os
import re
from pathlib import Path

POSTS_DIR = Path("content/posts")

# カルーセルHTMLブロック（globals.cssにスタイルを追加予定）
CAROUSEL_HTML = """
<div class="product-carousel">
  <div class="product-carousel-inner">
    <a href="https://mttag.com/s/L7IrW864-jY" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/revolution_dog.webp" alt="レボリューション(犬用)" />
      <span>レボリューション<br/>(犬用)</span>
    </a>
    <a href="https://mttag.com/s/PadhsxDEeZQ" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/nexgard_spectra.webp" alt="ネクスガードスペクトラ" />
      <span>ネクスガード<br/>スペクトラ</span>
    </a>
    <a href="https://mttag.com/s/MFppScuKzeM" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/nexgard.webp" alt="ネクスガード" />
      <span>ネクスガード</span>
    </a>
    <a href="https://mttag.com/s/JgUCemnI7d4" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/milprazon_chewable_cat.webp" alt="ミルプラゾンチュアブル(猫用)" />
      <span>ミルプラゾン<br/>チュアブル(猫用)</span>
    </a>
    <a href="https://mttag.com/s/yaFOovyO8ac" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/fiprofort_plus_cat.webp" alt="フィプロフォートプラス(猫用)" />
      <span>フィプロフォート<br/>プラス(猫用)</span>
    </a>
    <a href="https://mttag.com/s/lr269oGXelI" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/semintra.webp" alt="セミントラ" />
      <span>セミントラ</span>
    </a>
    <a href="https://mttag.com/s/QlCa-I83UNc" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/zithromax2.webp" alt="ジスロマック錠" />
      <span>ジスロマック錠</span>
    </a>
  </div>
</div>

"""

# ペット記事のスラッグ一覧（睡眠記事を除外済み）
PET_SLUGS = [
    "ai-recommended-pet-medicine",
    "cat-blood-in-urine",
    "cat-diarrhea-treatment",
    "cat-disease-treatment-guide",
    "cat-ear-mite-medicine",
    "cat-excessive-thirst",
    "cat-eye-discharge",
    "cat-flea-medicine-ranking",
    "cat-hair-loss",
    "cat-heartworm-prevention",
    "cat-no-appetite",
    "cat-skin-inflammation",
    "cat-sneezing-cause",
    "cat-tapeworm-medicine",
    "cat-vomiting-yellow",
    "cat-worm-in-stool",
    "dog-bloating-cause",
    "dog-body-odor",
    "dog-cat-same-medicine",
    "dog-cough-cause",
    "dog-dandruff-cause",
    "dog-diarrhea-cause-treatment",
    "dog-ear-mite-treatment",
    "dog-flea-tick-medicine-compare",
    "dog-frequent-urination",
    "dog-health-management-complete-guide",
    "dog-heartworm-medicine-recommend",
    "dog-itching-cause",
    "dog-lethargy-cause",
    "dog-roundworm-treatment",
    "dog-shaking-cause",
    "dog-vomiting-cause",
    "flea-tick-medicine-cost-compare",
    "flea-tick-medicine-danger",
    "heartworm-medicine-cheapest-ranking",
    "heartworm-medicine-side-effects",
    "overseas-pet-medicine-safety",
    "parasite-medicine-recommend-ranking",
    "pet-medicine-fake-identification",
    "pet-medicine-genuine-selection",
    "pet-medicine-human-effect",
    "pet-medicine-online-legal",
    "pet-medicine-online-shop-compare",
    "pet-medicine-otc-vs-online",
    "pet-medicine-overdose-risk",
    "pet-medicine-personal-import-safe",
    "pet-parasite-complete-guide",
    "pet-parasite-prevention-guide",
    "safe-pet-medicine-selection",
]

# 挿入ターゲットパターン（わんにゃん薬局リンクの直前）
# mttag.comへのリンクを含む行を探して直前に挿入
INSERT_BEFORE_PATTERN = re.compile(
    r'(\[わんにゃん薬局[^\]]*\]\(https://mttag\.com[^)]*\))',
    re.MULTILINE
)

def insert_carousel(content: str) -> tuple[str, bool]:
    """カルーセルをわんにゃん薬局リンクの直前に挿入。既に挿入済みならスキップ。"""
    if "product-carousel" in content:
        return content, False  # 挿入済み

    match = INSERT_BEFORE_PATTERN.search(content)
    if match:
        insert_pos = match.start()
        new_content = content[:insert_pos] + CAROUSEL_HTML + content[insert_pos:]
        return new_content, True

    # mttag.comリンクが見つからない場合は本文最初のH2見出し直前に挿入
    h2_match = re.search(r'^## ', content, re.MULTILINE)
    if h2_match:
        insert_pos = h2_match.start()
        new_content = content[:insert_pos] + CAROUSEL_HTML + content[insert_pos:]
        return new_content, True

    return content, False


def main():
    print("=== カルーセル一括挿入スクリプト ===")
    print(f"対象: {len(PET_SLUGS)}記事")
    print()

    success = 0
    skipped = 0
    failed = []

    for slug in PET_SLUGS:
        path = POSTS_DIR / f"{slug}.md"
        if not path.exists():
            print(f"  ✗ ファイルなし: {slug}.md")
            failed.append(slug)
            continue

        content = path.read_text(encoding="utf-8")
        new_content, inserted = insert_carousel(content)

        if not inserted:
            print(f"  ─ スキップ（挿入済み）: {slug}.md")
            skipped += 1
            continue

        path.write_text(new_content, encoding="utf-8")
        print(f"  ✓ 挿入完了: {slug}.md")
        success += 1

    print()
    print(f"=== 完了: 挿入 {success}件 / スキップ {skipped}件 / エラー {len(failed)}件 ===")
    if failed:
        print("エラー:")
        for s in failed:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
