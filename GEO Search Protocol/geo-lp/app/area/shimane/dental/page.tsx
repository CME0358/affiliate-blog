import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '島根の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「島根でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/shimane/dental/' },
  openGraph: {
    title: '島根の歯科クリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「島根でおすすめの歯科クリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/shimane/dental/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '島根', industry: '歯科クリニック' }} />
      
    </>
  )
}
