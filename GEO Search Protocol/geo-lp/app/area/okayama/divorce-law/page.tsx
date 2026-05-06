import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'

export const metadata: Metadata = {
  title: '岡山の離婚専門弁護士・調停サポート、AIに無視されていませんか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「岡山でおすすめの離婚専門弁護士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/area/okayama/divorce-law/' },
  openGraph: {
    title: '岡山の離婚専門弁護士・調停サポート、AIに無視されていませんか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「岡山でおすすめの離婚専門弁護士は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/area/okayama/divorce-law/',
  },
}

export default function Page() {
  return (
    <>
      <AiscanLP headline={{ area: '岡山', industry: '離婚専門弁護士・調停サポート' }} />
      
    </>
  )
}
