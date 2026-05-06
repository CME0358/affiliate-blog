import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岩手の人材派遣・スタッフィング、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岩手でおすすめの人材派遣会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/iwate/temp-agency/' },
  openGraph: {
    title: '岩手の人材派遣・スタッフィング、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岩手でおすすめの人材派遣会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/iwate/temp-agency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岩手', industry: '人材派遣・スタッフィング' }} />
      
    </>
  )
}
