import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '葛飾区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPTやGeminiで「葛飾区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tokyo/katsushika/' },
  openGraph: {
    title: '葛飾区のGEO対策、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPTやGeminiで「葛飾区 おすすめ」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tokyo/katsushika/',
  },
}

export default function Page() {
  return <AiscanLP headline={{ area: '葛飾区', industry: '表示' }} />
}
