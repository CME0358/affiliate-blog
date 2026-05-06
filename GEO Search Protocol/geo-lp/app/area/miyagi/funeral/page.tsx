import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '宮城の葬儀・斎場、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「宮城でおすすめの葬儀社・斎場は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/miyagi/funeral/' },
  openGraph: {
    title: '宮城の葬儀・斎場、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「宮城でおすすめの葬儀社・斎場は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/miyagi/funeral/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '宮城', industry: '葬儀・斎場' }} />
      
    </>
  )
}
