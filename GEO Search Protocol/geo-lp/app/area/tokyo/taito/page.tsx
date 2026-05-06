import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '台東区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPTやGeminiで「台東区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/taito/' },
  openGraph: {
    title: '台東区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPTやGeminiで「台東区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/taito/',
  },
}

export default function Page() {
  return <AiscanLP headline={{ area: '台東区', industry: '表示' }} />
}
