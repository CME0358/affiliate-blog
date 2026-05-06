import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岩手の皮膚科・アトピークリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岩手でおすすめの皮膚科・アトピークリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/iwate/dermatology/' },
  openGraph: {
    title: '岩手の皮膚科・アトピークリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岩手でおすすめの皮膚科・アトピークリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/iwate/dermatology/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岩手', industry: '皮膚科・アトピークリニック' }} />
      
    </>
  )
}
