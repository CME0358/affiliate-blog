import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '埼玉のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「埼玉でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/saitama/reform/' },
  openGraph: {
    title: '埼玉のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「埼玉でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/saitama/reform/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '埼玉', industry: 'リフォーム・リノベーション' }} />
      
    </>
  )
}
