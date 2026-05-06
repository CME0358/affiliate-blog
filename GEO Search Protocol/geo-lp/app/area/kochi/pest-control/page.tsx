import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '高知の害虫駆除・シロアリ対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「高知でおすすめの害虫駆除・シロアリ対策業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kochi/pest-control/' },
  openGraph: {
    title: '高知の害虫駆除・シロアリ対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「高知でおすすめの害虫駆除・シロアリ対策業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kochi/pest-control/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '高知', industry: '害虫駆除・シロアリ対策' }} />
      
    </>
  )
}
