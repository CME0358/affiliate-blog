import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '茨城のハウスクリーニング・エアコン清掃、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「茨城でおすすめのハウスクリーニング業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/ibaraki/cleaning/' },
  openGraph: {
    title: '茨城のハウスクリーニング・エアコン清掃、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「茨城でおすすめのハウスクリーニング業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/ibaraki/cleaning/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '茨城', industry: 'ハウスクリーニング・エアコン清掃' }} />
      
    </>
  )
}
