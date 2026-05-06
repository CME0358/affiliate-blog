import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '石川のエステサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「石川でおすすめのエステサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/ishikawa/esthetic/' },
  openGraph: {
    title: '石川のエステサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「石川でおすすめのエステサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/ishikawa/esthetic/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '石川', industry: 'エステサロン' }} />
      
    </>
  )
}
