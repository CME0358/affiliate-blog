import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '神奈川の不動産会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「神奈川で不動産売却のおすすめ会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/kanagawa/realestate/' },
  openGraph: {
    title: '神奈川の不動産会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「神奈川で不動産売却のおすすめ会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/kanagawa/realestate/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '神奈川', industry: '不動産会社' }} />
      
    </>
  )
}
