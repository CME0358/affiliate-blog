import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '香川のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「香川でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kagawa/reform/' },
  openGraph: {
    title: '香川のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「香川でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kagawa/reform/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '香川', industry: 'リフォーム・リノベーション' }} />
      
    </>
  )
}
