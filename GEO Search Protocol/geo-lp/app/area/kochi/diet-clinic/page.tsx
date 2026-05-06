import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '高知のダイエット外来・肥満外科、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「高知でおすすめのダイエット外来は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kochi/diet-clinic/' },
  openGraph: {
    title: '高知のダイエット外来・肥満外科、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「高知でおすすめのダイエット外来は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kochi/diet-clinic/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '高知', industry: 'ダイエット外来・肥満外科' }} />
      
    </>
  )
}
