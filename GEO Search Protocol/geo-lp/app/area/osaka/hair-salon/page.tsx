import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        大阪の美容院・ヘアサロンとGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        大阪の美容院は南北に広がる繁華街に数多く存在します。「心斎橋 美容院」「梅田 ヘアサロン おすすめ」でAI検索に推薦されることが予約数増加につながります。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '大阪の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「大阪でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/osaka/hair-salon/' },
  openGraph: {
    title: '大阪の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「大阪でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/osaka/hair-salon/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '大阪', industry: '美容院・ヘアサロン' }} />
      <GeoLocalText />
    </>
  )
}
