# QOL media LP 引き継ぎメモ

作成日：2026-04-27

---

## LP一覧・ファイル名

| LP | ファイル名 | URL |
|---|---|---|
| 睡眠 | `public/sleep-guide.html` | https://www.qolmedia.info/sleep-guide.html |
| ペット医薬品 | `public/pet-lp.html` | https://www.qolmedia.info/pet-lp.html |
| ファクタリング | `public/factoring-lp.html` | https://www.qolmedia.info/factoring-lp.html |
| ヘアケア・植毛 | `public/hc-guide.html` | https://www.qolmedia.info/hc-guide.html |

※ヘアケアLPは `hair-transplant-lp.html` → `hc-guide.html` にリネーム済み（Google広告ポリシー対応）
※睡眠LPは `sleep-lp.html` → `sleep-guide.html` にリネーム済み（同上）

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

## 本スレッドの作業内容

### sleep-guide
- モーダルリザルト3商品をブレインスリープ3製品に差し替え（A8.net）
- サプリコピー薬機法対応「このサプリが効く」→「このサプリ」
- マットレスコピー「体圧分散〜」→「脳も体も究極の睡眠を」
- GA4イベント追加（modal_open / modal_worry_select / cta_click）
- CTAコピー変更（「探す」→「どれに当てはまる？」）
- pulse・トースト・スクロール50%自動起動追加
- Step1 worry-btnを緑枠・矢印・active付きに強化
- Step2 solution-card-btnをサイズ拡大・「公式サイトで確認する」に変更
- **未解決：本番ファイルの `[e.target](http://e.target)` 破損問題**

### pet-lp
- GA4イベント追加（modal_open / modal_pet_select / modal_med_select / cta_click）
- CTAコピー変更（「お薬を探す」→「犬・猫どちらですか？」）
- pulse・トースト・スクロール50%自動起動追加
- Step1 worry-btnを緑枠・矢印・active付きに強化
- タップ誘導テキスト追加

### factoring-lp
- GA4イベント追加（diag_select / cta_click）
- 月末カウントダウンバナー追加（25日以降・header上部・最上面）
- バナーフォント17px・「今月も残りあと○日」テキスト
- 相見積もり注記を赤色点滅に変更（font-size 0.9em）
- 診断ボックスを白背景カードに変更・ボタン縦並び化
- pulse・トースト追加
- 結果カードに白背景追加（hero背景への埋没解消）

### hc-guide
- ファイル名リネーム（`hair-transplant-lp.html` → `hc-guide.html`）
- メタdescription薬機法・広告ポリシー対応リライト
- GA4イベント追加（modal_open / cta_click）
- Step1 modal-choiceを緑枠・矢印・active付きに強化
- タップ誘導テキスト追加
- pulse・トースト・スクロール50%自動起動追加

### robots.txt
- `src/app/robots.ts` を新規作成（Sitemap明示・Googlebot対応）
- Search Consoleのサイトマップ「取得できませんでした」問題の対処

---

## 未解決の問題

### 🔴 sleep-guide: `e.target` 破損問題（最重要）

**症状：** 本番ファイルの1256行目に `[e.target](http://e.target)` という壊れた文字列が存在し、モーダルのclose処理でJSエラーが発生。`modal_open` イベントが一切発火しない。

**確認コマンド：**
```bash
curl -s https://www.qolmedia.info/sleep-guide.html | grep -n "e.target"
```

**修正方法：**
ローカルファイルの該当行を手動でテキストエディタ（VSCode等）で開き、
```
[e.target](http://e.target)
```
を
```
e.target
```
に直接書き換えてpushする。sedやPythonでの置換が効かないため、エディタでの手動修正が確実。

```bash
# 修正後
cd ~/Downloads/affiliate-blog
git add public/sleep-guide.html
git commit -m "fix: sleep-guide e.target破損修正（モーダル不具合解消）"
git push
```

---

## Google広告の状況

| LP | キャンペーン | ステータス |
|---|---|---|
| hc-guide | [hair]GDN_10円設定_LP誘導 | 有効（制限付き）※審査中 |
| sleep-guide | [SLEEP]GDN_10円設定_LP誘導 | 有効（制限付き）|
| factoring-lp | [factoring]GDN | 運用中 |

**広告ポリシー違反（健康・パーソナライズド広告）について：**
- 説明文・見出しのリライト済み
- URLリネームで対応済み（hair/sleep → hc/sleep-guide）
- LP内コンテンツのクロール判定が残る可能性あり → 審査結果待ち

---

## sitemap・SEO状況

- `https://www.qolmedia.info/sitemap.xml` → 正常（117件・記事URLあり）
- Search Consoleのサイトマップ「取得できませんでした」→ 技術的問題なし・処理待ち
- インデックス登録済み：14ページ
- `robots.ts` 追加でSitemap明示済み


[[QOLmedia_引き継ぎメモ_20260409]]
[[QOLmedia_引き継ぎメモ_20260411]]
[[QOLmedia_引き継ぎメモ_20260411_夜]]
[[QOLmedia_引き継ぎメモ_20260418]]
[[QOLmedia_引き継ぎメモ_20260419]]
[[pet-lp_引き継ぎメモ_20260421]]
[[hair-transplant-lp_引き継ぎメモ_20260422]]
[[hair-transplant-lp_引き継ぎメモ_20260423]]
