import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '滋賀の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「滋賀でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/shiga/hair-salon/' },
  openGraph: {
    title: '滋賀の美容院・ヘアサロン、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「滋賀でおすすめの美容院は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/shiga/hair-salon/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '滋賀', industry: '美容院・ヘアサロン' }} />
      
    </>
  )
}
