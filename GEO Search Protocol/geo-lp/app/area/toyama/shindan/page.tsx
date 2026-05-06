import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '富山の‘おすすめ業者’検索で、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「富山でAI検索対策の無料診断は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/toyama/shindan/' },
  openGraph: {
    title: '富山の‘おすすめ業者’検索で、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「富山でAI検索対策の無料診断は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/toyama/shindan/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '富山', industry: '__none__' }} />
      
    </>
  )
}
