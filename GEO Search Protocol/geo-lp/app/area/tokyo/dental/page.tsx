import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        東京の歯科クリニックとGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        東京の歯科医院は激戦区です。「痛くない歯医者 新宿」「丁寧な歯科 東京」といった検索クエリでAIに推薦されるかどうかが、新患獲得の分岐点になっています。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '東京の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「東京でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/dental/' },
  openGraph: {
    title: '東京の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「東京でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/dental/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '東京', industry: '歯科クリニック' }} />
      <GeoLocalText />
    </>
  )
}
