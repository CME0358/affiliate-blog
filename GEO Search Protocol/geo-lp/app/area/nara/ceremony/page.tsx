import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '奈良の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「奈良でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/nara/ceremony/' },
  openGraph: {
    title: '奈良の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「奈良でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/nara/ceremony/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '奈良', industry: '結婚式場・葬儀社' }} />
      
    </>
  )
}
