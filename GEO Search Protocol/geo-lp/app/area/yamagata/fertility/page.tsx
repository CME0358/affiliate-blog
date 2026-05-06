import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山形の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山形でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamagata/fertility/' },
  openGraph: {
    title: '山形の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山形でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamagata/fertility/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山形', industry: '不妊治療クリニック' }} />
      
    </>
  )
}
