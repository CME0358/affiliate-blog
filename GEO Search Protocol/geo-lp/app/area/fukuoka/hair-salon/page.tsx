import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        福岡の美容院・ヘアサロンとGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        福岡の美容院は天神・薬院エリアを中心に展開しています。「福岡 美容院 おすすめ」「天神 ヘアサロン」でAI推薦を獲得することが予約増加に直結します。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '福岡の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福岡でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukuoka/hair-salon/' },
  openGraph: {
    title: '福岡の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福岡でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukuoka/hair-salon/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福岡', industry: '美容院・ヘアサロン' }} />
      <GeoLocalText />
    </>
  )
}
