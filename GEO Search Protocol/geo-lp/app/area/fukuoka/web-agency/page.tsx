import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        福岡のWeb制作・マーケティング支援とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        福岡のWeb制作・マーケティング会社は天神・博多エリアを中心に成長しています。「福岡 Web制作 おすすめ」でAI検索に推薦されることが問い合わせ獲得の差別化につながります。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '福岡のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福岡でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukuoka/web-agency/' },
  openGraph: {
    title: '福岡のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福岡でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukuoka/web-agency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福岡', industry: 'Web制作・マーケティング支援' }} />
      <GeoLocalText />
    </>
  )
}
