import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岐阜の学習塾・個別指導塾、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岐阜でおすすめの学習塾・個別指導塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/gifu/childcare/' },
  openGraph: {
    title: '岐阜の学習塾・個別指導塾、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岐阜でおすすめの学習塾・個別指導塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/gifu/childcare/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岐阜', industry: '学習塾・個別指導塾' }} />
      
    </>
  )
}
