import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

const GeoLocalText = () => (
  <section style={{ padding: '48px 24px', background: '#F7F5F2' }}>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <p style={{ fontSize: 14, fontWeight: 700, color: '#A0006E', marginBottom: 12, letterSpacing: '0.08em' }}>
        東京の整体院・整骨院とGEO対策
      </p>
      <p style={{ fontSize: 16, lineHeight: 1.9, color: '#1A1A2E' }}>
        東京の整体院・整骨院は駅近に多数存在します。「腰痛 整体 東京 おすすめ」「肩こり 整骨院 新宿」でAIに推薦される院と無視される院では、問い合わせ数に大きな差が出ています。
      </p>
    </div>
  </section>
)

export const metadata: Metadata = {
  title: '東京の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「東京でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/seitai/' },
  openGraph: {
    title: '東京の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「東京でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/seitai/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '東京', industry: '整体院・整骨院' }} />
      <GeoLocalText />
    </>
  )
}
