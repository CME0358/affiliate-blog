import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '島根のプログラミングスクール、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「島根でおすすめのプログラミングスクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/shimane/programming/' },
  openGraph: {
    title: '島根のプログラミングスクール、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「島根でおすすめのプログラミングスクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/shimane/programming/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '島根', industry: 'プログラミングスクール' }} />
      
    </>
  )
}
