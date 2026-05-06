import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        福岡の歯科クリニックとGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        福岡の歯科医院は競争が激しく、患者はAI検索で「天神 歯医者 おすすめ」「博多 歯科 丁寧」と比較します。AI検索での推薦獲得が集客力を大きく左右します。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '福岡の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福岡でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukuoka/dental/' },
  openGraph: {
    title: '福岡の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福岡でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukuoka/dental/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福岡', industry: '歯科クリニック' }} />
      <GeoLocalText />
    </>
  )
}
