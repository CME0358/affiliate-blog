import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '茨城の動物病院・ペットクリニック、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「茨城でおすすめの動物病院・ペットクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/ibaraki/pet-clinic/' },
  openGraph: {
    title: '茨城の動物病院・ペットクリニック、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「茨城でおすすめの動物病院・ペットクリニックは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/ibaraki/pet-clinic/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '茨城', industry: '動物病院・ペットクリニック' }} />
      
    </>
  )
}
