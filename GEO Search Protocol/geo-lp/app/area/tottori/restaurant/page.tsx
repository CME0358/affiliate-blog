import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '鳥取の飲食店、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「鳥取でおすすめの飲食店は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tottori/restaurant/' },
  openGraph: {
    title: '鳥取の飲食店、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「鳥取でおすすめの飲食店は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tottori/restaurant/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '鳥取', industry: '飲食店' }} />
      
    </>
  )
}
