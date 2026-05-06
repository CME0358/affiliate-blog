import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '高知の予備校・大学受験対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「高知でおすすめの予備校・大学受験塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kochi/cram-school/' },
  openGraph: {
    title: '高知の予備校・大学受験対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「高知でおすすめの予備校・大学受験塾は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kochi/cram-school/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '高知', industry: '予備校・大学受験対策' }} />
      
    </>
  )
}
