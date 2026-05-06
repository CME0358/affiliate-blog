import { cookies } from 'next/headers'
import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'
import AiscanLP_B from '@/components/AiscanLP_B'

export const metadata: Metadata = {
  title: 'ダイエット外来・肥満外科の集客、AIに任せてますか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「おすすめのダイエット外来・肥満外科は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/diet-clinic/' },
  openGraph: {
    title: 'ダイエット外来・肥満外科の集客、AIに任せてますか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「おすすめのダイエット外来・肥満外科は？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/diet-clinic/',
  },
}

export default async function Page() {
  const cookieStore = await cookies()
  const variant = cookieStore.get('geo_ab_variant')?.value ?? 'A'

  return variant === 'B'
    ? <AiscanLP_B headline={{ industry: 'ダイエット外来・肥満外科' }} />
    : <AiscanLP   headline={{ industry: 'ダイエット外来・肥満外科' }} />
}
