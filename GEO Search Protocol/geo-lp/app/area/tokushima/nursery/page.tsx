import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '徳島の保育園・託児所、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「徳島でおすすめの保育園・託児所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokushima/nursery/' },
  openGraph: {
    title: '徳島の保育園・託児所、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「徳島でおすすめの保育園・託児所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokushima/nursery/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '徳島', industry: '保育園・託児所' }} />
      
    </>
  )
}
