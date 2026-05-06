#!/usr/bin/env node
// generate-pages.js
// 使い方: node generate-pages.js
// 実行場所: ~/Downloads/geo-lp/ のルートで実行

const fs = require('fs')
const path = require('path')

// ── 都道府県 ──────────────────────────────────────────
const PREFECTURES = [
  { slug: 'hokkaido',   name: '北海道' },
  { slug: 'aomori',     name: '青森' },
  { slug: 'iwate',      name: '岩手' },
  { slug: 'miyagi',     name: '宮城' },
  { slug: 'akita',      name: '秋田' },
  { slug: 'yamagata',   name: '山形' },
  { slug: 'fukushima',  name: '福島' },
  { slug: 'ibaraki',    name: '茨城' },
  { slug: 'tochigi',    name: '栃木' },
  { slug: 'gunma',      name: '群馬' },
  { slug: 'saitama',    name: '埼玉' },
  { slug: 'chiba',      name: '千葉' },
  { slug: 'tokyo',      name: '東京' },
  { slug: 'kanagawa',   name: '神奈川' },
  { slug: 'niigata',    name: '新潟' },
  { slug: 'toyama',     name: '富山' },
  { slug: 'ishikawa',   name: '石川' },
  { slug: 'fukui',      name: '福井' },
  { slug: 'yamanashi',  name: '山梨' },
  { slug: 'nagano',     name: '長野' },
  { slug: 'shizuoka',   name: '静岡' },
  { slug: 'gifu',       name: '岐阜' },
  { slug: 'aichi',      name: '愛知' },
  { slug: 'mie',        name: '三重' },
  { slug: 'shiga',      name: '滋賀' },
  { slug: 'kyoto',      name: '京都' },
  { slug: 'osaka',      name: '大阪' },
  { slug: 'hyogo',      name: '兵庫' },
  { slug: 'nara',       name: '奈良' },
  { slug: 'wakayama',   name: '和歌山' },
  { slug: 'tottori',    name: '鳥取' },
  { slug: 'shimane',    name: '島根' },
  { slug: 'okayama',    name: '岡山' },
  { slug: 'hiroshima',  name: '広島' },
  { slug: 'yamaguchi',  name: '山口' },
  { slug: 'tokushima',  name: '徳島' },
  { slug: 'kagawa',     name: '香川' },
  { slug: 'ehime',      name: '愛媛' },
  { slug: 'kochi',      name: '高知' },
  { slug: 'fukuoka',    name: '福岡' },
  { slug: 'saga',       name: '佐賀' },
  { slug: 'nagasaki',   name: '長崎' },
  { slug: 'kumamoto',   name: '熊本' },
  { slug: 'oita',       name: '大分' },
  { slug: 'miyazaki',   name: '宮崎' },
  { slug: 'kagoshima',  name: '鹿児島' },
  { slug: 'okinawa',    name: '沖縄' },
]

