import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '京都の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「京都でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kyoto/fertility/' },
  openGraph: {
    title: '京都の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「京都でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kyoto/fertility/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '京都', industry: '不妊治療クリニック' }} />
      
    </>
  )
}
