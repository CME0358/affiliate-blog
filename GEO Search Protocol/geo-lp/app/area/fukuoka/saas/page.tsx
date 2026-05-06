import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '福岡のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福岡でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukuoka/saas/' },
  openGraph: {
    title: '福岡のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福岡でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukuoka/saas/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福岡', industry: 'SaaS取扱企業' }} />
      
    </>
  )
}
