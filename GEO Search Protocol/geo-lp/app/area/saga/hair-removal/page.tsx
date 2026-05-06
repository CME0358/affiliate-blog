import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '佐賀の医療脱毛・エステ脱毛、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「佐賀でおすすめの医療脱毛は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/saga/hair-removal/' },
  openGraph: {
    title: '佐賀の医療脱毛・エステ脱毛、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「佐賀でおすすめの医療脱毛は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/saga/hair-removal/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '佐賀', industry: '医療脱毛・エステ脱毛' }} />
      
    </>
  )
}
