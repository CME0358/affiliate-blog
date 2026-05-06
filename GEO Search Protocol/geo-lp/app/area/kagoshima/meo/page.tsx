import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '鹿児島のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「鹿児島でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kagoshima/meo/' },
  openGraph: {
    title: '鹿児島のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「鹿児島でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kagoshima/meo/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '鹿児島', industry: 'MEO対策会社' }} />
      
    </>
  )
}
