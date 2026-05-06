import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '愛媛の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「愛媛でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/ehime/moving/' },
  openGraph: {
    title: '愛媛の引越し業者・単身引越し、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「愛媛でおすすめの引越し業者は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/ehime/moving/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '愛媛', industry: '引越し業者・単身引越し' }} />
      
    </>
  )
}
