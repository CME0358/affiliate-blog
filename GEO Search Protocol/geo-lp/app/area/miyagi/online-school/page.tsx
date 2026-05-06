import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '宮城のオンライン英会話・語学スクール、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「宮城でおすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/miyagi/online-school/' },
  openGraph: {
    title: '宮城のオンライン英会話・語学スクール、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「宮城でおすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/miyagi/online-school/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '宮城', industry: 'オンライン英会話・語学スクール' }} />
      
    </>
  )
}
