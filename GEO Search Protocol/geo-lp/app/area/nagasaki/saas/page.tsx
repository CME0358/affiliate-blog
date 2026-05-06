import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '長崎のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「長崎でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/nagasaki/saas/' },
  openGraph: {
    title: '長崎のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「長崎でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/nagasaki/saas/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '長崎', industry: 'SaaS取扱企業' }} />
      
    </>
  )
}
