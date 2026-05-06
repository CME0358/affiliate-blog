import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岐阜のトランクルーム・収納サービス、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岐阜でおすすめのトランクルーム・収納サービスは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/gifu/storage/' },
  openGraph: {
    title: '岐阜のトランクルーム・収納サービス、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岐阜でおすすめのトランクルーム・収納サービスは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/gifu/storage/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岐阜', industry: 'トランクルーム・収納サービス' }} />
      
    </>
  )
}
