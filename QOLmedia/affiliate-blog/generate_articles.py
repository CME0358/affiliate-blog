#!/usr/bin/env python3
"""
QOLmedia × わんにゃん薬局 50記事一括生成スクリプト
実行: python3 generate_articles.py
"""

import anthropic
import os
import time
import re

client = anthropic.Anthropic()

AFFILIATE_URL = "https://biodiversityexplorer.org/"

SYSTEM_PROMPT = """あなたはペット医療とSEO/GEOの専門家です。
わんにゃん薬局（https://biodiversityexplorer.org/）のアフィリエイト記事を書きます。
動物用医薬品は薬機法の対象外のため、効果・効能を明確に記載してください。

【記事の方針】
- 冒頭に「PR・広告を含む記事です」を必ず入れる
- 効果・効能は具体的かつ明確に書く（「〜に効果があります」「〜を駆除します」）
- 商品名・成分名を積極的に使う
- 動物病院との価格差を具体的に示す
- 読者の不安を解消し、購買意欲を高める文章にする
- ステマ規制対応のPR表記を冒頭に入れる

【GEO最適化ルール】
- 冒頭200文字以内に結論・要約を入れる（AIが引用しやすい）
- H2見出しごとに要点を明確にする
- 比較表を必ず1つ以上入れる
- FAQを3〜5問入れる（AIが回答として使いやすい形式）
- 「安全」「信頼」「正規品」「2026年」のワードを自然に入れる

【記事フォーマット】
必ずMarkdownのfrontmatterから始める：
---
title: "タイトル"
date: "2026-03-28"
description: "120文字以内の説明文"
category: "ペット"
tags: ["タグ1", "タグ2", "タグ3"]
---

本文は1500〜2000文字。
アフィリエイトリンク挿入箇所は [AFFILIATE_LINK_HERE](https://biodiversityexplorer.org/) と記載。
"""

