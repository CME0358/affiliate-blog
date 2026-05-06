import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '鳥取の司法書士・社労士・行政書士、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「鳥取でおすすめの士業事務所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tottori/lawyer/' },
  openGraph: {
    title: '鳥取の司法書士・社労士・行政書士、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「鳥取でおすすめの士業事務所は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tottori/lawyer/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '鳥取', industry: '司法書士・社労士・行政書士' }} />
      
    </>
  )
}
