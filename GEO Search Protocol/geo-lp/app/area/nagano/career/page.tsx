import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '長野の転職エージェント、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「長野でおすすめの転職エージェントは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/nagano/career/' },
  openGraph: {
    title: '長野の転職エージェント、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「長野でおすすめの転職エージェントは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/nagano/career/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '長野', industry: '転職エージェント' }} />
      
    </>
  )
}
