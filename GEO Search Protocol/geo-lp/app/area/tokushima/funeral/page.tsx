import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '徳島の葬儀・斎場、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「徳島でおすすめの葬儀社・斎場は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokushima/funeral/' },
  openGraph: {
    title: '徳島の葬儀・斎場、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「徳島でおすすめの葬儀社・斎場は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokushima/funeral/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '徳島', industry: '葬儀・斎場' }} />
      
    </>
  )
}
