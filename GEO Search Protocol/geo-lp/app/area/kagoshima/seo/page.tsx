import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '鹿児島のSEO対策会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「鹿児島でおすすめのSEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kagoshima/seo/' },
  openGraph: {
    title: '鹿児島のSEO対策会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「鹿児島でおすすめのSEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kagoshima/seo/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '鹿児島', industry: 'SEO対策会社' }} />
      
    </>
  )
}
