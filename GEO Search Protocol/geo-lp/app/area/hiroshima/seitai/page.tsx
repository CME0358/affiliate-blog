import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '広島の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「広島でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/hiroshima/seitai/' },
  openGraph: {
    title: '広島の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「広島でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/hiroshima/seitai/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '広島', industry: '整体院・整骨院' }} />
      
    </>
  )
}
