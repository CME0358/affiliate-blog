import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '佐賀のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「佐賀でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/saga/meo/' },
  openGraph: {
    title: '佐賀のMEO対策会社、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「佐賀でおすすめのMEO対策会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/saga/meo/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '佐賀', industry: 'MEO対策会社' }} />
      
    </>
  )
}
