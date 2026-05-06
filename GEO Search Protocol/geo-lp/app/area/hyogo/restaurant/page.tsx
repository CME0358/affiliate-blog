import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '兵庫の飲食店、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「兵庫でおすすめの飲食店は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/hyogo/restaurant/' },
  openGraph: {
    title: '兵庫の飲食店、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「兵庫でおすすめの飲食店は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/hyogo/restaurant/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '兵庫', industry: '飲食店' }} />
      
    </>
  )
}
