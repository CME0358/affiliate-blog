import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '新潟のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「新潟でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/niigata/reform/' },
  openGraph: {
    title: '新潟のリフォーム・リノベーション、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「新潟でおすすめのリフォーム会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/niigata/reform/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '新潟', industry: 'リフォーム・リノベーション' }} />
      
    </>
  )
}
