import { cookies } from 'next/headers'
import type { Metadata } from 'next'
import AiscanLP from '@/components/AiscanLP'
import AiscanLP_B from '@/components/AiscanLP_B'

export const metadata: Metadata = {
  title: 'オンライン英会話・語学スクールの集客、AIに任せてますか？｜GEO無料診断',
  description: 'ChatGPT・Geminiで「おすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
  alternates: { canonical: 'https://aiscan.coaretail.com/online-school/' },
  openGraph: {
    title: 'オンライン英会話・語学スクールの集客、AIに任せてますか？｜GEO無料診断',
    description: 'ChatGPT・Geminiで「おすすめのオンライン英会話・語学スクールは？」と検索されたとき、あなたの会社・店舗は出てきますか？AI検索での認識状況を無料で診断します。',
    url: 'https://aiscan.coaretail.com/online-school/',
  },
}

export default async function Page() {
  const cookieStore = await cookies()
  const variant = cookieStore.get('geo_ab_variant')?.value ?? 'A'

  return variant === 'B'
    ? <AiscanLP_B headline={{ industry: 'オンライン英会話・語学スクール' }} />
    : <AiscanLP   headline={{ industry: 'オンライン英会話・語学スクール' }} />
}
