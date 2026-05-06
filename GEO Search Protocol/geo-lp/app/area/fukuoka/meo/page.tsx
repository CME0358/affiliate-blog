import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        福岡のMEO対策会社とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        福岡でMEO対策を実施している企業は、GEO対策により九州全域のAI検索での露出を強化できます。ChatGPT・Geminiでの推薦獲得が次の集客課題です。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '福岡のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福岡でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukuoka/meo/' },
  openGraph: {
    title: '福岡のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福岡でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukuoka/meo/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福岡', industry: 'MEO対策会社' }} />
      <GeoLocalText />
    </>
  )
}