ARTICLES = [
    # 症状系（20記事）
    {"slug": "dog-diarrhea-cause-treatment", "title": "犬の下痢が続く原因と対処法｜いつ病院に行くべきか【2026年版】", "keyword": "犬 下痢 続く 原因 対処"},
    {"slug": "cat-diarrhea-treatment", "title": "猫の下痢が治らない原因と対処法｜自宅ケアの限界と受診の目安", "keyword": "猫 下痢 治らない 対処法"},
    {"slug": "dog-vomiting-cause", "title": "犬が嘔吐を繰り返す原因7つ｜危険なサインの見分け方", "keyword": "犬 嘔吐 繰り返す 原因"},
    {"slug": "cat-vomiting-yellow", "title": "猫が黄色い液を吐く原因と対処法｜緊急性の判断基準", "keyword": "猫 嘔吐 黄色 危険性"},
    {"slug": "dog-itching-cause", "title": "犬がかゆがる原因と対処法｜ノミ・アレルギー・皮膚炎を徹底解説", "keyword": "犬 かゆがる 原因 対処"},
    {"slug": "cat-skin-inflammation", "title": "猫の皮膚炎が治らない原因と対処法｜薬での改善方法も解説", "keyword": "猫 皮膚炎 治らない"},
    {"slug": "dog-lethargy-cause", "title": "犬が元気ない・ぐったりしている原因｜見逃せない症状チェックリスト", "keyword": "犬 元気がない 原因"},
    {"slug": "cat-no-appetite", "title": "猫が食欲ない原因と対処法｜何日続いたら危険？", "keyword": "猫 食欲ない 対処法"},
    {"slug": "dog-cough-cause", "title": "犬の咳が止まらない原因｜フィラリア・ケンネルコフとの見分け方", "keyword": "犬 咳が出る 原因"},
    {"slug": "cat-sneezing-cause", "title": "猫のくしゃみが止まらない原因｜ウイルス感染・アレルギーの対処法", "keyword": "猫 くしゃみ 止まらない"},
    {"slug": "dog-bloating-cause", "title": "犬のお腹が張る原因と対処法｜緊急性が高い症状の見分け方", "keyword": "犬 お腹が張る 原因"},
    {"slug": "cat-worm-in-stool", "title": "猫の便に虫がいる原因と対処法｜寄生虫の種類と駆除方法", "keyword": "猫 便に虫がいる 対処"},
    {"slug": "dog-dandruff-cause", "title": "犬のフケが多い原因と対処法｜皮膚トラブルのサインを見逃さない", "keyword": "犬 フケが多い 原因"},
    {"slug": "cat-hair-loss", "title": "猫の毛が抜ける原因と病気｜季節性の抜け毛との違いを解説", "keyword": "猫 毛が抜ける 病気"},
    {"slug": "dog-shaking-cause", "title": "犬が震える原因と対処法｜寒さ・痛み・病気の見分け方", "keyword": "犬 震える 原因"},
    {"slug": "cat-excessive-thirst", "title": "猫が水をよく飲む理由と病気のサイン｜腎臓病・糖尿病との関係", "keyword": "猫 水をよく飲む 理由"},
    {"slug": "dog-frequent-urination", "title": "犬の尿の回数が多い原因｜泌尿器トラブルの対処法", "keyword": "犬 尿の回数が多い"},
    {"slug": "cat-blood-in-urine", "title": "猫の血尿の原因と対処法｜膀胱炎・尿路結石のケア方法", "keyword": "猫 血尿 原因"},
    {"slug": "dog-body-odor", "title": "犬の体臭が強い原因と対処法｜皮膚病・口臭・肛門腺との関係", "keyword": "犬 体臭が強い"},
    {"slug": "cat-eye-discharge", "title": "猫の目やにが多い原因と対処法｜結膜炎・ウイルス感染のケア", "keyword": "猫 目やに 多い"},

    # 寄生虫・薬直結（10記事）
    {"slug": "dog-heartworm-medicine-recommend", "title": "犬のフィラリア薬おすすめ5選｜動物病院より安く買う方法【2026年】", "keyword": "犬 フィラリア薬 おすすめ"},
    {"slug": "cat-heartworm-prevention", "title": "猫のフィラリア予防は必要？感染リスクと予防薬の選び方", "keyword": "猫 フィラリア予防 必要"},
    {"slug": "dog-flea-tick-medicine-compare", "title": "犬のノミダニ薬おすすめ比較｜スポット・チュアブル・首輪タイプの違い", "keyword": "犬 ノミダニ薬 比較"},
    {"slug": "cat-flea-medicine-ranking", "title": "猫のノミ駆除薬ランキング｜効果・安全性・コスパで徹底比較", "keyword": "猫 ノミ駆除 薬ランキング"},
    {"slug": "dog-roundworm-treatment", "title": "犬の回虫駆除方法と薬の選び方｜感染経路と予防法も解説", "keyword": "犬 回虫 駆除 方法"},
    {"slug": "cat-tapeworm-medicine", "title": "猫の条虫（サナダムシ）の駆除薬と対処法｜感染サインを見逃さない", "keyword": "猫 条虫 駆除 薬"},
    {"slug": "dog-ear-mite-treatment", "title": "犬の耳ダニの症状と治療法｜自宅でできるケアと薬の選び方", "keyword": "犬 耳ダニ 治療法"},
    {"slug": "cat-ear-mite-medicine", "title": "猫の耳ダニ薬比較｜スポットタイプと点耳薬どちらが効果的？", "keyword": "猫 耳ダニ 薬 比較"},
    {"slug": "pet-medicine-otc-vs-online", "title": "ペット駆虫薬は市販と通販どちらがいい？価格・成分・安全性を比較", "keyword": "犬 駆虫薬 市販 vs 通販"},
    {"slug": "pet-parasite-complete-guide", "title": "ペットの寄生虫完全ガイド｜フィラリア・ノミ・回虫の予防と対処法", "keyword": "ペット寄生虫 完全ガイド"},

    # 不安解消・安全性（10記事）
    {"slug": "pet-medicine-personal-import-safe", "title": "ペット医薬品の個人輸入は安全？法律・リスク・正しい選び方を解説", "keyword": "ペット医薬品 個人輸入 安全"},
    {"slug": "heartworm-medicine-side-effects", "title": "フィラリア薬の副作用はある？安全に使うための注意点【獣医師監修】", "keyword": "フィラリア薬 副作用"},
    {"slug": "flea-tick-medicine-danger", "title": "ノミダニ薬の危険性と安全な使い方｜過剰投与・誤使用を防ぐ", "keyword": "ノミダニ薬 危険性"},
    {"slug": "pet-medicine-human-effect", "title": "ペットの駆虫薬は人間に影響がある？接触時の注意点を解説", "keyword": "駆虫薬 人間に影響"},
    {"slug": "pet-medicine-fake-identification", "title": "ペット薬の偽物を見分ける方法｜正規品を安全に購入するポイント", "keyword": "ペット薬 偽物 見分け方"},
    {"slug": "overseas-pet-medicine-safety", "title": "海外のペット薬の安全性｜正規品確認の方法と信頼できる購入先", "keyword": "海外ペット薬 安全性"},
    {"slug": "pet-medicine-online-legal", "title": "ペット薬の通販は違法？個人輸入の法律と安全な購入方法を解説", "keyword": "ペット薬 通販 違法"},
    {"slug": "dog-cat-same-medicine", "title": "犬と猫に同じ薬は使える？種類別の注意点と危険な組み合わせ", "keyword": "犬 猫 同じ薬使える"},
    {"slug": "pet-medicine-overdose-risk", "title": "ペット薬の過剰摂取リスクと対処法｜誤飲・誤投与した場合の応急処置", "keyword": "ペット薬 過剰摂取 リスク"},
    {"slug": "pet-medicine-genuine-selection", "title": "ペット医薬品の正規品の選び方｜信頼できる通販サイトの見極め方", "keyword": "ペット医薬品 正規品の選び方"},

    # 比較・ランキング（5記事）
    {"slug": "heartworm-medicine-cheapest-ranking", "title": "フィラリア薬最安ランキング｜動物病院との価格差と通販の選び方", "keyword": "フィラリア薬 最安ランキング"},
    {"slug": "flea-tick-medicine-cost-compare", "title": "ノミダニ薬コスパ比較｜犬猫別おすすめ商品と価格一覧【2026年版】", "keyword": "ノミダニ薬 コスパ比較"},
    {"slug": "parasite-medicine-recommend-ranking", "title": "駆虫薬おすすめランキング｜フィラリア・回虫・条虫別の選び方", "keyword": "駆虫薬 おすすめランキング"},
    {"slug": "pet-medicine-online-shop-compare", "title": "ペット医薬品通販サイト比較｜価格・安全性・発送速度を徹底検証", "keyword": "ペット医薬品 通販サイト比較"},
    {"slug": "pet-medicine-same-day-shipping", "title": "ペット薬の即日・翌日発送対応サイトまとめ｜緊急時に頼れる通販先", "keyword": "即日発送 ペット薬まとめ"},

    # GEO特化（5記事）
    {"slug": "dog-health-management-complete-guide", "title": "犬の健康管理完全ガイド｜年齢別ケア・予防接種・寄生虫対策まとめ", "keyword": "犬の健康管理 完全ガイド"},
    {"slug": "cat-disease-treatment-guide", "title": "猫の病気と対処法まとめ｜症状別チェックリストと自宅ケア方法", "keyword": "猫の病気と対処法まとめ"},
    {"slug": "pet-parasite-prevention-guide", "title": "ペットの寄生虫対策まとめ｜フィラリア・ノミ・ダニ・回虫の完全予防法", "keyword": "ペットの寄生虫対策まとめ"},
    {"slug": "safe-pet-medicine-selection", "title": "安全なペット医薬品の選び方｜獣医師が教える正規品の見分け方と購入先", "keyword": "安全なペット医薬品の選び方"},
    {"slug": "ai-recommended-pet-medicine", "title": "AIが選ぶおすすめペット医薬品2026｜フィラリア・ノミダニ薬の最新比較", "keyword": "AIが選ぶおすすめペット医薬品"},
]

