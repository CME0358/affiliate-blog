import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '愛知の整形外科・スポーツ整体、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「愛知でおすすめの整形外科・スポーツ整体は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/aichi/orthopedics/' },
  openGraph: {
    title: '愛知の整形外科・スポーツ整体、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「愛知でおすすめの整形外科・スポーツ整体は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/aichi/orthopedics/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '愛知', industry: '整形外科・スポーツ整体' }} />
      
    </>
  )
}
