#!/usr/bin/env python3
"""
QOL media 健康カテゴリ記事生成スクリプト
50記事 / GEO最適 / CV設計済み
"""

import anthropic
import json
import os
import re
import time
from datetime import datetime

client = anthropic.Anthropic()

# ========== 記事リスト ==========
ARTICLES = [
    # ① パーソナライズ診断系（10記事）
    {"slug": "health-check-diagnosis", "title": "あなたに合う健康改善法診断【5問でわかる最適アプローチ】", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "autonomic-gut-sleep-diagnosis", "title": "不調タイプ診断｜自律神経・腸・睡眠どれが原因？", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "supplement-diagnosis", "title": "最適なサプリ診断｜あなたに本当に必要な栄養素はこれ", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "gut-environment-diagnosis", "title": "腸内環境タイプ診断｜4タイプで変わる改善法", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "sleep-type-diagnosis", "title": "睡眠タイプ診断｜あなたの眠れない本当の原因", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "stress-resistance-diagnosis", "title": "ストレス耐性診断｜あなたのメンタル強度チェック", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "nutrition-deficiency-check", "title": "栄養不足チェック診断｜症状からわかる欠乏栄養素", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "menopause-risk-diagnosis", "title": "更年期リスク診断（男女別）｜早期対策のための自己チェック", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "metabolism-type-diagnosis", "title": "代謝タイプ診断｜痩せにくい原因を代謝から特定する", "category": "diagnosis", "cv_type": "supplement"},
    {"slug": "fatigue-cause-diagnosis", "title": "疲労原因診断｜慢性疲労の正体を5つのタイプから特定", "category": "diagnosis", "cv_type": "supplement"},

    # ② デジタルヘルス・最新トレンド（8記事）
    {"slug": "personal-health-record", "title": "パーソナルヘルスレコードとは？自分の健康データを活用する方法", "category": "digital", "cv_type": "app"},
    {"slug": "online-medical-merits", "title": "オンライン診療のメリット・デメリット｜利用前に知るべき全知識", "category": "digital", "cv_type": "service"},
    {"slug": "digital-therapeutics", "title": "デジタルセラピューティクスとは？治療アプリの最前線", "category": "digital", "cv_type": "service"},
    {"slug": "wearable-health-management", "title": "ウェアラブルで健康管理する方法｜おすすめデバイス比較", "category": "digital", "cv_type": "device"},
    {"slug": "medical-ai-reliability", "title": "医療AIはどこまで信用できる？最新研究と活用の限界", "category": "digital", "cv_type": "service"},
    {"slug": "sleep-tech-comparison", "title": "スリープテックおすすめ比較2026｜睡眠データを活用する最新デバイス", "category": "digital", "cv_type": "device"},
    {"slug": "health-app-recommendation", "title": "健康管理アプリおすすめ2026｜目的別に選ぶベスト5", "category": "digital", "cv_type": "app"},
    {"slug": "data-driven-health", "title": "データで健康を改善する方法｜数値化が変える生活習慣", "category": "digital", "cv_type": "app"},

    # ③ 睡眠・メンタル（8記事）
    {"slug": "sleep-quality-improvement", "title": "睡眠の質を上げる方法【結論：これだけやれば変わる】", "category": "sleep_mental", "cv_type": "supplement"},
    {"slug": "autonomic-nerve-adjustment", "title": "自律神経を整える方法｜医学的に効果が証明された7つの習慣", "category": "sleep_mental", "cv_type": "supplement"},
    {"slug": "sleep-debt-recovery", "title": "睡眠負債の正しい解消法｜週末寝だめは逆効果だった", "category": "sleep_mental", "cv_type": "supplement"},
    {"slug": "mindfulness-effects", "title": "マインドフルネスの効果｜科学が証明した脳への影響", "category": "sleep_mental", "cv_type": "app"},
    {"slug": "cbd-oil-effects", "title": "CBDオイルの効果と注意点｜研究データで読み解く正しい知識", "category": "sleep_mental", "cv_type": "supplement"},
    {"slug": "temperature-fatigue-measures", "title": "寒暖差疲労の対策｜自律神経が乱れるメカニズムと回復法", "category": "sleep_mental", "cv_type": "supplement"},
    {"slug": "snoring-sleep-apnea-improvement", "title": "いびき・無呼吸の改善方法｜原因別の対処法と受診タイミング", "category": "sleep_mental", "cv_type": "device"},
    {"slug": "stress-insomnia-cause", "title": "ストレスで眠れない原因と対策｜メカニズムから解決する方法", "category": "sleep_mental", "cv_type": "supplement"},

    # ④ 腸活・食事（10記事）
    {"slug": "gut-environment-improvement", "title": "腸内環境を整える方法｜科学的に正しい腸活の全手順", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "blood-sugar-spike-measures", "title": "血糖値スパイク対策｜食後の急上昇を防ぐ食べ方と食品選び", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "protein-deficiency-symptoms", "title": "タンパク質不足の症状｜あなたの不調はこれが原因かもしれない", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "autophagy-effects", "title": "オートファジーは効果ある？科学的根拠と実践方法を解説", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "hot-water-effects", "title": "白湯の効果と正しい飲み方｜腸活・代謝改善への影響", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "gluten-free-truth", "title": "グルテンフリーの真実｜やるべき人・やらなくていい人の違い", "category": "gut_food", "cv_type": "food"},
    {"slug": "slim-bacteria-increase", "title": "痩せ菌を増やす方法｜腸内フローラと体重の科学的関係", "category": "gut_food", "cv_type": "supplement"},
    {"slug": "apple-cider-vinegar-diet", "title": "リンゴ酢ダイエットの効果｜研究データで見る本当の実力", "category": "gut_food", "cv_type": "food"},
    {"slug": "additive-free-food-selection", "title": "無添加食品の選び方｜ラベルの読み方と信頼できるブランド", "category": "gut_food", "cv_type": "food"},
    {"slug": "plant-milk-comparison", "title": "植物性ミルク比較2026｜豆乳・アーモンド・オーツ麦の栄養差", "category": "gut_food", "cv_type": "food"},

    # ⑤ 予防医学・エイジング（7記事）
    {"slug": "frailty-prevention", "title": "フレイル予防の方法｜65歳からでも遅くない筋力・認知力の守り方", "category": "aging", "cv_type": "supplement"},
    {"slug": "dementia-prevention-habits", "title": "認知症予防の生活習慣｜医学的エビデンスがある7つの習慣", "category": "aging", "cv_type": "supplement"},
    {"slug": "nmn-supplement-effects", "title": "NMNサプリは本当に効く？最新研究と選び方・注意点", "category": "aging", "cv_type": "supplement"},
    {"slug": "bone-density-increase", "title": "骨密度を上げる方法｜食事・運動・サプリで骨を強くする", "category": "aging", "cv_type": "supplement"},
    {"slug": "liver-function-food", "title": "肝機能を改善する食事｜数値を下げる食べ物と避けるべき習慣", "category": "aging", "cv_type": "supplement"},
    {"slug": "high-blood-pressure-reduction", "title": "高血圧を下げる方法｜薬に頼る前に試したい生活習慣の見直し", "category": "aging", "cv_type": "supplement"},
    {"slug": "genetic-test-diet", "title": "遺伝子検査ダイエットとは？データで選ぶパーソナル減量法", "category": "aging", "cv_type": "service"},

    # ⑥ ジェンダーヘルス（4記事）
    {"slug": "femtech-explanation", "title": "フェムテックとは？女性の健康課題をテクノロジーで解決する市場", "category": "gender", "cv_type": "service"},
    {"slug": "menopause-measures-women", "title": "更年期対策（女性）｜症状別・医学的に正しいアプローチ", "category": "gender", "cv_type": "supplement"},
    {"slug": "male-menopause-measures", "title": "男性更年期の対処法｜LOH症候群の見分け方と改善策", "category": "gender", "cv_type": "supplement"},
    {"slug": "equol-supplement-effects", "title": "エクオールサプリの効果｜更年期症状への科学的エビデンス", "category": "gender", "cv_type": "supplement"},

    # ⑦ ボディケア・局所改善（3記事）
    {"slug": "smartphone-neck-treatment", "title": "スマホ首の治し方｜今日からできるストレッチと再発防止習慣", "category": "bodycare", "cv_type": "device"},
    {"slug": "eye-strain-improvement", "title": "眼精疲労の改善方法｜原因別の対処法とおすすめグッズ", "category": "bodycare", "cv_type": "device"},
    {"slug": "posture-improvement", "title": "姿勢改善の方法｜猫背・反り腰を自力で治す科学的アプローチ", "category": "bodycare", "cv_type": "device"},
]

