import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '鳥取の緊急修理業者、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「鳥取で近くの水道修理業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tottori/emergency/' },
  openGraph: {
    title: '鳥取の緊急修理業者、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「鳥取で近くの水道修理業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tottori/emergency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '鳥取', industry: '緊急修理業者' }} />
      
    </>
  )
}
