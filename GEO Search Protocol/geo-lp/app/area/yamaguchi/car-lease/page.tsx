import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山口のカーリース・車販売、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山口でおすすめのカーリース・車販売は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamaguchi/car-lease/' },
  openGraph: {
    title: '山口のカーリース・車販売、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山口でおすすめのカーリース・車販売は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamaguchi/car-lease/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山口', industry: 'カーリース・車販売' }} />
      
    </>
  )
}