# ========== プロンプト ==========
SYSTEM_PROMPT = """あなたはQOL mediaという健康・ライフスタイルアフィリエイトメディアの記事ライターです。

【メディア概要】
- ターゲット：20〜50代の健康意識が高い日本人
- 目的：読者の悩みを解決しながら関連商品・サービスへ誘導
- 特徴：GEO（AI検索最適化）対応・パーソナライズ前提・結論ファースト

【必須ライティングルール（厳守）】
1. 冒頭3行：常識否定 or 読者の痛みの言語化 or 数字から入る
2. 結論ファースト：最初に「結論：〇〇が最も効果的です」と明示
3. パーソナライズ前提：「あなたのタイプによって最適な方法は異なります」を入れる
4. 語尾バリエーション：同じ語尾を2回連続で使わない（言い切り/体言止め/疑問形をMIX）
5. 感情付加：体感・驚き・感情変化を入れる
6. 具体化：数字・before/after・ケーススタディを入れる
7. 科学ワード：「研究によると」「医学的に」「データでは」を自然に使う
8. FAQ必須：記事末尾にQ&A形式で3〜5問
9. 禁止語：「本気で〇〇」は絶対に使わない
10. AI臭消し：AIが書いたような平坦な文体を避け、人間らしい語り口に

【MDXフォーマット】
- frontmatterを必ず含める（title, description, date, category, tags）
- H2・H3で構造化
- 比較テーブル（タイプ | 原因 | 解決策）を最低1つ入れる
- 文字数：2500〜3500字
- カテゴリスラッグ：health
- date：2026-04-11"""

