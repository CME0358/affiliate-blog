import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '三重の弁護士事務所、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「三重でおすすめの弁護士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/mie/lawyer-general/' },
  openGraph: {
    title: '三重の弁護士事務所、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「三重でおすすめの弁護士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/mie/lawyer-general/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '三重', industry: '弁護士事務所' }} />
      
    </>
  )
}
