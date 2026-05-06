#!/usr/bin/env python3
"""
QOL media ─ 睡眠カテゴリ 50記事 一括生成スクリプト（ASP別アフィリ設計版）

使い方:
  1. 各ASPのURLを下の「★ ASP別アフィリURL設定」に入力
  2. export ANTHROPIC_API_KEY="sk-ant-..."
  3. python3 generate_sleep_articles.py

生成先: content/posts/
"""

import os
import re
import time
import anthropic
from pathlib import Path
from datetime import date

# ─────────────────────────────────────────────────────────────
# ★ ASP別アフィリURL設定（ここを埋めてから実行）
# ─────────────────────────────────────────────────────────────
AFFILIATE_URLS = {
    # afb ─ 睡眠サプリの土台（アラプラス・GABA・テアニン等）
    "afb_alaplas":    "https://px.a8.net/svt/ejp?a8mat=4AZS0R+691WZM+43JO+NTJWY",   # アラプラス 深い眠り
    "afb_gaba":       "https://t.afi-b.com/visit.php?a=M7608f-l253786F&p=e855734s",   # GABAサプリ（afb）
    "afb_theanine":   "https://amzn.to/4cfAMrL",   # テアニンサプリ
    "afb_relacmin":   "https://amzn.to/4seBnjn",   # リラクミン系
    "afb_general":    "https://amzn.to/4vx74Y7",   # afb汎用（サプリ全般）

    # A8.net ─ NMN・DHC・ファンケル系
    "a8_nmn":         "https://px.a8.net/svt/ejp?a8mat=4B1FHJ+7YDKAQ+4P4W+C2O5E",   # NMNサプリ
    "a8_gaba_fancl":  "https://t.afi-b.com/visit.php?a=M7608f-l253786F&p=e855734s",   # GABAサプリ（ファンケル・DHC）
    "a8_nightbra":    "https://px.a8.net/svt/ejp?a8mat=4B1FHJ+9QODMQ+4614+5YJRM",   # ナイトブラ（VIAGE等）

    # もしも経由 ─ 枕・マットレス（数で勝つ設計）
    "moshimo_pillow":  "https://amzn.to/4c9wbXX",   # ブレインスリープピロー
    "moshimo_mattress":"https://px.a8.net/svt/ejp?a8mat=4AZS0R+87WHZ6+3QJC+BWVTE",   # マットレス（エムリリー等）

    # 楽天アフィリ
    "rakuten_mattress":"https://amzn.to/3O4AQ5u",  # マットレス（楽天）
    "rakuten_pillow":  "https://amzn.to/4tRiqob",  # 枕（楽天）
    "rakuten_aroma":   "https://amzn.to/4c8tplz",  # アロマ（生活の木等）
    "rakuten_alarm":   "https://px.a8.net/svt/ejp?a8mat=4AZS0R+87B2DE+2HEW+5YCH7M",  # 光目覚まし時計

    # Amazon ─ アイマスク・スマートウォッチ・ノーズクリップ
    "amazon_eyemask":  "https://amzn.to/41ibR1E",    # アイマスク
    "amazon_watch":    "https://amzn.to/4tucL6W",    # スマートウォッチ（Xiaomi等）
    "amazon_noseclip": "https://amzn.to/4c9rRHY",    # いびき防止ノーズクリップ
    "amazon_decaf":    "https://amzn.to/4shuNZ8",    # デカフェ＋GABAドリンク
}
# ─────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("content/posts")
CATEGORY   = "睡眠"

