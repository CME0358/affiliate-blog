import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '群馬の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「群馬でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/gunma/seitai/' },
  openGraph: {
    title: '群馬の整体院・整骨院、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「群馬でおすすめの整体院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/gunma/seitai/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '群馬', industry: '整体院・整骨院' }} />
      
    </>
  )
}
