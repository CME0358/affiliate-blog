# QOL media LP 引き継ぎメモ

作成日：2026-04-28

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

---

## GA4イベント一覧

### sleep-guide・pet-lp・hc-guide（モーダル型）

| イベント名 | 発火タイミング |
|---|---|
| `modal_open` | CTAボタンクリック |
| `modal_worry_select` | 悩み選択（sleep） |
| `modal_pet_select` | 犬/猫選択（pet） |
| `modal_med_select` | 薬種選択（pet） |
| `modal_auto_open` | スクロール50%で自動起動 |
| `toast_show` | 15秒後トースト表示 |
| `cta_click` | 商品・クリニックリンククリック |

### factoring-lp（診断型）

| イベント名 | 発火タイミング |
|---|---|
| `diag_select` | 診断回答（fast/low） |
| `diag_auto_show` | スクロール50% |
| `toast_show` | 15秒後トースト表示 |
| `cta_click` | 無料相談ボタンクリック |
| `month_end_banner_show` | 月末バナー表示（25日以降） |

---

## アフィリリンク設定

### sleep-guide（A8.net / ブレインスリープ）

| 商品 | URL |
|---|---|
| ブレインスリープNMN9000（サプリ） | `https://px.a8.net/svt/ejp?a8mat=4AZS0Q+FLFTS2+4KU6+ZRXQP` |
| ブレインスリープピロー（枕） | `https://px.a8.net/svt/ejp?a8mat=4AZS0R+6C130I+4KU6+61Z81` |
| ブレインスリープマットレスフロート | `https://px.a8.net/svt/ejp?a8mat=4AZS0R+6BFNEQ+4KU6+BYLJL` |

### hc-guide（A8.net / アルモ形成クリニック）

| 項目 | 値 |
|---|---|
| アフィリURL | `https://px.a8.net/svt/ejp?a8mat=4B1R5O+GF7I0Y+5H8A+5YZ75` |
| クリニックB | 現在`display:none`（ASP審査通過後に復活） |

---

## 本スレッドの作業内容（2026-04-28）

### sleep-guide
- FVコピー変更（B案採用）
  - H1：`毎晩の眠れない夜を、今夜から変える。` → `寝つけない？夜中に目が覚める？朝、疲れが取れない？`
  - サブ：悩み列挙型 → 「原因タイプで対策が変わる」診断フレームに変更
- FV構成変更：hero-stats（60専門記事・10解決カテゴリ・専門家）を削除し、CTAボタンをh1直下に移動（スクロールせずにFVに収める対策）

### pet-lp
- FVコピー変更（C案採用）
  - H1：`動物病院のお薬代、最大70%安くなります。` → `愛犬・愛猫のお薬、動物病院で買うのが当たり前ですか？`
  - サブ：`正規品・獣医師監修・最大70%節約。同じ成分の薬を、賢く安全に手に入れる方法を徹底解説します。`
- FVにCTAボタン追加（`▶ 愛犬・愛猫どちらですか？`・緑・z-index・グロー付き）
- Step1モーダルタイトル：`どちらのペットですか？` → `どちらのお薬をお探しですか？`
- Step2モーダルタイトル：`何の薬を探していますか？` → `何のお薬をお探しですか？`
- pulse・トースト・スクロール50%自動起動を追加（hc-guide相当に統一）
- トーストテキスト：`🐾 愛犬・愛猫のお薬、30秒で最適なものを見つけませんか？`

### factoring-lp
- カウントダウンバナー縮小：font-size 17px → 15px
- 診断UI（diag-box）コンパクト化：padding・font-sizeを縮小
- hero-stats削除でFV短縮
- カウント計算修正：`lastDay - day` → `lastDay - day + 1`（当日含む）
- バナーテキスト短縮：「⏰ 今月も残りあと○日」のみに変更
- stickyボタン：3択 → 「📋 あなたに合う業者は？」1ボタン・クリックでFV診断へスクロール

### hc-guide
- 変更なし（現状維持）

---

## GA4データ分析メモ（2026-04-28時点）

### sleep-guide（広告キャンペーン：[SLEEP] GDN_10円設定_LP誘導）
- 広告クリック172 / 表示回数3.14万 / 平均CPC ¥8 / 費用 ¥1,433
- GA4：page_view 100、first_visit 86、scroll 5、modal_open 1
- **課題：スクロール率が極端に低い（5%）。CTAがFVに収まっていなかったことが主因 → 本日修正済み**

### pet-lp
- modal_open 1件確認（step1での離脱が疑われたが母数不足で判断保留）
- FVにCTAボタンがなかったことが主因 → 本日追加済み

---

## HTML修正ルール（重要）

- 修正作業時は**必ず直近で作成したHTMLを参照**する。旧バージョンを読み込まない。
- 直近の作成から**6時間以上経過している場合**は、現在使用中のHTMLをアップロードするよう確認を促す。
- ローカルでコードをコピペする際、ターミナルやNotionが `e.target` を `[e.target](http://e.target)` に自動変換することがある。**コマンドはヒアドキュメント形式（`<< 'EOF'`）を使うか、直接手入力すること**。

---

## 未解決の問題

なし（前回の `e.target` 破損問題は解決済み）

---

## Google広告の状況

| LP | キャンペーン | ステータス |
|---|---|---|
| hc-guide | [hair]GDN_10円設定_LP誘導 | 有効（制限付き）※審査中 |
| sleep-guide | [SLEEP]GDN_10円設定_LP誘導 | 有効（制限付き） |
| factoring-lp | [factoring]GDN | 運用中 |

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