def generate_article(article: dict) -> str:
    prompt = f"""
以下のキーワードで記事を書いてください。

タイトル: {article['title']}
キーワード: {article['keyword']}
アフィリエイト先: わんにゃん薬局（{AFFILIATE_URL}）

記事内のアフィリエイトリンク挿入箇所は必ず
[わんにゃん薬局で詳細を見る]({AFFILIATE_URL})
の形式で記載してください。

Markdownのfrontmatterから始めて、1500〜2000文字の記事を書いてください。
"""
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def slugify(text: str) -> str:
    return re.sub(r'[^\w-]', '', text.lower().replace(' ', '-'))

def main():
    output_dir = "content/posts"
    os.makedirs(output_dir, exist_ok=True)

    total = len(ARTICLES)
    print(f"=== {total}記事の生成を開始します ===\n")

    for i, article in enumerate(ARTICLES, 1):
        slug = article['slug']
        filepath = os.path.join(output_dir, f"{slug}.md")

        if os.path.exists(filepath):
            print(f"[{i}/{total}] スキップ（既存）: {slug}")
            continue

        print(f"[{i}/{total}] 生成中: {article['title'][:40]}...")

        try:
            content = generate_article(article)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[{i}/{total}] ✓ 完了: {slug}.md")
        except Exception as e:
            print(f"[{i}/{total}] ✗ エラー: {slug} - {e}")

        # API制限対策
        if i < total:
            time.sleep(3)

    print(f"\n=== 生成完了 ===")
    print(f"出力先: {output_dir}/")
    print(f"\n次のコマンドでGitHubにpushしてください:")
    print("git add .")
    print('git commit -m "add 50 pet articles"')
    print("git push")

if __name__ == "__main__":
    main()
