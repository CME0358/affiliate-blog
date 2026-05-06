import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '沖縄の司法書士・社労士・行政書士、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「沖縄でおすすめの士業事務所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/okinawa/lawyer/' },
  openGraph: {
    title: '沖縄の司法書士・社労士・行政書士、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「沖縄でおすすめの士業事務所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/okinawa/lawyer/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '沖縄', industry: '司法書士・社労士・行政書士' }} />
      
    </>
  )
}
