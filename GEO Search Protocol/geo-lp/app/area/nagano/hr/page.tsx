import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '長野の採用支援企業、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「長野でおすすめの求人・転職先は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/nagano/hr/' },
  openGraph: {
    title: '長野の採用支援企業、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「長野でおすすめの求人・転職先は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/nagano/hr/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '長野', industry: '採用支援企業' }} />
      
    </>
  )
}
