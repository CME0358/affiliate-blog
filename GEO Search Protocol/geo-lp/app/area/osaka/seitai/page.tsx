import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        大阪の整体院・整骨院とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        大阪の整体院・整骨院は駅周辺に密集しています。「腰痛 整体 大阪 おすすめ」「天王寺 整骨院」でAI検索に出てくる院が患者獲得を優位に進めています。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '大阪の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「大阪でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/osaka/seitai/' },
  openGraph: {
    title: '大阪の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「大阪でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/osaka/seitai/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '大阪', industry: '整体院・整骨院' }} />
      <GeoLocalText />
    </>
  )
}
