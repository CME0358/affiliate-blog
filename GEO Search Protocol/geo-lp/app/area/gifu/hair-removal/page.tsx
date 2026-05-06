import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岐阜の医療脱毛・エステ脱毛、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岐阜でおすすめの医療脱毛は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/gifu/hair-removal/' },
  openGraph: {
    title: '岐阜の医療脱毛・エステ脱毛、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岐阜でおすすめの医療脱毛は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/gifu/hair-removal/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岐阜', industry: '医療脱毛・エステ脱毛' }} />
      
    </>
  )
}
