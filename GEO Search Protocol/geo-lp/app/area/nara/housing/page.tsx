import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '奈良の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「奈良でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/nara/housing/' },
  openGraph: {
    title: '奈良の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「奈良でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/nara/housing/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '奈良', industry: '注文住宅・ハウスメーカー' }} />
      
    </>
  )
}