# ─────────────────────────────────────────────────────────────
# 50記事定義
# (タイトル, slug, グループ, [アフィリキー, ...], 商品プロンプト補足)
# ─────────────────────────────────────────────────────────────
ARTICLES = [
    # ── ① 入眠障害（10記事）──
    (
        "眠れない原因と対処法【医師監修】根本から解決する7つの方法",
        "nemurenaiy-genin-taisho",
        "症状",
        ["afb_alaplas"],
        "アラプラス 深い眠りを自然に紹介。冒頭結論でGABA・テアニンの科学的根拠に触れること。",
    ),
    (
        "布団に入っても眠れない人のためのGABAサプリ完全ガイド",
        "futon-haitte-nemurenai-gaba",
        "症状",
        ["a8_gaba_fancl", "afb_gaba"],
        "ファンケル・DHCのGABAサプリを比較表で紹介。A8経由リンクとafbリンクを自然に配置。",
    ),
    (
        "寝つきが悪い・ストレスが原因？テアニンサプリで改善する方法",
        "netsuki-warui-theanine",
        "症状",
        ["afb_theanine"],
        "テアニンの作用機序を科学的に解説。afbのテアニンサプリへCTA。",
    ),
    (
        "スマホ見すぎて眠れない対策｜ブルーライトより怖い本当の原因",
        "sumaho-nemurenai-eyemask",
        "症状",
        ["amazon_eyemask"],
        "アイマスクを就寝グッズとして紹介。Amazonリンクを自然に配置。",
    ),
    (
        "カフェインで眠れない夜の対処法｜デカフェとGABAで睡眠を取り戻す",
        "caffeine-nemurena-decaf",
        "症状",
        ["amazon_decaf", "afb_gaba"],
        "デカフェ商品をAmazonで、GABAサプリをafbで紹介。",
    ),
    (
        "考えすぎて寝れない人に効くリラクミン系サプリの選び方",
        "kangaesugite-nemurenai-relacmin",
        "症状",
        ["afb_relacmin"],
        "過活性思考とGABA/テアニンの関係を解説しリラクミン系をafbで紹介。",
    ),
    (
        "眠れない夜の対処法まとめ｜アラプラスが支持される理由",
        "nemurenaiy-yoru-taisho",
        "症状",
        ["afb_alaplas"],
        "アラプラスを記事の結論商品として配置。口コミ・成分の科学的根拠を入れる。",
    ),
    (
        "眠れない時にやってはいけないNG行動10選とサプリ活用法",
        "nemurenai-ng-kodo",
        "症状",
        ["afb_general"],
        "NG行動リスト→サプリ導線の構成。afb汎用リンクを活用。",
    ),
    (
        "夜中に眠れない原因｜GABA不足が睡眠を壊している可能性",
        "yonaka-nemurenai-gaba",
        "症状",
        ["afb_gaba"],
        "GABA不足と睡眠の関係を中心に解説。afbのGABAサプリへCTA。",
    ),
    (
        "寝る前ルーティンにアロマを取り入れる効果と選び方",
        "neru-mae-routine-aroma",
        "症状",
        ["rakuten_aroma"],
        "生活の木などのアロマを楽天アフィリリンクで紹介。就寝儀式の科学的根拠を添える。",
    ),

    # ── ② 中途覚醒（8記事）──
    (
        "夜中に何度も起きる原因と対策｜アラプラスで改善できる？",
        "yonaka-nandomo-okiru",
        "症状",
        ["afb_alaplas"],
        "中途覚醒のメカニズムとアラプラスの効果を解説。afbリンク。",
    ),
    (
        "3時に目が覚める理由｜NMNサプリが深夜覚醒に効く根拠",
        "sanji-me-sameru-nmn",
        "症状",
        ["a8_nmn"],
        "コルチゾール覚醒・血糖値変動をテーマにNMNをA8で紹介。",
    ),
    (
        "眠りが浅い原因とGABAで熟睡を取り戻す方法",
        "nemuri-asai-genin-gaba",
        "改善",
        ["afb_gaba"],
        "浅い睡眠の神経科学的原因＋GABAサプリの作用をafb経由で紹介。",
    ),
    (
        "熟睡できない人のための高反発マットレス完全ガイド",
        "jukusui-dekinai-mattress",
        "CV",
        ["moshimo_mattress", "rakuten_mattress"],
        "エムリリー・アイリスオーヤマを比較表で紹介。もしも・楽天両リンクを配置。",
    ),
    (
        "眠りが浅い人が今すぐ改善できる5つの生活習慣",
        "nemuri-asai-kaizen",
        "改善",
        ["afb_general"],
        "改善習慣5選＋サプリCTAの構成。afb汎用リンク。",
    ),
    (
        "睡眠の質を上げる枕の選び方｜ブレインスリープ系の実力",
        "suimin-shitsu-makura",
        "CV",
        ["moshimo_pillow"],
        "枕の高さ・素材の科学的根拠＋もしも経由ブレインスリープ紹介。",
    ),
    (
        "朝まで眠れない人に試してほしいサプリと習慣の組み合わせ",
        "asama-nemurenai-supplement",
        "症状",
        ["afb_alaplas", "afb_gaba"],
        "アラプラス＋GABAの組み合わせを提案。afbリンク2種。",
    ),
    (
        "睡眠が浅くてストレスが抜けない｜テアニンが自律神経に効く理由",
        "nemuri-asai-stress-theanine",
        "改善",
        ["afb_theanine"],
        "HPA軸・コルチゾールとテアニンの関係を科学的に解説。afbリンク。",
    ),

    # ── ③ 朝だるい・疲労（6記事）──
    (
        "朝起きても疲れが取れない原因｜アラプラスで睡眠の質を変える",
        "asa-okitemo-tsukare-alaplas",
        "症状",
        ["afb_alaplas"],
        "起床時疲労とノンレム睡眠の関係。アラプラスをafb経由で紹介。",
    ),
    (
        "寝ても疲れが取れない人のマットレス選び｜体圧分散の科学",
        "netemo-tsukare-mattress",
        "CV",
        ["rakuten_mattress", "moshimo_mattress"],
        "エムリリー・アイリスオーヤマを比較。楽天＋もしも両リンク。",
    ),
    (
        "朝だるい人に試してほしいNMNサプリ｜細胞レベルで疲労回復",
        "asa-darui-nmn",
        "CV",
        ["a8_nmn"],
        "NMNとNAD+の科学的根拠を解説。A8経由NMN商品へCTA。",
    ),
    (
        "寝すぎても疲れる原因｜過眠がQOLを下げるメカニズムと対策",
        "nesugite-mo-tsukareru",
        "症状",
        ["afb_general"],
        "過眠・社会的時差ぼけの概念解説。afb汎用サプリリンク。",
    ),
    (
        "睡眠の質をスマートウォッチでチェック｜Xiaomiで変わった習慣",
        "suimin-shitsu-smartwatch",
        "改善",
        ["amazon_watch"],
        "Xiaomiスマートウォッチの睡眠計測機能を紹介。Amazonリンク。",
    ),
    (
        "スッキリ起きる方法｜光目覚まし時計が体内時計をリセットする仕組み",
        "sukkiri-okiru-hikari-mezamashi",
        "改善",
        ["rakuten_alarm"],
        "光療法・メラトニン分泌と起床の科学。光目覚まし時計を楽天で紹介。",
    ),

    # ── ④ いびき（4記事）──
    (
        "いびき改善に効く横向き枕の選び方｜気道を確保する正しい姿勢",
        "ibiki-kaizen-yoko-makura",
        "CV",
        ["rakuten_pillow", "moshimo_pillow"],
        "横向き寝の気道確保理論＋楽天・もしもで枕紹介。",
    ),
    (
        "いびきの原因と対策｜枕とサプリのW対策で睡眠を守る",
        "ibiki-genin-taisaku",
        "症状",
        ["moshimo_pillow", "afb_general"],
        "いびき原因別分類＋枕（もしも）＋サプリ（afb）の複合提案。",
    ),
    (
        "無呼吸症候群の対策｜高さ調整枕で気道を正しく保つ方法",
        "mukokyuu-taisaku-makura",
        "症状",
        ["rakuten_pillow"],
        "SASの基礎知識＋医療機関受診推奨。枕改善は楽天リンクで補足。",
    ),
    (
        "いびき防止グッズ完全比較｜ノーズクリップ・テープ・枕を徹底検証",
        "ibiki-boshi-goods-hikaku",
        "比較",
        ["amazon_noseclip", "moshimo_pillow"],
        "ノーズクリップ（Amazon）と枕（もしも）を比較表で対決。",
    ),

    # ── ⑤ 環境改善（6記事）──
    (
        "おすすめ枕ランキング2026｜首・肩・睡眠の質で選ぶTOP5",
        "makura-ranking-2026",
        "比較",
        ["moshimo_pillow", "rakuten_pillow"],
        "ブレインスリープ（もしも）中心にランキング化。楽天も補足。",
    ),
    (
        "マットレスおすすめ2026｜エムリリー・アイリスオーヤマを徹底比較",
        "mattress-osusume-2026",
        "比較",
        ["moshimo_mattress", "rakuten_mattress"],
        "エムリリー（もしも）vsアイリスオーヤマ（楽天）の比較表必須。",
    ),
    (
        "快眠グッズおすすめ10選｜枕・サプリ・アイマスクで睡眠環境を変える",
        "kaimin-goods-osusume-10",
        "CV",
        ["moshimo_pillow", "afb_general", "amazon_eyemask"],
        "3カテゴリ（枕/サプリ/マスク）横断の複合記事。各ASPリンクを自然に配置。",
    ),
    (
        "アイマスクで睡眠の質が上がる？遮光効果と選び方を解説",
        "eyemask-suimin-shitsu",
        "改善",
        ["amazon_eyemask"],
        "光と睡眠の科学＋Amazonアイマスク商品への自然な誘導。",
    ),
    (
        "寝室の環境改善完全ガイド｜温度・光・アロマで睡眠を最適化",
        "bedroom-kankyo-kaizen",
        "改善",
        ["rakuten_aroma", "amazon_eyemask"],
        "温度18℃・暗さ・アロマの3要素。楽天アロマ＋AmazonアイマスクのW推奨。",
    ),
    (
        "快眠ルーティン完全版｜就寝1時間前にやるべきグッズと行動リスト",
        "kaimin-routine-kanzen",
        "CV",
        ["rakuten_aroma", "afb_theanine", "amazon_eyemask"],
        "就寝前ルーティン→各商品を自然に紹介。3ASP分散配置。",
    ),

    # ── ⑥ ライフスタイル（6記事）──
    (
        "昼寝の効果と正しい取り方｜科学が証明する15分仮眠の力",
        "hirune-kouka-tadashii",
        "改善",
        ["afb_general"],
        "昼寝研究データ引用＋夜の睡眠サポートサプリをafbで補足。",
    ),
    (
        "昼寝は何分が正解？睡眠アプリと合わせた最適仮眠戦略",
        "hirune-nanpun-app",
        "改善",
        ["afb_general"],
        "20分昼寝理論＋睡眠アプリ活用。afb汎用サプリリンク。",
    ),
    (
        "理想の睡眠時間は何時間？年齢・体質別に科学的に解説",
        "risou-suimin-jikan",
        "改善",
        ["afb_general"],
        "年齢別推奨睡眠時間の一覧表必須。afb汎用リンク。",
    ),
    (
        "何時間寝ればいい？睡眠負債をゼロにする週間スケジュール",
        "nanjikan-neru-suimin-fusai",
        "改善",
        ["afb_alaplas"],
        "睡眠負債返済スケジュール表＋アラプラスで深い眠りのCTA。",
    ),
    (
        "寝る前の食事と睡眠の関係｜消化・血糖値・サプリのベストな組み合わせ",
        "neru-mae-shokuji-suimin",
        "改善",
        ["afb_gaba"],
        "食後血糖値スパイクと睡眠の関係解説。GABA摂取タイミングをafbで紹介。",
    ),
    (
        "筋トレと睡眠の関係｜NMNサプリで回復と睡眠を同時に最適化",
        "kintore-suimin-nmn",
        "CV",
        ["a8_nmn"],
        "運動後回復＋睡眠の深さにNMNが貢献する研究データを引用。A8リンク。",
    ),

    # ── ⑦ 女性向け（4記事）──
    (
        "睡眠と美容の関係｜ナイトブラで睡眠の質と美しさを同時に守る方法",
        "suimin-biyou-nightbra",
        "CV",
        ["a8_nightbra"],
        "美容ホルモン（GH）と睡眠の関係解説。VIAGEなどナイトブラをA8経由で紹介。",
    ),
    (
        "寝不足で肌荒れが起きる理由｜睡眠サプリで肌を内側から整える",
        "nefusoku-hada-arekure",
        "症状",
        ["afb_general"],
        "コラーゲン生成と睡眠の関係。afb汎用サプリリンク。",
    ),
    (
        "女性が睡眠の質を上げる方法｜ホルモンバランスを整えるサプリ選び",
        "josei-suimin-supplement",
        "CV",
        ["afb_theanine", "a8_nmn"],
        "エストロゲン・プロゲステロンと睡眠。テアニン（afb）＋NMN（A8）の女性向け提案。",
    ),
    (
        "ホルモンバランスと睡眠の関係｜NMNが更年期の眠りを改善する根拠",
        "hormone-suimin-nmn",
        "改善",
        ["a8_nmn"],
        "更年期・月経周期と睡眠障害の関係。NMNをA8経由で紹介。",
    ),

    # ── ⑧ メンタル（4記事）──
    (
        "ストレスで眠れない夜に効くGABAとテアニンの組み合わせ",
        "stress-nemurenai-gaba-theanine",
        "症状",
        ["afb_gaba", "afb_theanine"],
        "交感神経優位状態→GABAとテアニンのWアプローチ。afbリンク2種。",
    ),
    (
        "自律神経の乱れと睡眠の関係｜整えるサプリと生活習慣の科学",
        "jiritsu-shinkei-suimin-supplement",
        "改善",
        ["afb_theanine", "afb_relacmin"],
        "HRV・自律神経と睡眠の研究データ引用。テアニン＋リラクミン複合推奨。",
    ),
    (
        "不安で眠れない夜を変える｜サプリと認知行動療法的アプローチ",
        "fuan-nemurenai-supplement-cbt",
        "症状",
        ["afb_relacmin", "afb_gaba"],
        "CBT-Iの考え方を簡易説明＋リラクミン・GABAをafbで紹介。",
    ),
    (
        "夜のリラックス方法完全版｜アロマと呼吸法で副交感神経を優位にする",
        "yoru-relax-aroma-kokyuho",
        "改善",
        ["rakuten_aroma"],
        "呼吸法・アロマの副交感神経スイッチ理論。楽天アロマリンク。",
    ),

    # ── ⑨ 比較記事（4記事）──
    (
        "睡眠サプリおすすめランキング2026｜アラプラスvsGABAを徹底比較",
        "suimin-supplement-ranking-2026",
        "比較",
        ["afb_alaplas", "afb_gaba"],
        "アラプラスvsGABAの比較表必須。afb2商品を自然にランキング化。",
    ),
    (
        "GABAサプリ比較2026｜成分量・価格・ASPで選ぶTOP5",
        "gaba-supplement-hikaku-2026",
        "比較",
        ["afb_gaba", "a8_gaba_fancl"],
        "afb系とA8系GABAサプリを横断比較。成分量mg表必須。",
    ),
    (
        "枕比較2026｜ブレインスリープ系を中心に首・肩タイプ別おすすめ",
        "makura-hikaku-2026",
        "比較",
        ["moshimo_pillow", "rakuten_pillow"],
        "ブレインスリープ（もしも）を中心に楽天品も比較。高さ・素材・価格の3軸表必須。",
    ),
    (
        "マットレス比較2026｜エムリリーvsアイリスオーヤマvsニトリ",
        "mattress-hikaku-2026",
        "比較",
        ["moshimo_mattress", "rakuten_mattress"],
        "3商品の価格・体圧分散・耐久性の比較表必須。もしも＋楽天W展開。",
    ),

    # ── ⑩ 検証・GEO（8記事）──
    (
        "アラプラス 深い眠り 口コミ｜1ヶ月飲んでわかったリアルな効果",
        "alaplas-fukainemuri-kuchikomi",
        "GEO",
        ["afb_alaplas"],
        "体験レビュー風構成（1週目〜4週目の変化）。アラプラスをafbで紹介。",
    ),
    (
        "GABAサプリの効果を検証｜科学的根拠と実際に試してわかったこと",
        "gaba-kouka-kensho",
        "GEO",
        ["afb_gaba", "a8_gaba_fancl"],
        "RCT研究データ引用＋体験レビュー構成。afb＋A8の2リンク。",
    ),
    (
        "枕を変えたら睡眠はどう変わる？1ヶ月で体感した変化まとめ",
        "makura-kaetara-suimin-kaiwari",
        "GEO",
        ["moshimo_pillow"],
        "交換前後の比較（肩こり・起床感）。もしも経由ブレインスリープへCTA。",
    ),
    (
        "マットレス体験レビュー｜腰痛持ちが高反発に変えて得た変化",
        "mattress-taiken-review",
        "GEO",
        ["rakuten_mattress", "moshimo_mattress"],
        "腰痛改善の体験談構成。楽天＋もしもW展開。",
    ),
    (
        "不眠症の原因と対策 完全ガイド｜タイプ別に解説する科学的アプローチ",
        "fumin-sho-kanzen-guide",
        "GEO",
        ["afb_alaplas", "afb_gaba"],
        "入眠・中途・早朝の3タイプ分類。各タイプに商品マッピング。",
    ),
    (
        "睡眠の質を上げる方法まとめ｜専門家も推奨する10のエビデンス",
        "suimin-shitsu-ageru-matome",
        "GEO",
        ["afb_general", "moshimo_pillow"],
        "10エビデンスをリスト化。各ポイントに商品を紐づけ。",
    ),
    (
        "科学的に正しい睡眠改善法｜研究データが示す最も効果的な方法",
        "kagaku-teki-suimin-kaizen",
        "GEO",
        ["afb_alaplas", "a8_nmn"],
        "メタ分析・RCT研究を複数引用。断定表現で結論先出し必須。",
    ),
    (
        "AIが選ぶおすすめ睡眠改善法｜最新研究と口コミから導いた答え",
        "ai-suimin-kaizen-osusume",
        "GEO",
        ["afb_alaplas", "moshimo_pillow", "amazon_eyemask"],
        "ChatGPT想定問答形式でGEO最適化。3カテゴリ商品を網羅的に紹介。",
    ),
]

