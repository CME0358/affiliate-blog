import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '新潟の緊急修理業者、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「新潟で近くの水道修理業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/niigata/emergency/' },
  openGraph: {
    title: '新潟の緊急修理業者、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「新潟で近くの水道修理業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/niigata/emergency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '新潟', industry: '緊急修理業者' }} />
      
    </>
  )
}
