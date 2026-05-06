import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '大分の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「大分でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/oita/fertility/' },
  openGraph: {
    title: '大分の不妊治療クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「大分でおすすめの不妊治療クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/oita/fertility/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '大分', industry: '不妊治療クリニック' }} />
      
    </>
  )
}
