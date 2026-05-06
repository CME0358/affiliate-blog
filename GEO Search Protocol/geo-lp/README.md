# GEO Search Protocol — LP

## ローカル確認

```bash
npm install
npm run dev
# → http://localhost:3000
```

## Vercelデプロイ手順

### 方法①：GitHub経由（推奨）

1. このフォルダをGitHubにpush
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_ACCOUNT/geo-lp.git
git push -u origin main
```

2. [vercel.com](https://vercel.com) でGitHubリポジトリをimport
3. Frameworkは「Next.js」を選択（自動検出されます）
4. Deploy → 完了

### 方法②：Vercel CLI

```bash
npm i -g vercel
vercel login
vercel --prod
```

## ドメイン設定

Vercelダッシュボード → Settings → Domains
→ `lp.coaretail.com` を追加

DNSにCNAMEレコードを追加：
```
cname: lp → cname.vercel-dns.com
```

## パフォーマンス目標
- LCP: 2.5秒以下（モバイル）
- FCP: 1.8秒以下
- Score: 90+（モバイル）

## CVポイント
- CTAボタン（全7箇所）→ フォームモーダル
- フォーム送信後：サンクスページ表示
- 実際の申込先はformspreeやGoogleフォームへの差し替えも可
