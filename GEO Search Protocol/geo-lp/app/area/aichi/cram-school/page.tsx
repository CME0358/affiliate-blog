import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '愛知の予備校・大学受験対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「愛知でおすすめの予備校・大学受験塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/aichi/cram-school/' },
  openGraph: {
    title: '愛知の予備校・大学受験対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「愛知でおすすめの予備校・大学受験塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/aichi/cram-school/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '愛知', industry: '予備校・大学受験対策' }} />
      
    </>
  )
}
