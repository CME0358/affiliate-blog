# QOLmedia 週次改善ループ（PDCA）

## サマリー（3行以内）

**月曜15分**で数値記録→**火〜金**で1改善だけ実装→**金曜**でGA4確認。ループ記録は [[QOLmedia_週次KPIログ]]。戦略の優先順位は [[QOLmedia_戦略_キャッシュ×単価]] に固定。

---

## ループ（毎週）

```
Plan（月）→ Do（火〜金・1件）→ Check（金）→ Act（次週Planへ1行）
```

### 月曜 — Plan（15分）

- [ ] マネートラック：週間購入総額・承認件数・実効30%
- [ ] A8：HC / ファクタ / 睡眠の承認額（確定のみ）
- [ ] 楽天：先週の承認有無（あれば1行）
- [ ] [[QOLmedia_週次KPIログ]] に1行追記
- [ ] **今週のDoを1つだけ**決める（下表から）

### 火〜金 — Do（週1改善）

同時に2つ以上やらない。

| 優先 | チャネル | 改善例 |
| ---: | --- | --- |
| 1 | ペット | X文面差替・記事CTA・mttag周り |
| 2 | HC | LP見出し・モーダル・検索KW1記事 |
| 3 | ファクタ | 比較表順位・底部CTA・診断の出口 |
| 4 | 睡眠 | モーダル主CTA・stickyを診断へ |
| 5 | 楽天 | API403・generate_daily復旧 |

### 金曜 — Check（10分）

- [ ] GA4（`G-BS30YQY1N7`）：4LPの `primary_article_click` / `cta_click`
- [ ] Buffer：5本/日が `uploaded` か（楽天は `queue.csv`）
- [ ] 先週のDoが効いたか → [[QOLmedia_週次KPIログ]] の「所感」

### Act

- 効いた → 横展開（同型のLPへ）
- 効かない → 戻す or 次優先チャネルへ

---

## 自動運用

### 日次（触らない）

| 時刻 | 処理 |
| --- | --- |
| 18:30 | `run_daily.sh`（楽天→QOL4） |
| 20:00〜翌0:00 | Buffer予約投稿 |

Mac起動・ネット接続必須。楽天はAPI 403時は生成停止。

### 週次（自動）

| 時刻 | 処理 |
| --- | --- |
| **月曜 9:00** | `qol_weekly_report.py` → `reports/weekly_*_mon.md` + KPI行下書き + 通知 |
| **金曜 17:00** | 同上（`fri`）+ GA4・投入状況の再集計 |

```bash
# launchd 登録（初回のみ）
10_Projects/QOLmedia/scripts/launchd/install_weekly.sh

# 手動
10_Projects/QOLmedia/scripts/qol_weekly_loop.sh mon   # 月曜Plan
10_Projects/QOLmedia/scripts/qol_weekly_loop.sh fri   # 金曜Check
```

**GA4**: HTMLの `G-BS30YQY1N7` は計測用。週次の**自動数値取得**は `scripts/ga4.env`（プロパティID + サービスアカウント）設定時のみ。未設定時はレポートに[GA4コンソール](https://analytics.google.com/)確認リンクを出力。

```bash
cp scripts/ga4.env.example scripts/ga4.env   # 編集
scripts/setup_weekly.sh                       # 任意・API用venv
```

---

## サイクル履歴（要約）

| サイクル | 週 | Do | 結果 |
| --- | --- | --- | --- |
| 2 | 2026-08-05 | 共感3ch→sleep URL / HC LP費用訴求 / AGA記事 / 睡眠¥8k固定 / KPI全週¥0 | デプロイ後GA4で2週確認 |
| 1 | 2026-05-20週 | ファクタ底部CTA→No.1／睡眠sticky→診断モーダル／戦略Doc化 | 効果測定不能（KPI未入力） |

詳細: [[QOLmedia_週次KPIログ]]

---

## 刺さったフレーム

- 「週1改善だけ」でペットに50%時間を守る

## 刺さらなかったフレーム

- 4チャネル均等の週次$500追跡

## 関連ページ

- [[QOLmedia_戦略_キャッシュ×単価]]
- [[QOLmedia_週次KPIログ]]
- [[QOLmedia_4チャネル_$500日次]]

## 更新履歴

- 2026-05-20：週次レポート自動化（launchd 月9/金17・`reports/`）
- 2026-05-20：初版・サイクル1開始
