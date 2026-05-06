import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '中野区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPTやGeminiで「中野区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/nakano/' },
  openGraph: {
    title: '中野区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPTやGeminiで「中野区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/nakano/',
  },
}

export default function Page() {
  return <AiscanLP headline={{ area: '中野区', industry: '表示' }} />
}
