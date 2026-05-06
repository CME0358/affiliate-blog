import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '富山の保険代理店・FP相談、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「富山でおすすめの保険代理店・FP相談は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/toyama/insurance/' },
  openGraph: {
    title: '富山の保険代理店・FP相談、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「富山でおすすめの保険代理店・FP相談は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/toyama/insurance/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '富山', industry: '保険代理店・FP相談' }} />
      
    </>
  )
}
