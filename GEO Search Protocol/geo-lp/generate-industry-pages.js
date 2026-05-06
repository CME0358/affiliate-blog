#!/usr/bin/env node
// generate-industry-pages.js
// 使い方: node generate-industry-pages.js
// 実行場所: ~/Downloads/geo-lp/ のルートで実行

const fs = require('fs')
const path = require('path')

const INDUSTRIES = [
  { slug: 'beauty-clinic',  name: '美容クリニック' },
  { slug: 'restaurant',     name: '飲食店' },
  { slug: 'hr',             name: '求人・採用' },
  { slug: 'accountant',     name: '税理士・会計士' },
  { slug: 'dental',         name: '歯科クリニック' },
  { slug: 'gym',            name: 'パーソナルジム' },
  { slug: 'esthetic',       name: 'エステサロン' },
  { slug: 'hair-salon',     name: '美容院・ヘアサロン' },
  { slug: 'nail-salon',     name: 'ネイルサロン' },
  { slug: 'hair-removal',   name: '医療脱毛・エステ脱毛' },
  { slug: 'aga',            name: 'AGA・薄毛治療' },
  { slug: 'seitai',         name: '整体院・整骨院' },
  { slug: 'realestate',     name: '不動産売却・査定' },
  { slug: 'housing',        name: '注文住宅・ハウスメーカー' },
  { slug: 'reform',         name: 'リフォーム・リノベーション' },
  { slug: 'career',         name: '転職エージェント' },
  { slug: 'programming',    name: 'プログラミングスクール' },
  { slug: 'lawyer-general', name: '弁護士事務所' },
  { slug: 'emergency',      name: '水道修理・鍵開け緊急サービス' },
  { slug: 'ceremony',       name: '結婚式場・葬儀社' },
  { slug: 'car-buy',        name: '中古車買取' },
  { slug: 'saas',           name: 'BtoB SaaS・業務システム' },
  { slug: 'web-agency',     name: 'Web制作・マーケティング支援' },
  { slug: 'meo',            name: 'MEO対策' },
  { slug: 'seo',            name: 'SEO対策' },
  { slug: 'lawyer',         name: '司法書士・社労士・行政書士' },
  { slug: 'shindan',        name: 'AI検索診断' },
  { slug: 'dermatology',    name: '皮膚科・アトピークリニック' },
  { slug: 'psychiatry',     name: '心療内科・精神科クリニック' },
  { slug: 'orthopedics',    name: '整形外科・スポーツ整体' },
  { slug: 'fertility',      name: '不妊治療クリニック' },
  { slug: 'diet-clinic',    name: 'ダイエット外来・肥満外科' },
  { slug: 'eyeclinic',      name: '眼科・レーシック・ICL' },
  { slug: 'childcare',      name: '学習塾・個別指導塾' },
  { slug: 'cram-school',    name: '予備校・大学受験対策' },
  { slug: 'online-school',  name: 'オンライン英会話・語学スクール' },
  { slug: 'nursery',        name: '保育園・託児所' },
  { slug: 'pet-hotel',      name: 'ペットホテル・トリミング' },
  { slug: 'pet-clinic',     name: '動物病院・ペットクリニック' },
  { slug: 'funeral',        name: '葬儀・斎場' },
  { slug: 'inheritance',    name: '遺品整理・相続手続き代行' },
  { slug: 'insurance',      name: '保険代理店・FP相談' },
  { slug: 'car-lease',      name: 'カーリース・車販売' },
  { slug: 'used-car-buy',   name: '中古車販売' },
  { slug: 'moving',         name: '引越し業者・単身引越し' },
  { slug: 'storage',        name: 'トランクルーム・収納サービス' },
  { slug: 'cleaning',       name: 'ハウスクリーニング・エアコン清掃' },
  { slug: 'pest-control',   name: '害虫駆除・シロアリ対策' },
  { slug: 'interior',       name: 'インテリアコーディネート・家具' },
  { slug: 'meal-kit',       name: '食材宅配・ミールキット' },
  { slug: 'temp-agency',    name: '人材派遣・スタッフィング' },
  { slug: 'divorce-law',    name: '離婚専門弁護士・調停サポート' },
]

const BASE_URL = 'https://aiscan.coaretail.com'
const APP_DIR = path.join(__dirname, 'app')

function generatePageContent(slug, name) {
  const title = name + 'の集客、AIに任せてますか？｜GEO無料診断'
  const description = 'ChatGPT・Geminiで「おすすめの' + name + 'は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。'
  const canonical = BASE_URL + '/' + slug + '/'
  const lines = [
    "import { cookies } from 'next/headers'",
    "import type { Metadata } from 'next'",
    "import AiscanLP from '@/components/AiscanLP'",
    "import AiscanLP_B from '@/components/AiscanLP_B'",
    "",
    "export const metadata: Metadata = {",
    "  title: '" + title + "',",
    "  description: '" + description + "',",
    "  alternates: { canonical: '" + canonical + "' },",
    "  openGraph: {",
    "    title: '" + title + "',",
    "    description: '" + description + "',",
    "    url: '" + canonical + "',",
    "  },",
    "}",
    "",
    "export default async function Page() {",
    "  const cookieStore = await cookies()",
    "  const variant = cookieStore.get('geo_ab_variant')?.value ?? 'A'",
    "",
    "  return variant === 'B'",
    "    ? <AiscanLP_B headline={{ industry: '" + name + "' }} />",
    "    : <AiscanLP   headline={{ industry: '" + name + "' }} />",
    "}",
    "",
  ]
  return lines.join('\n')
}

let count = 0
for (const ind of INDUSTRIES) {
  const dirPath = path.join(APP_DIR, ind.slug)
  const filePath = path.join(dirPath, 'page.tsx')
  fs.mkdirSync(dirPath, { recursive: true })
  const content = generatePageContent(ind.slug, ind.name)
  fs.writeFileSync(filePath, content, 'utf8')
  count++
  console.log('✅ ' + ind.slug + '/page.tsx')
}

console.log('\n🎉 完了: ' + count + 'ページ生成')
console.log('📁 app/{slug}/page.tsx を ' + count + '件生成しました')