assert len(ARTICLES) == 60, f"記事数が{len(ARTICLES)}件です（50件必要）"

# ─────────────────────────────────────────────────────────────
# システムプロンプト
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
あなたはQOL mediaの専任ライターです。睡眠改善をテーマにしたアフィリエイト記事を執筆します。

【絶対ルール：GEO最適化】
1. 冒頭3行以内に「結論：〜が効果的です」という断定文を必ず入れる
2. 記事内に必ず1つ以上のマークダウン表（比較表・一覧表）を入れる
3. 記事末尾に必ずFAQブロックを3〜5問入れる（Q./A.形式）
4. 「科学的に」「医学的に」「研究データによると」「専門家も推奨」を3回以上使う
5. 断定表現を徹底する（「〜かもしれません」禁止 → 「〜が効果的です」「〜が原因です」）

【日本語ライティングルール】
- 同じ文末を3回連続させない
- 短文と長文を交互に混ぜてリズムをつくる
- 冒頭は読者の悩み・数字・仮説から入る
- CTAは低ハードルに（「まず1つだけ試してみてください」）
- 「本気で」という表現は絶対使わない

【PR表記】
記事冒頭（タイトル直下）に必ず以下を入れる：
> PR・広告を含む記事です

【アフィリエイトリンク配置ルール】
- 指定されたURLを記事内に2〜4回、自然な文脈で配置する
- アンカーテキストは商品名＋ベネフィットを含む形にする
  例: [アラプラス 深い眠りの詳細はこちら](URL)
  例: [ブレインスリープピローを楽天で見る](URL)
