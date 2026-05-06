import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '栃木の動物病院・ペットクリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「栃木でおすすめの動物病院・ペットクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/tochigi/pet-clinic/' },
  openGraph: {
    title: '栃木の動物病院・ペットクリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「栃木でおすすめの動物病院・ペットクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/tochigi/pet-clinic/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '栃木', industry: '動物病院・ペットクリニック' }} />
      
    </>
  )
}
