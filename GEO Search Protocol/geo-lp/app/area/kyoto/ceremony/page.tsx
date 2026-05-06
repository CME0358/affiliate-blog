import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '京都の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「京都でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kyoto/ceremony/' },
  openGraph: {
    title: '京都の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「京都でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kyoto/ceremony/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '京都', industry: '結婚式場・葬儀社' }} />
      
    </>
  )
}
