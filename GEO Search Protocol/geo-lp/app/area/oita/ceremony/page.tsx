import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '大分の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「大分でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/oita/ceremony/' },
  openGraph: {
    title: '大分の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「大分でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/oita/ceremony/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '大分', industry: '結婚式場・葬儀社' }} />
      
    </>
  )
}
