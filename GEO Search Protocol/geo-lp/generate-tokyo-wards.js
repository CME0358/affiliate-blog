#!/usr/bin/env node
// generate-tokyo-wards.js
// 使い方: node generate-tokyo-wards.js
// 実行場所: ~/Downloads/geo-lp/ のルートで実行
// 生成URL: /area/tokyo/[区スラッグ] (23件)

const fs = require('fs')
const path = require('path')

const TOKYO_WARDS = [
  { slug: 'chiyoda',    name: '千代田区' },
  { slug: 'chuo',       name: '中央区' },
  { slug: 'minato',     name: '港区' },
  { slug: 'shinjuku',   name: '新宿区' },
  { slug: 'bunkyo',     name: '文京区' },
  { slug: 'taito',      name: '台東区' },
  { slug: 'sumida',     name: '墨田区' },
  { slug: 'koto',       name: '江東区' },
  { slug: 'shinagawa',  name: '品川区' },
  { slug: 'meguro',     name: '目黒区' },
  { slug: 'ota',        name: '大田区' },
  { slug: 'setagaya',   name: '世田谷区' },
  { slug: 'shibuya',    name: '渋谷区' },
  { slug: 'nakano',     name: '中野区' },
  { slug: 'suginami',   name: '杉並区' },
  { slug: 'toshima',    name: '豊島区' },
  { slug: 'kita',       name: '北区' },
  { slug: 'arakawa',    name: '荒川区' },
  { slug: 'itabashi',   name: '板橋区' },
  { slug: 'nerima',     name: '練馬区' },
  { slug: 'adachi',     name: '足立区' },
  { slug: 'katsushika', name: '葛飾区' },
  { slug: 'edogawa',    name: '江戸川区' },
]

const BASE_URL = 'https://aiscan.coaretail.com'
const APP_DIR = path.join(__dirname, 'app')

let count = 0

for (const ward of TOKYO_WARDS) {
  const dirPath = path.join(APP_DIR, 'area', 'tokyo', ward.slug)
  const filePath = path.join(dirPath, 'page.tsx')
  const url = `${BASE_URL}/area/tokyo/${ward.slug}`

  const title = `${ward.name}のGEO対策、AIに無視されていませんか？｜GEO無料診断`
  const description = `ChatGPTやGeminiで「${ward.name} おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。`

  const content = `import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '${title}',
  description: '${description}',
  alternates: { canonical: '${url}/' },
  openGraph: {
    title: '${title}',
    description: '${description}',
    url: '${url}/',
  },
}

export default function Page() {
  return <AiscanLP headline={{ area: '${ward.name}', industry: '表示' }} />
}
`

  fs.mkdirSync(dirPath, { recursive: true })
  fs.writeFileSync(filePath, content, 'utf8')
  console.log(`✅ ${ward.name}: ${url}`)
  count++
}

console.log(`\n🎉 完了: ${count}ページ生成`)
console.log('※ sitemap.tsは手動で追加してください')
