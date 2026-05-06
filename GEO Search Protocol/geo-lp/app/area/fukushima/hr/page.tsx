import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '福島の採用支援企業、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福島でおすすめの求人・転職先は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukushima/hr/' },
  openGraph: {
    title: '福島の採用支援企業、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福島でおすすめの求人・転職先は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukushima/hr/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福島', industry: '採用支援企業' }} />
      
    </>
  )
}
