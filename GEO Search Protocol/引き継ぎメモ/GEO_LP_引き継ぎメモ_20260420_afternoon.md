# GEO LP 引き継ぎメモ（2026年4月20日 午後セッション）

---

## 本日（午後）行った主な作業

### A案（AiscanLP.tsx）

1. **フォント全体 +4px**
   - 固定値・clamp値すべてPythonで一括処理

2. **S2.5 DOES THIS SOUND FAMILIAR? セクション**
   - B案と同一構造に変更
   - 背景：`fv-bg.webp` + `rgba(0,0,0,0.78)` オーバーレイ
   - カード：`rgba(255,255,255,0.1)` 半透明白
   - h2：`whiteSpace: 'nowrap'` で一列固定・白文字
   - 締めコピー：「今すぐ診断することをおすすめします。」（A案はそのまま）

---

### B案（AiscanLP_B.tsx）

1. **REALITY CHECK セクション（S2）2カラム化**
   - 左：質問カード5枚（税理士・美容室・外壁塗装・美容クリニック・社労士）
   - 右：`/public/chatgpt-reality.png`（透過PNG・背景同色で馴染む）
   - `gridTemplateColumns: repeat(auto-fit, minmax(280px, 1fr))`でSP自動1カラム

2. **FVバナー画像**
   - SP：`width: 100%`
   - PC（640px〜）：`width: 80%`（max-width: 800px）
   - バナー上マージン：`padding-top: 44px`

3. **FV説明会情報エリア**
   - 日時フォント SP：20px / PC：28px
   - 参加費無料：SP＝テキスト（金色）/ PC＝バッジ画像（free-badge.webp）

4. **FVコピー B案に変更**
   - リード（デフォルト）：`ChatGPTに「おすすめ」を聞いた瞬間、`
   - H1：`競合だけが、選ばれています。`
   - サブ：`あなたが知らない間に、AIは答えを出し終えています。`
   - エリア×業種パターン：`「{エリア}」で「おすすめの{業種}」を聞いた瞬間、`

5. **CTAボタン**
   - `【診断結果を受け取る】` 削除
   - `maxWidth: 480` で横幅制限

6. **S2.5 DOES THIS SOUND FAMILIAR? セクション**
   - 背景：`fv-bg.webp` + `rgba(0,0,0,0.78)` オーバーレイ
   - h2：`whiteSpace: 'nowrap'` 一列固定・白文字
   - 締めコピー：「今すぐ**勉強会に参加**することをおすすめします。」

7. **HOW IT WORKS（S2.7）・DIAGNOSIS PREVIEW（S3）削除**
   - 説明会フロー移行のため不要と判断

8. **S7 FINAL CTAセクション**
   - 旧グラデーション背景を廃止
   - FV黒セクション（バナー画像＋説明会情報＋CTA）を丸ごと移植

9. **YOUR CHOICE セクション**
   - 道②から「診断は完全無料・2営業日以内にお届け」を削除

10. **フォーム（FormModal）説明会用にリライト**
    - ヘッダー：「AI表示診断」→「無料オンライン説明会」
    - サブ：「無料・2営業日以内にお届け」→「参加費無料・Zoom開催」
    - 冒頭ボット：「無料AI表示診断のお申し込みです」→「無料オンライン説明会へのお申し込みです」
    - emailステップ：「診断レポートをお送りします」→「説明会の参加案内をお送りします」
    - 完了メッセージ：「2営業日以内に診断レポートを」→「説明会の参加案内を」

---

## ファイル修正ルール（再確認）

- **A案（AiscanLP.tsx）のベース**：直前にoutputしたファイルを使用
- **B案（AiscanLP_B.tsx）のベース**：アップロードされたファイルを使用
- 修正依頼時は必ず両案のファイルをアップロードまたは最新outputを参照すること

---

## 保留事項（継続）

- seminar-banner-b.webp・free-badge.webp の画像用意→push（差し替え待ち）
- chatgpt-reality.png のpush（IMG_2396.PNGをリネーム）
- B案フォームを説明会申し込み＋日程選択に変更（将来）
- A/B判定 → FVコピー確定（現状CVゼロのためCTAクリック率で判断）
- indexing-submit.js実行（岐阜県・東京23区の新規分・16時以降）
- 無料オンライン説明会の初回録画→以降は録画回し運用
- 全ページへのAI生成独自テキスト追加（Gemini API連携）
- 顔写真・代表メッセージ追加（初回成約後）
- 信頼性セクション追加（導入実績・企業名・お客様の声）

---

## Cookie操作（B案確認方法）

```javascript
// B案に切り替え
document.cookie = "ab_variant=B; path=/; max-age=2592000"
location.reload()

// A案に戻す
document.cookie = "ab_variant=A; path=/; max-age=2592000"
location.reload()
```


[[GEO_LP_引き継ぎメモ_20260401]]
[[GEO_LP_引き継ぎメモ_20260410]]
[[GEO_LP_引き継ぎメモ_20260419b]]
[[GEO_LP_引き継ぎメモ_20260420]]
