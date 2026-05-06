# QOL media LP 引き継ぎメモ

作成日：2026-05-05

---

## LP一覧・ファイル名

| LP | ファイル名 | URL |
|---|---|---|
| 睡眠 | `public/sleep-guide.html` | https://www.qolmedia.info/sleep-guide.html |
| ペット医薬品 | `public/pet-lp.html` | https://www.qolmedia.info/pet-lp.html |
| ファクタリング | `public/factoring-lp.html` | https://www.qolmedia.info/factoring-lp.html |
| ヘアケア・植毛 | `public/hc-guide.html` | https://www.qolmedia.info/hc-guide.html |

---

## トラッキング設定（全LP共通）

| 項目 | 値 |
|---|---|
| GA4 | `G-BS30YQY1N7` |
| Clarity | `w6fgeud38o` |
| CTA色 | `#06C755` |
| リポジトリ | `~/Downloads/affiliate-blog` |

---

## 本スレッドの作業内容（2026-05-05）

### hc-guide
- フッター追加（factoring-lpを参考に統一）
  - プライバシーポリシー / 運営について / お問い合わせ / © 2026 QOL media
  - 背景色：`#0f1c2e`
- メタタイトルに `| QOL media` を追加
  - `クリニック選びで後悔しないために｜ヘアケア選びの専門情報サイト | QOL media`

### pet-lp
- CTAボタン4箇所をURL遷移に変更（FV `▶ 愛犬・愛猫どちらですか？` のみモーダル維持）
  - 遷移先URL：`https://mttag.com/s/CiN-gOTx1i8`
  - 対象：ヘッダー / インラインCTA / MAIN CTA / stickyボタン
  - GA4 `cta_click` イベントに `event_label` で各箇所を識別
- mttagリンク全6箇所に `referrerpolicy="no-referrer"` を追加
  - 原因：トラッキングリンクのリダイレクトループ（ERR_TOO_MANY_REDIRECTS）
  - 直接URL入力では正常動作することを確認済み
- FV H1の改行位置を修正
  - 変更前：`愛犬・愛猫のお薬、動物病院で` / `買うのが当たり前ですか？`
  - 変更後：`愛犬・愛猫のお薬` / `動物病院で` / `買うのが当たり前ですか？`
  - 読点（、）も同時に削除

---

## CTAボタン構成（pet-lp 最新）

| 箇所 | テキスト | アクション | GA4ラベル |
|---|---|---|---|
| FV | ▶ 愛犬・愛猫どちらですか？ | モーダル起動 | — |
| ヘッダー | ▶ お薬を探す | URL遷移 | `header-cta` |
| インラインCTA | ▶ ペットのお薬を探す | URL遷移 | `inline-cta` |
| MAIN CTA | ペットのお薬を今すぐ探す | URL遷移 | `main-cta` |
| stickyボタン | 今すぐ探す | URL遷移 | `sticky-cta` |

---

## アフィリリンク設定

### pet-lp（もしもアフィリエイト）

| 項目 | 値 |
|---|---|
| 遷移先URL | `https://mttag.com/s/CiN-gOTx1i8` |
| 備考 | referrerpolicyループ問題あり・no-referrer対応済み |

### sleep-guide（A8.net / ブレインスリープ）

| 商品 | URL |
|---|---|
| ブレインスリープNMN9000 | `https://px.a8.net/svt/ejp?a8mat=4AZS0Q+FLFTS2+4KU6+ZRXQP` |
| ブレインスリープピロー | `https://px.a8.net/svt/ejp?a8mat=4AZS0R+6C130I+4KU6+61Z81` |
| ブレインスリープマットレスフロート | `https://px.a8.net/svt/ejp?a8mat=4AZS0R+6BFNEQ+4KU6+BYLJL` |

### hc-guide（A8.net / アルモ形成クリニック）

| 項目 | 値 |
|---|---|
| アフィリURL | `https://px.a8.net/svt/ejp?a8mat=4B1R5O+GF7I0Y+5H8A+5YZ75` |
| クリニックB | 現在`display:none`（ASP審査通過後に復活） |

---

## Google広告の状況

| LP | キャンペーン | ステータス |
|---|---|---|
| hc-guide | [hair]GDN_10円設定_LP誘導 | 有効（制限付き）※審査中 |
| sleep-guide | [SLEEP]GDN_10円設定_LP誘導 | 有効（制限付き） |
| factoring-lp | [factoring]GDN | 運用中 |

---

## 未解決の問題

- mttagリンクのリダイレクトループ：`referrerpolicy="no-referrer"` 追加済みだが効果未確認。解消しない場合はASP（もしもアフィリエイト）の管理画面でトラッキング設定を確認する。

---

## HTML修正ルール（重要）

- 修正作業時は**必ず直近で作成したHTMLをアップロード**する。旧バージョンを読み込まない。
- 直近の作成から**6時間以上経過している場合**は、現在使用中のHTMLをアップロードするよう確認を促す。
- ターミナルやNotionが `e.target` を `[e.target](http://e.target)` に自動変換することがある。**コマンドはヒアドキュメント形式（`<< 'EOF'`）を使うか、直接手入力すること**。
- pushコマンドは修正完了時に毎回セットで表示する。

---

## pushコマンド（定型）

```bash
cd ~/Downloads/affiliate-blog && git add public/[ファイル名] && git commit -m "[メッセージ]" && git push origin main
```

---

## sitemap・SEO状況

- `https://www.qolmedia.info/sitemap.xml` → 正常（117件・記事URLあり）
- インデックス登録済み：14ページ
- `robots.ts` でSitemap明示済み


[[QOLmedia_引き継ぎメモ_20260409]]
[[QOLmedia_引き継ぎメモ_20260411]]
[[QOLmedia_引き継ぎメモ_20260411_夜]]
[[QOLmedia_引き継ぎメモ_20260418]]
[[QOLmedia_引き継ぎメモ_20260419]]
[[pet-lp_引き継ぎメモ_20260421]]
[[hair-transplant-lp_引き継ぎメモ_20260422]]
[[hair-transplant-lp_引き継ぎメモ_20260423]]
[[qolmedia-lp_引き継ぎメモ_20260427]]
[[qolmedia-lp_引き継ぎメモ_20260428]]