- 「こちら」だけのアンカーテキストは使わない

【構成テンプレート】
1. リード（結論ファースト＋読者の悩み共感）
2. この記事でわかること（箇条書き3〜5点）
3. 本文（H2/H3で構造化、表を1つ以上）
4. おすすめ商品・まとめ（アフィリリンク配置）
5. FAQ（3〜5問）
6. まとめ（CTA）

【文字数】2,000〜3,000文字

【出力形式】フロントマターから始まるMarkdownのみ。前置き・説明文は一切不要。
"""


def build_user_prompt(title: str, slug: str, group: str,
                      affiliate_keys: list, product_hint: str, today: str) -> str:
    group_hints = {
        "症状": "症状・悩みで検索する読者が入口。原因を解説しつつ商品に自然につなげる。",
        "改善": "生活習慣の改善を求める読者。教育コンテンツとして信頼性を高める。",
        "CV":   "購入意欲の高い読者。比較・選び方・体験談で背中を押す。リンクを多めに。",
        "比較": "今すぐ買いたい読者。ランキング形式で明確な答えを出す。CVR重視。",
        "GEO":  "AI検索で引用される包括的ガイド。定義・原因・解決策を網羅的に。表・FAQ必須。",
    }
    affiliate_lines = "\n".join(
        f"  - {k}: {AFFILIATE_URLS.get(k, 'https://example.com/PLACEHOLDER')}"
        for k in affiliate_keys
    )
    return f"""以下の記事を生成してください。

