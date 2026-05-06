import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '京都の転職エージェント、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「京都でおすすめの転職エージェントは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kyoto/career/' },
  openGraph: {
    title: '京都の転職エージェント、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「京都でおすすめの転職エージェントは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kyoto/career/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '京都', industry: '転職エージェント' }} />
      
    </>
  )
}
