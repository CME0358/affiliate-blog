import { cookies } from 'next/headers'
import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'
import AiscanLP_B from '@/components/AiscanLP_B'

export const metadata: Metadata = {
  title: '結婚式場・葬儀社の集客、AIに任せてますか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「おすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/ceremony/' },
  openGraph: {
    title: '結婚式場・葬儀社の集客、AIに任せてますか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「おすすめの結婚式場・葬儀社は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/ceremony/',
  },
}

export default async function Page() {
  const cookieStore = await cookies()
  const variant = cookieStore.get('geo_ab_variant')?.value ?? 'A'

  return variant === 'B'
    ? <AiscanLP_B headline={{ industry: '結婚式場・葬儀社' }} />
    : <AiscanLP   headline={{ industry: '結婚式場・葬儀社' }} />
}
