import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '広島の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「広島でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/hiroshima/moving/' },
  openGraph: {
    title: '広島の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「広島でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/hiroshima/moving/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '広島', industry: '引越し業者・単身引越し' }} />
      
    </>
  )
}
