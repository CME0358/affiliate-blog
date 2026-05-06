import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '福島の税理士・会計士、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「福島でおすすめの税理士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/fukushima/accountant/' },
  openGraph: {
    title: '福島の税理士・会計士、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「福島でおすすめの税理士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/fukushima/accountant/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '福島', industry: '税理士・会計士' }} />
      
    </>
  )
}
