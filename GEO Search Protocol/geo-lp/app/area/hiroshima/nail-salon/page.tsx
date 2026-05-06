import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '広島のネイルサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「広島でおすすめのネイルサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/hiroshima/nail-salon/' },
  openGraph: {
    title: '広島のネイルサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「広島でおすすめのネイルサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/hiroshima/nail-salon/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '広島', industry: 'ネイルサロン' }} />
      
    </>
  )
}
