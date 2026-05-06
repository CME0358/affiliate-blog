import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山口のペットホテル・トリミング、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山口でおすすめのペットホテル・トリミングサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamaguchi/pet-hotel/' },
  openGraph: {
    title: '山口のペットホテル・トリミング、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山口でおすすめのペットホテル・トリミングサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamaguchi/pet-hotel/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山口', industry: 'ペットホテル・トリミング' }} />
      
    </>
  )
}
