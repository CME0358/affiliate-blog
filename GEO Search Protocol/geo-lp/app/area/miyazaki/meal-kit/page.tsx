import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '宮崎の食材宅配・ミールキット、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「宮崎でおすすめの食材宅配・ミールキットは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/miyazaki/meal-kit/' },
  openGraph: {
    title: '宮崎の食材宅配・ミールキット、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「宮崎でおすすめの食材宅配・ミールキットは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/miyazaki/meal-kit/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '宮崎', industry: '食材宅配・ミールキット' }} />
      
    </>
  )
}
