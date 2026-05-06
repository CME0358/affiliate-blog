# hair-transplant-lp.html 引き継ぎメモ

作成日：2026-04-23

---

## このスレッドで実施した作業

### 1. 前スレッドからの引き継ぎ状態

前スレッド完成時点のファイル：`public/hair-transplant-lp.html`

#### LP構成（10セクション）

| # | セクション ID | 役割 |
|---|---|---|
| ① | `#fv` | 「まだ大丈夫」への問いかけ＋無料診断CTA |
| ② | `#empathy` | 共感チェックリスト（5項目セルフチェック＋警告文） |
| ③ | `#risk` | 進行ステージ（初期→中期→後期の3段階） |
| ④ | `#solution` | 解決策3択（薬・サロン・植毛の比較） |
| ⑤ | `#how` | 植毛の仕組み（3ポイント） |
| ⑥ | `#faq` | 5問アコーディオンFAQ |
| ⑦ | `#credibility` | 権威性・信頼性セクション |
| ⑧ | `#comparison` | Clinic Guide（クリニック比較カード） |
| ⑨ | `#closing` | クロージングCTA |
| sticky | モバイルCTA | FVを過ぎたら固定表示 |

---

### 2. 本スレッドでの修正内容

#### ① FVデザイン修正（4点）

**ヘッダーロゴ**
- 変更前：テキスト `薄毛・植毛ガイド`（`<span class="header-logo">`）
- 変更後：`<img src="/QOL_logo_transparent.png" alt="QOL media" />` を `.logo` クラスで表示
- 画像パス：`affiliate-blog/public/QOL_logo_transparent.png`（既存ファイル流用）

**fv-eyebrow / fv-stat の枠幅**
- `fv-eyebrow`：すでに `display: inline-block` → 変更不要
- `fv-stat`：`display: inline-block` を追加、テキスト幅に合わせた枠に変更

**FV左カラム**
- `align-items: flex-start` を明示追加（flex縦並びの左寄せを確定）

**PC表示でモバイルFVが重複表示されるバグ修正**
- 原因：CSSカスケード順序の問題（`.fv-mb { display: block; }` が mediaクエリより後に定義されていた）
- 修正：`.fv-mb` のデフォルトを `display: none` に変更
- `@media (max-width: 767px)` 内で `.fv-mb { display: block; }` を追加

---

#### ② アフィリリンク設定（アルモ形成クリニック）

**設定済みクリニック情報**

| 項目 | 内容 |
|---|---|
| 店舗名 | アルモ形成クリニック |
| アフィリURL | `https://px.a8.net/svt/ejp?a8mat=4B1R5O+GF7I0Y+5H8A+5YZ75` |
| バナー画像URL | `https://pub.a8.net/a8v2/A8ImageAction.do?eid=s00000025561&id=202402261733557060` |
| ASP | A8.net |

**反映箇所**

| 箇所 | 内容 |
|---|---|
| Clinic Guide（`#comparison`）クリニックA | 店舗名・バナー画像・アフィリURL設定済み |
| Clinic Guide クリニックB | `style="display:none;"` で非表示（ASP追加時に復活） |
| モーダル Result A | 店舗名・バナー画像・アフィリURL設定済み |
| モーダル Result B | 同上（現状アフィリ1件のため同一URLに接続） |

---

#### ③ メタタイトル変更（Google広告ポリシー対応）

| | タイトル |
|---|---|
| 変更前 | その抜け毛、まだ大丈夫って思ってませんか？｜自毛植毛の無料カウンセリング |
| 変更後 | クリニック選びで後悔しないために｜ヘアケア選びの専門情報サイト |

変更理由：「抜け毛」「薄毛」「植毛」「まだ大丈夫？」がGoogle広告ポリシーに抵触し審査落ちを繰り返していたため、医療ワード・不安煽り表現を排除。

---

### 3. トラッキング設定（前スレッドから継続）

| 項目 | 値 |
|---|---|
| GA4 | `G-BS30YQY1N7`（pet-lp・sleep-lpと共通） |
| Clarity | `w6fgeud38o`（pet-lp・sleep-lpと共通） |
| CTA色 | `#06C755` |

#### GA4イベント設定済み

| イベント名 | 発火タイミング |
|---|---|
| `modal_open` | モーダルを開いた時 |
| `modal_step2` | Step2選択時（`event_label` で consult/info 区別） |
| `modal_result` | 結果表示時（`event_label` で clinic-a/clinic-b 区別） |

---

### 4. 現在のファイル状態

| 項目 | 状態 |
|---|---|
| `public/hair-transplant-lp.html` | 上記全変更適用済み |
| GA4 `G-BS30YQY1N7` | ✅ |
| Clarity `w6fgeud38o` | ✅ |
| CTA色 `#06C755` | ✅ |
| ヘッダーロゴ `QOL_logo_transparent.png` | ✅ |
| アルモ形成クリニック リンク設定 | ✅ |
| モーダル Result 画像 | ✅ |
| メタタイトル（広告ポリシー対応） | ✅ |
| クリニックB 非表示 | ✅ |

---

### 5. 残タスク

- [ ] **クリニックBの情報追加**（ASP審査通過後）
  - `style="display:none;"` を削除して復活
  - 店舗名・アフィリURL・バナー画像・説明文を記入
  - モーダル Result B のURLも個別URLに更新

- [ ] **FV統計数値の差し替え**（ASPまたはクリニック公開データがあれば）

- [ ] **Googleインデックス登録**（`indexing-submit.js` で投入）

- [ ] **Google広告の審査再申請**（メタタイトル変更後）

- [ ] **モーダルのclickイベントGA4計測**（任意・pet-lpと同仕様で追加可能）


[[QOLmedia_引き継ぎメモ_20260409]]
[[QOLmedia_引き継ぎメモ_20260411]]
[[QOLmedia_引き継ぎメモ_20260411_夜]]
[[QOLmedia_引き継ぎメモ_20260418]]
[[QOLmedia_引き継ぎメモ_20260419]]
[[pet-lp_引き継ぎメモ_20260421]]
[[hair-transplant-lp_引き継ぎメモ_20260422]]
