import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山形のオンライン英会話・語学スクール、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山形でおすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamagata/online-school/' },
  openGraph: {
    title: '山形のオンライン英会話・語学スクール、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山形でおすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamagata/online-school/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山形', industry: 'オンライン英会話・語学スクール' }} />
      
    </>
  )
}
