import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '埼玉の不動産会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「埼玉で不動産売却のおすすめ会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/saitama/realestate/' },
  openGraph: {
    title: '埼玉の不動産会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「埼玉で不動産売却のおすすめ会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/saitama/realestate/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '埼玉', industry: '不動産会社' }} />
      
    </>
  )
}
