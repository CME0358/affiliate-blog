import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '品川区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPTやGeminiで「品川区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/shinagawa/' },
  openGraph: {
    title: '品川区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPTやGeminiで「品川区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/shinagawa/',
  },
}

export default function Page() {
  return <AiscanLP headline={{ area: '品川区', industry: '表示' }} />
}
