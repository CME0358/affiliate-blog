# 10_Projects Monorepo

## Vercel デプロイ対象

- `GEO Search Protocol/geo-lp`
- `QOLmedia/affiliate-blog`

Vercel 側では同一リポジトリから、それぞれ別プロジェクトとして作成し、**Root Directory** を上記のパスに設定する。

## 運用メモ

- `node_modules` / `.next` などの生成物はルートの `.gitignore` で除外
- `.env*` や `service-account-key.json` 等の秘密情報はコミットしない（ローカル・Vercel環境変数で管理）

