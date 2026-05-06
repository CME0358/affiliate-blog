import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岩手のAGA・薄毛治療、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岩手でおすすめのAGAクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/iwate/aga/' },
  openGraph: {
    title: '岩手のAGA・薄毛治療、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岩手でおすすめのAGAクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/iwate/aga/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岩手', industry: 'AGA・薄毛治療' }} />
      
    </>
  )
}
