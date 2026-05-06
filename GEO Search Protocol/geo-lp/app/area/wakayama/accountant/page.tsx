import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '和歌山の税理士・会計士、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「和歌山でおすすめの税理士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/wakayama/accountant/' },
  openGraph: {
    title: '和歌山の税理士・会計士、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「和歌山でおすすめの税理士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/wakayama/accountant/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '和歌山', industry: '税理士・会計士' }} />
      
    </>
  )
}