// ── 業種 ──────────────────────────────────────────────
const INDUSTRIES = [
  { slug: 'beauty-clinic',  name: '美容クリニック',           query: 'おすすめの美容クリニックは？' },
  { slug: 'restaurant',     name: '飲食店',                   query: 'おすすめの飲食店は？' },
  { slug: 'hr',             name: '採用支援企業',           query: 'おすすめの求人・転職先は？' },
  { slug: 'accountant',     name: '税理士・会計士',           query: 'おすすめの税理士は？' },
  { slug: 'dental',         name: '歯科クリニック',           query: 'おすすめの歯科クリニックは？' },
  { slug: 'gym',            name: 'パーソナルジム',           query: 'おすすめのパーソナルジムは？' },
  { slug: 'esthetic',       name: 'エステサロン',             query: 'おすすめのエステサロンは？' },
  { slug: 'hair-salon',     name: '美容院・ヘアサロン',       query: 'おすすめの美容院は？' },
  { slug: 'nail-salon',     name: 'ネイルサロン',             query: 'おすすめのネイルサロンは？' },
  { slug: 'hair-removal',   name: '医療脱毛・エステ脱毛',     query: 'おすすめの医療脱毛は？' },
  { slug: 'aga',            name: 'AGA・薄毛治療',            query: 'おすすめのAGAクリニックは？' },
  { slug: 'seitai',         name: '整体院・整骨院',           query: 'おすすめの整体院は？' },
  { slug: 'realestate',     name: '不動産会社',         query: '不動産売却のおすすめ会社は？' },
  { slug: 'housing',        name: '注文住宅・ハウスメーカー', query: 'おすすめのハウスメーカーは？' },
  { slug: 'reform',         name: 'リフォーム・リノベーション', query: 'おすすめのリフォーム会社は？' },
  { slug: 'career',         name: '転職エージェント',         query: 'おすすめの転職エージェントは？' },
  { slug: 'programming',    name: 'プログラミングスクール',   query: 'おすすめのプログラミングスクールは？' },
  { slug: 'lawyer-general', name: '弁護士事務所',             query: 'おすすめの弁護士は？' },
  { slug: 'emergency',      name: '緊急修理業者', query: '近くの水道修理業者は？' },
  { slug: 'ceremony',       name: '結婚式場・葬儀社',         query: 'おすすめの結婚式場・葬儀社は？' },
  { slug: 'car-buy',        name: '中古車買取',               query: 'おすすめの中古車買取は？' },
  { slug: 'saas',           name: 'SaaS取扱企業',  query: 'おすすめのMAツール・CRMは？' },
  { slug: 'web-agency',     name: 'Web制作・マーケティング支援', query: 'おすすめのWeb制作会社は？' },
  { slug: 'meo',            name: 'MEO対策会社',                  query: 'おすすめのMEO対策会社は？' },
  { slug: 'seo',            name: 'SEO対策会社',                  query: 'おすすめのSEO対策会社は？' },
  { slug: 'lawyer',         name: '司法書士・社労士・行政書士', query: 'おすすめの士業事務所は？' },
  { slug: 'shindan',        name: '__none__',                       query: 'AI検索対策の無料診断は？' },
  { slug: 'dermatology',    name: '皮膚科・アトピークリニック',       query: 'おすすめの皮膚科・アトピークリニックは？' },
  { slug: 'psychiatry',     name: '心療内科・精神科クリニック',       query: 'おすすめの心療内科・精神科は？' },
  { slug: 'orthopedics',    name: '整形外科・スポーツ整体',           query: 'おすすめの整形外科・スポーツ整体は？' },
  { slug: 'fertility',      name: '不妊治療クリニック',               query: 'おすすめの不妊治療クリニックは？' },
  { slug: 'diet-clinic',    name: 'ダイエット外来・肥満外科',         query: 'おすすめのダイエット外来は？' },
  { slug: 'eyeclinic',      name: '眼科・レーシック・ICL',            query: 'おすすめの眼科・レーシッククリニックは？' },
  { slug: 'childcare',      name: '学習塾・個別指導塾',               query: 'おすすめの学習塾・個別指導塾は？' },
  { slug: 'cram-school',    name: '予備校・大学受験対策',             query: 'おすすめの予備校・大学受験塾は？' },
  { slug: 'online-school',  name: 'オンライン英会話・語学スクール',   query: 'おすすめのオンライン英会話・語学スクールは？' },
  { slug: 'nursery',        name: '保育園・託児所',                   query: 'おすすめの保育園・託児所は？' },
  { slug: 'pet-hotel',      name: 'ペットホテル・トリミング',         query: 'おすすめのペットホテル・トリミングサロンは？' },
  { slug: 'pet-clinic',     name: '動物病院・ペットクリニック',       query: 'おすすめの動物病院・ペットクリニックは？' },
  { slug: 'funeral',        name: '葬儀・斎場',                       query: 'おすすめの葬儀社・斎場は？' },
  { slug: 'inheritance',    name: '遺品整理・相続手続き代行',         query: 'おすすめの遺品整理・相続手続き代行は？' },
  { slug: 'insurance',      name: '保険代理店・FP相談',               query: 'おすすめの保険代理店・FP相談は？' },
  { slug: 'car-lease',      name: 'カーリース・車販売',               query: 'おすすめのカーリース・車販売は？' },
  { slug: 'used-car-buy',   name: '中古車販売',                       query: 'おすすめの中古車販売店は？' },
  { slug: 'moving',         name: '引越し業者・単身引越し',           query: 'おすすめの引越し業者は？' },
  { slug: 'storage',        name: 'トランクルーム・収納サービス',     query: 'おすすめのトランクルーム・収納サービスは？' },
  { slug: 'cleaning',       name: 'ハウスクリーニング・エアコン清掃', query: 'おすすめのハウスクリーニング業者は？' },
  { slug: 'pest-control',   name: '害虫駆除・シロアリ対策',           query: 'おすすめの害虫駆除・シロアリ対策業者は？' },
  { slug: 'interior',       name: 'インテリアコーディネート・家具',   query: 'おすすめのインテリアコーディネーターは？' },
  { slug: 'meal-kit',       name: '食材宅配・ミールキット',           query: 'おすすめの食材宅配・ミールキットは？' },
  { slug: 'temp-agency',    name: '人材派遣・スタッフィング',         query: 'おすすめの人材派遣会社は？' },
  { slug: 'divorce-law',    name: '離婚専門弁護士・調停サポート',     query: 'おすすめの離婚専門弁護士は？' },
]

