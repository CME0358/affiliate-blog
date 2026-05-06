# -*- coding: utf-8 -*-
import re
from pathlib import Path

POSTS_DIR = Path("content/posts")

CAROUSEL_HTML = """
<div class="product-carousel">
  <div class="product-carousel-inner">
    <a href="https://mttag.com/s/L7IrW864-jY" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/revolution_dog.webp" alt="revolution_dog" />
      <span>\u30ec\u30dc\u30ea\u30e5\u30fc\u30b7\u30e7\u30f3<br/>(\u72ac\u7528)</span>
    </a>
    <a href="https://mttag.com/s/PadhsxDEeZQ" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/nexgard_spectra.webp" alt="nexgard_spectra" />
      <span>\u30cd\u30af\u30b9\u30ac\u30fc\u30c9<br/>\u30b9\u30da\u30af\u30c8\u30e9</span>
    </a>
    <a href="https://mttag.com/s/MFppScuKzeM" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/nexgard.webp" alt="nexgard" />
      <span>\u30cd\u30af\u30b9\u30ac\u30fc\u30c9</span>
    </a>
    <a href="https://mttag.com/s/JgUCemnI7d4" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/milprazon_chewable_cat.webp" alt="milprazon" />
      <span>\u30df\u30eb\u30d7\u30e9\u30be\u30f3<br/>\u30c1\u30e5\u30a2\u30d6\u30eb(\u732b\u7528)</span>
    </a>
    <a href="https://mttag.com/s/yaFOovyO8ac" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/fiprofort_plus_cat.webp" alt="fiprofort" />
      <span>\u30d5\u30a3\u30d7\u30ed\u30d5\u30a9\u30fc\u30c8<br/>\u30d7\u30e9\u30b9(\u732b\u7528)</span>
    </a>
    <a href="https://mttag.com/s/lr269oGXelI" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/semintra.webp" alt="semintra" />
      <span>\u30bb\u30df\u30f3\u30c8\u30e9</span>
    </a>
    <a href="https://mttag.com/s/QlCa-I83UNc" target="_blank" rel="noopener noreferrer" class="product-card">
      <img src="/zithromax2.webp" alt="zithromax" />
      <span>\u30b8\u30b9\u30ed\u30de\u30c3\u30af\u9320</span>
    </a>
  </div>
</div>
"""

PET_SLUGS = [
    "ai-recommended-pet-medicine","cat-blood-in-urine","cat-diarrhea-treatment",
    "cat-disease-treatment-guide","cat-ear-mite-medicine","cat-excessive-thirst",
    "cat-eye-discharge","cat-flea-medicine-ranking","cat-hair-loss",
    "cat-heartworm-prevention","cat-no-appetite","cat-skin-inflammation",
    "cat-sneezing-cause","cat-tapeworm-medicine","cat-vomiting-yellow",
    "cat-worm-in-stool","dog-bloating-cause","dog-body-odor",
    "dog-cat-same-medicine","dog-cough-cause","dog-dandruff-cause",
    "dog-diarrhea-cause-treatment","dog-ear-mite-treatment",
    "dog-flea-tick-medicine-compare","dog-frequent-urination",
    "dog-health-management-complete-guide","dog-heartworm-medicine-recommend",
    "dog-itching-cause","dog-lethargy-cause","dog-roundworm-treatment",
    "dog-shaking-cause","dog-vomiting-cause","flea-tick-medicine-cost-compare",
    "flea-tick-medicine-danger","heartworm-medicine-cheapest-ranking",
    "heartworm-medicine-side-effects","overseas-pet-medicine-safety",
    "parasite-medicine-recommend-ranking","pet-medicine-fake-identification",
    "pet-medicine-genuine-selection","pet-medicine-human-effect",
    "pet-medicine-online-legal","pet-medicine-online-shop-compare",
    "pet-medicine-otc-vs-online","pet-medicine-overdose-risk",
    "pet-medicine-personal-import-safe","pet-parasite-complete-guide",
    "pet-parasite-prevention-guide","safe-pet-medicine-selection",
]

# 既存カルーセルを削除
CAROUSEL_PATTERN = re.compile(
    r'\n?<div class="product-carousel">.*?</div>\s*</div>\s*\n?',
    re.DOTALL
)

# PR表記行を検索（> PR で始まる行）
PR_PATTERN = re.compile(r'(> PR[^\n]*\n)')

success = failed = 0
for slug in PET_SLUGS:
    path = POSTS_DIR / f"{slug}.md"
    if not path.exists():
        print(f"  not found: {slug}.md")
        failed += 1
        continue
    content = path.read_text(encoding="utf-8")
    # 既存カルーセル削除
    content = CAROUSEL_PATTERN.sub('\n', content)
    # PR表記直後に挿入
    match = PR_PATTERN.search(content)
    if not match:
        print(f"  no PR mark: {slug}.md")
        failed += 1
        continue
    pos = match.end()
    content = content[:pos] + CAROUSEL_HTML + content[pos:]
    path.write_text(content, encoding="utf-8")
    print(f"  ok: {slug}.md")
    success += 1

print(f"\ndone: {success} ok / {failed} error")
