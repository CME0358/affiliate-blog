import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '愛媛のハウスクリーニング・エアコン清掃、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「愛媛でおすすめのハウスクリーニング業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/ehime/cleaning/' },
  openGraph: {
    title: '愛媛のハウスクリーニング・エアコン清掃、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「愛媛でおすすめのハウスクリーニング業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/ehime/cleaning/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '愛媛', industry: 'ハウスクリーニング・エアコン清掃' }} />
      
    </>
  )
}
