import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '群馬のペットホテル・トリミング、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「群馬でおすすめのペットホテル・トリミングサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/gunma/pet-hotel/' },
  openGraph: {
    title: '群馬のペットホテル・トリミング、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「群馬でおすすめのペットホテル・トリミングサロンは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/gunma/pet-hotel/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '群馬', industry: 'ペットホテル・トリミング' }} />
      
    </>
  )
}
