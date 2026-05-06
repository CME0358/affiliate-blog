import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '和歌山の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「和歌山でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/wakayama/ceremony/' },
  openGraph: {
    title: '和歌山の結婚式場・葬儀社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「和歌山でおすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/wakayama/ceremony/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '和歌山', industry: '結婚式場・葬儀社' }} />
      
    </>
  )
}
