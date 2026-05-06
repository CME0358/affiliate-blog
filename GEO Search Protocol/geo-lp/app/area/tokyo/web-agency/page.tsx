import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        東京のWeb制作・マーケティング支援とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        東京のWeb制作・マーケティング支援会社は数千社以上あります。「東京 Web制作 おすすめ」「SEO 会社 東京 比較」でAIに推薦される会社が、問い合わせを独占する時代になっています。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '東京のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「東京でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/web-agency/' },
  openGraph: {
    title: '東京のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「東京でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/web-agency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '東京', industry: 'Web制作・マーケティング支援' }} />
      <GeoLocalText />
    </>
  )
}
