# QOLmedia コンディション改善 × 日次運用マップ

## サマリー

**30〜50代男性のコンディション改善メディア** + **収益導線（pet/factoring/sleep/haircare）**。Xは共感・保存・フォロー獲得とLP導線を並行。2026-08-05: pet/factoring を再開（7ch）。

---

## 現行7チャネル

| チャネル | CSV | 予定時刻（JST） | 形式 | 備考 |
| --- | --- | --- | --- | --- |
| 疲労 | [[x_posts_fatigue_49.csv]] | **08:00** | URLなし | 共感投稿 |
| 集中力 | [[x_posts_focus_49.csv]] | **12:00** | URLなし | 共感投稿 |
| **ペット** | [[x_posts_pet_49.csv]] | **15:00** | 本文 + LP | pet-lp.html（2026-08-05再開） |
| ストレス | [[x_posts_stress_49.csv]] | **18:00** | URLなし | 共感投稿 |
| **ファクタ** | [[x_posts_factoring_49.csv]] | **20:00** | 本文 + LP | factoring-lp.html（2026-08-05再開） |
| 睡眠 | [[x_posts_sleep_49.csv]] | **21:00** | 本文 + LP | sleep-guide.html |
| ヘアケア | [[x_posts_hc_49.csv]] | **23:00** | 本文 + LP | hc-guide.html |

詳細KPI: [[ペットアフィ_KPI]] · [[ファクタリングアフィ_KPI]] · [[睡眠アフィ_KPI]] · [[ヘアケアアフィ_KPI]]  
ロードマップ: [[QOLmedia_100万ロードマップ]] · [[QOLmedia_KPIベースライン]]  
週次ループ: [[QOLmedia_週次改善ループ]] · [[QOLmedia_週次KPIログ]]

### 日次 X スケジュール

`rakuten-affiliate/rakuten-x-affiliate/run_daily.sh` → `upload_qol_x_buffer.py`  
基準日は **生成日+1日**（`SCHEDULE_DATE_OFFSET_DAYS=1`）。

ローテ: `qol_x_state.json`（keys: sleep, focus, fatigue, haircare, stress · 各CSV 49行・**1日1行**）  
ログ: `qol_x_upload_log.csv`

---

## 停止カテゴリ（2026-06-06）

| カテゴリ | 状態 | 備考 |
| --- | --- | --- |
| ~~ペット~~ | **2026-08-05 再開** | `x_posts_pet_49.csv` 復帰 |
| ~~ファクタリング~~ | **2026-08-05 再開** | `x_posts_factoring_49.csv` 復帰 |
| 楽天アフィ | 停止 | `archive/deprecated/rakuten-x-affiliate/` |

旧KPIドキュメント: [[ペットアフィ_KPI]] · [[ファクタリングアフィ_KPI]]

---

## 導線の型

### A型：LP + 記事（睡眠）

```
流入 → sleep-guide → 記事 → ASP
```

### B型：LP直CV（ヘアケア）

```
流入 → hc-guide → カウンセリング予約
```

### C型：共感のみ（集中力・疲労・ストレス）

```
X共感投稿 → プロフィール遷移 → フォロー
（商品・URLなし）
```

---

## 計測共通

- GA4: `G-BS30YQY1N7`
- Clarity: `w6fgeud38o`
- 睡眠: `primary_article_click`
- ヘアケア: `cta_click` / `modal_open`

---

## 更新履歴

- 2026-08-05：7ch再開（pet 15:00 / factoring 20:00）・100万ロードマップ連携
- 2026-06-06：コンディション改善メディアへ再設計（pet/factoring/rakuten 一時停止・5ch新スケジュール）
- 2026-05-20：4チャネルマップ初版
