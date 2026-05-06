import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '富山の学習塾・個別指導塾、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「富山でおすすめの学習塾・個別指導塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/toyama/childcare/' },
  openGraph: {
    title: '富山の学習塾・個別指導塾、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「富山でおすすめの学習塾・個別指導塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/toyama/childcare/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '富山', industry: '学習塾・個別指導塾' }} />
      
    </>
  )
}
