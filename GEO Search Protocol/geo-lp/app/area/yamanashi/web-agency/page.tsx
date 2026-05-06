import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '山梨のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「山梨でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/yamanashi/web-agency/' },
  openGraph: {
    title: '山梨のWeb制作・マーケティング支援、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「山梨でおすすめのWeb制作会社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/yamanashi/web-agency/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '山梨', industry: 'Web制作・マーケティング支援' }} />
      
    </>
  )
}
