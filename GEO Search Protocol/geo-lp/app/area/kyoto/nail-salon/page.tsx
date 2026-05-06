import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '京都のネイルサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「京都でおすすめのネイルサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kyoto/nail-salon/' },
  openGraph: {
    title: '京都のネイルサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「京都でおすすめのネイルサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kyoto/nail-salon/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '京都', industry: 'ネイルサロン' }} />
      
    </>
  )
}
