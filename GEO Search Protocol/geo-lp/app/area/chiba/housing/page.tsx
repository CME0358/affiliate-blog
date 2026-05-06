import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '千葉の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「千葉でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/chiba/housing/' },
  openGraph: {
    title: '千葉の注文住宅・ハウスメーカー、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「千葉でおすすめのハウスメーカーは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/chiba/housing/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '千葉', industry: '注文住宅・ハウスメーカー' }} />
      
    </>
  )
}
