import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '福井の保険代理店・FP相談、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福井でおすすめの保険代理店・FP相談は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukui/insurance/' },
  openGraph: {
    title: '福井の保険代理店・FP相談、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福井でおすすめの保険代理店・FP相談は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukui/insurance/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福井', industry: '保険代理店・FP相談' }} />
      
    </>
  )
}