// 重複slug除去
const UNIQUE_INDUSTRIES = INDUSTRIES.filter((v, i, a) => a.findIndex(t => t.slug === v.slug) === i)

const BASE_URL = 'https://aiscan.coaretail.com'
const APP_DIR = path.join(__dirname, 'app')
const SITEMAP_ENTRIES = []

// ── 主要都市×主要業種の独自テキスト ────────────────────
const PRIORITY_PREFS = ['tokyo', 'osaka', 'fukuoka']
const PRIORITY_INDUSTRIES = ['beauty-clinic', 'dental', 'esthetic', 'hair-salon', 'gym', 'seitai', 'restaurant', 'realestate', 'meo', 'web-agency']

const UNIQUE_TEXTS = {
  tokyo: {
    'beauty-clinic': '東京都内には美容クリニックが集中しており、患者はChatGPTやGeminiで「渋谷 美容クリニック おすすめ」と検索して比較します。AI検索に出てこないクリニックは、競合に患者を奪われ続けます。',
    'dental': '東京の歯科医院は激戦区です。「痛くない歯医者 新宿」「丁寧な歯科 東京」といった検索クエリでAIに推薦されるかどうかが、新患獲得の分岐点になっています。',
    'esthetic': '東京のエステサロンは銀座・表参道・新宿エリアに集中しています。ChatGPTで「銀座 エステ おすすめ」と検索した際に名前が出るサロンとそうでないサロンでは、集客力に大きな差が生まれています。',
    'hair-salon': '東京の美容院は全国最多水準です。「青山 ヘアサロン」「表参道 カット 上手い」といった検索でAIに推薦されることが、指名客獲得の鍵を握っています。',
    'gym': '東京のパーソナルジムは都心を中心に急増しています。「恵比寿 パーソナルジム」「渋谷 ダイエット ジム おすすめ」でAI検索に出てこないジムは、潜在顧客を逃し続けています。',
    'seitai': '東京の整体院・整骨院は駅近に多数存在します。「腰痛 整体 東京 おすすめ」「肩こり 整骨院 新宿」でAIに推薦される院と無視される院では、問い合わせ数に大きな差が出ています。',
    'restaurant': '東京の飲食店はミシュランガイド掲載店から町の名店まで多様です。「東京 ランチ おすすめ」「接待 レストラン 銀座」でAIに推薦されることが、予約数増加に直結します。',
    'realestate': '東京の不動産市場は全国最大規模です。「東京 不動産売却 おすすめ」「マンション査定 東京」でAI検索に表示されない不動産会社は、見込み客との接点を失い続けています。',
    'meo': '東京でMEO対策を行う企業にとって、AI検索への対応は次の必須課題です。GEO対策によりChatGPT・Geminiでの推薦表示を獲得することで、MEOと組み合わせた強力な集客基盤を構築できます。',
    'web-agency': '東京のWeb制作・マーケティング支援会社は数千社以上あります。「東京 Web制作 おすすめ」「SEO 会社 東京 比較」でAIに推薦される会社が、問い合わせを独占する時代になっています。',
  },
  osaka: {
    'beauty-clinic': '大阪の美容クリニックは梅田・心斎橋・難波エリアに集中しています。「大阪 美容クリニック おすすめ」でChatGPTやGeminiに推薦されるかどうかが、新規患者獲得の分岐点です。',
    'dental': '大阪の歯科医院は競争が激しく、患者はAI検索で「痛くない歯医者 梅田」「子供 歯科 大阪 おすすめ」と比較します。AI検索での推薦獲得が集客の鍵です。',
    'esthetic': '大阪のエステサロンは心斎橋・難波・梅田エリアに集まっています。ChatGPTで「大阪 エステ おすすめ」と検索した際に出てくるサロンとそうでないサロンでは集客力が大きく異なります。',
    'hair-salon': '大阪の美容院は南北に広がる繁華街に数多く存在します。「心斎橋 美容院」「梅田 ヘアサロン おすすめ」でAI検索に推薦されることが予約数増加につながります。',
    'gym': '大阪のパーソナルジムは梅田・心斎橋周辺を中心に増加しています。「大阪 パーソナルジム おすすめ」でAIに推薦されないジムは、新規会員獲得の機会を失っています。',
    'seitai': '大阪の整体院・整骨院は駅周辺に密集しています。「腰痛 整体 大阪 おすすめ」「天王寺 整骨院」でAI検索に出てくる院が患者獲得を優位に進めています。',
    'restaurant': '大阪は食文化が根付く街です。「大阪 たこ焼き おすすめ」「難波 ランチ 安い うまい」でAI検索に推薦されることが、観光客・地元客双方の集客に直結します。',
    'realestate': '大阪の不動産市場は万博・IR誘致を背景に活況です。「大阪 不動産売却」「マンション査定 梅田 おすすめ」でAIに推薦される会社が見込み客を獲得しています。',
    'meo': '大阪でMEO対策を実施中の企業は、次のステップとしてGEO対策が必須です。ChatGPT・Geminiでの推薦獲得により、AI検索時代の集客基盤を確立できます。',
    'web-agency': '大阪のWeb制作・マーケティング会社は梅田・本町エリアに多く集積しています。「大阪 Web制作 おすすめ」でAIに推薦されることが、問い合わせ獲得の優位性につながります。',
  },
  fukuoka: {
    'beauty-clinic': '福岡の美容クリニックは天神・博多エリアに集中しています。「福岡 美容クリニック おすすめ」でChatGPTやGeminiに推薦されることが、九州全域からの患者獲得につながります。',
    'dental': '福岡の歯科医院は競争が激しく、患者はAI検索で「天神 歯医者 おすすめ」「博多 歯科 丁寧」と比較します。AI検索での推薦獲得が集客力を大きく左右します。',
    'esthetic': '福岡のエステサロンは天神・大名エリアに集まっています。「福岡 エステ おすすめ」でAI検索に出てくるサロンが新規顧客を獲得し、出てこないサロンは埋もれていきます。',
    'hair-salon': '福岡の美容院は天神・薬院エリアを中心に展開しています。「福岡 美容院 おすすめ」「天神 ヘアサロン」でAI推薦を獲得することが予約増加に直結します。',
    'gym': '福岡のパーソナルジムは天神・博多周辺で急増しています。「福岡 パーソナルジム おすすめ」でAIに推薦されないジムは、新規会員獲得競争で後れを取っています。',
    'seitai': '福岡の整体院・整骨院は各駅周辺に多数存在します。「腰痛 整体 福岡 おすすめ」「天神 整骨院」でAI検索に推薦される院が患者獲得を有利に進めています。',
    'restaurant': '福岡はラーメン・もつ鍋・明太子など食の街として知られています。「福岡 ラーメン おすすめ」「博多 もつ鍋 有名店」でAI検索に推薦されることが観光客・地元客の集客に直結します。',
    'realestate': '福岡の不動産市場は人口増加を背景に活況が続いています。「福岡 不動産売却 おすすめ」「マンション査定 天神」でAI検索に表示されることが見込み客獲得の鍵です。',
    'meo': '福岡でMEO対策を実施している企業は、GEO対策により九州全域のAI検索での露出を強化できます。ChatGPT・Geminiでの推薦獲得が次の集客課題です。',
    'web-agency': '福岡のWeb制作・マーケティング会社は天神・博多エリアを中心に成長しています。「福岡 Web制作 おすすめ」でAI検索に推薦されることが問い合わせ獲得の差別化につながります。',
  },
}