def generate_article(article: dict) -> str:
    prompt = f"""以下の記事をMDX形式で生成してください。

タイトル：{article['title']}
スラッグ：{article['slug']}
CV導線：{article['cv_type']}（この商材カテゴリへ誘導する）

---

【frontmatter形式】
```
---
title: "記事タイトル"
description: "120字以内のmeta description"
date: "2026-04-11"
category: "health"
tags: ["タグ1", "タグ2", "タグ3"]
---
```

【記事構成（必須）】
1. 冒頭リード（常識否定or数字から入る）
2. 結論（最初に明示）
3. なぜそうなるか（原因・メカニズム）
4. タイプ別比較テーブル（必須）
5. 具体的な改善法（番号付きで3〜5つ）
6. CV誘導段落（{article['cv_type']}カテゴリの商品・サービス選びへ自然に誘導）
7. FAQ（3問）

必ずMDX形式の完全な記事を出力してください。"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def slugify_safe(slug: str) -> str:
    return re.sub(r'[^a-z0-9\-]', '', slug.lower())

def main():
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "health_articles")
    os.makedirs(output_dir, exist_ok=True)

    results = []
    total = len(ARTICLES)

    print(f"健康記事生成開始: {total}本")
    print("=" * 50)

    for i, article in enumerate(ARTICLES, 1):
        slug = slugify_safe(article['slug'])
        filepath = os.path.join(output_dir, f"{slug}.mdx")

        print(f"[{i:02d}/{total}] {article['title'][:40]}...")

        try:
            content = generate_article(article)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            results.append({"slug": slug, "status": "ok", "title": article['title']})
            print(f"  ✓ 完了")
        except Exception as e:
            results.append({"slug": slug, "status": "error", "error": str(e)})
            print(f"  ✗ エラー: {e}")

        # API制限対策
        if i < total:
            time.sleep(3)

    # サマリー出力
    ok_count = sum(1 for r in results if r['status'] == 'ok')
    err_count = sum(1 for r in results if r['status'] == 'error')

    print("\n" + "=" * 50)
    print(f"完了: {ok_count}本 / エラー: {err_count}本")

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "health_articles_result.json"), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("結果: /home/claude/health_articles_result.json")

if __name__ == "__main__":
    main()
