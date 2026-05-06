import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '熊本のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「熊本でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kumamoto/saas/' },
  openGraph: {
    title: '熊本のSaaS取扱企業、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「熊本でおすすめのMAツール・CRMは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kumamoto/saas/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '熊本', industry: 'SaaS取扱企業' }} />
      
    </>
  )
}
