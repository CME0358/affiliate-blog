import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山形の保育園・託児所、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山形でおすすめの保育園・託児所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamagata/nursery/' },
  openGraph: {
    title: '山形の保育園・託児所、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山形でおすすめの保育園・託児所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamagata/nursery/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山形', industry: '保育園・託児所' }} />
      
    </>
  )
}