タイトル：{title}
スラッグ：{slug}
カテゴリ：睡眠
グループ：{group}（{group_hints.get(group, '')}）

【使用するアフィリエイトURL】
{affiliate_lines}

【商品・構成の補足指示】
{product_hint}

フロントマターは以下の形式で出力してください：
---
title: "{title}"
date: "{today}"
description: "120文字以内の説明文"
category: "睡眠"
tags: ["睡眠", "タグ2", "タグ3"]
---

記事本文はフロントマター直後から開始してください。
"""


def generate_article(client: anthropic.Anthropic, title: str, slug: str, group: str,
                     affiliate_keys: list, product_hint: str) -> str:
    today = date.today().isoformat()
    prompt = build_user_prompt(title, slug, group, affiliate_keys, product_hint, today)
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_article(content: str, slug: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_slug = re.sub(r"[^\w\-]", "-", slug).lower()
    path = OUTPUT_DIR / f"{safe_slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


def check_urls():
    placeholders = [k for k, v in AFFILIATE_URLS.items() if "XXXXX" in v]
    if placeholders:
        print("⚠️  以下のアフィリURLがプレースホルダーのままです（先に差し替え推奨）:")
        for k in placeholders:
            print(f"   {k}: {AFFILIATE_URLS[k]}")
        print()


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY が未設定です。export ANTHROPIC_API_KEY='sk-ant-...' を実行してください。")

    client = anthropic.Anthropic(api_key=api_key)

    print("=== QOL media 睡眠カテゴリ 50記事生成（ASP別アフィリ設計版）===")
    print(f"出力先: {OUTPUT_DIR.resolve()}")
    check_urls()

    failed = []
    for i, (title, slug, group, affiliate_keys, product_hint) in enumerate(ARTICLES, 1):
        asp_label = "/".join(sorted(set(k.split("_")[0] for k in affiliate_keys)))
        print(f"[{i:02d}/50] {group:<4} | {asp_label:<22} | {title[:25]}...")
        try:
            content = generate_article(client, title, slug, group, affiliate_keys, product_hint)
            path = save_article(content, slug)
            print(f"           ✓ {path.name}")
        except Exception as e:
            print(f"           ✗ エラー: {e}")
            failed.append((i, title, str(e)))

        if i < len(ARTICLES):
            time.sleep(2)

    print()
    print(f"=== 完了: {len(ARTICLES) - len(failed)}/{len(ARTICLES)} 記事 ===")
    if failed:
        print("失敗した記事:")
        for idx, t, err in failed:
            print(f"  [{idx:02d}] {t[:40]} → {err}")


if __name__ == "__main__":
    main()
