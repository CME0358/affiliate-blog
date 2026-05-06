import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '福井の遺品整理・相続手続き代行、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福井でおすすめの遺品整理・相続手続き代行は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukui/inheritance/' },
  openGraph: {
    title: '福井の遺品整理・相続手続き代行、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福井でおすすめの遺品整理・相続手続き代行は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukui/inheritance/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福井', industry: '遺品整理・相続手続き代行' }} />
      
    </>
  )
}
