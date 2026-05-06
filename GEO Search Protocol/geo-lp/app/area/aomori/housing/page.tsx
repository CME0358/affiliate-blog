import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '青森の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「青森でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/aomori/housing/' },
  openGraph: {
    title: '青森の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「青森でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/aomori/housing/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '青森', industry: '注文住宅・ハウスメーカー' }} />
      
    </>
  )
}