let count = 0

for (const pref of PREFECTURES) {
  for (const ind of UNIQUE_INDUSTRIES) {
    const dirPath = path.join(APP_DIR, 'area', pref.slug, ind.slug)
    const filePath = path.join(dirPath, 'page.tsx')
    const url = `${BASE_URL}/area/${pref.slug}/${ind.slug}`

    const title = `${pref.name}の${ind.name}、AIに無視されていませんか？｜GEO無料診断`
    const description = `ChatGPT・Geminiで「${pref.name}で${ind.query}」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。`

    const isPriority = PRIORITY_PREFS.includes(pref.slug) && PRIORITY_INDUSTRIES.includes(ind.slug)
    const uniqueText = isPriority && UNIQUE_TEXTS[pref.slug]?.[ind.slug]
      ? UNIQUE_TEXTS[pref.slug][ind.slug]
      : ''

    const uniqueBlock = uniqueText ? `
const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        ${pref.name}の${ind.name}とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        ${uniqueText}
      </p>
    </div>
  </section>
)
` : ''

    const importBlock = uniqueText
      ? `import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'`
      : `import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'`

    const content = `${importBlock}
${uniqueBlock}
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
  return (
    <>
      <AiscanLP headline={{ area: '${pref.name}', industry: '${ind.name}' }} />
      ${uniqueText ? '<GeoLocalText />' : ''}
    </>
  )
}
`

    fs.mkdirSync(dirPath, { recursive: true })
    fs.writeFileSync(filePath, content, 'utf8')

    SITEMAP_ENTRIES.push({
      url,
      changeFrequency: 'weekly',
      priority: 0.7,
    })

    count++
    if (count % 100 === 0) console.log(`✅ ${count}ページ生成済み...`)
  }
}


console.log(`\n🎉 完了: ${count}ページ生成`)
console.log(`📁 app/area/ 以下に ${PREFECTURES.length}都道府県 × ${UNIQUE_INDUSTRIES.length}業種 = ${count}ページ`)
console.log('※ sitemap.tsは別管理のため自動更新しません')
