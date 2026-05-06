import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '沖縄の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「沖縄でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/okinawa/moving/' },
  openGraph: {
    title: '沖縄の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「沖縄でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/okinawa/moving/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '沖縄', industry: '引越し業者・単身引越し' }} />
      
    </>
  )
}
