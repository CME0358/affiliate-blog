import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '運営について | QOL media',
  description: 'QOL mediaの運営方針・サイト概要についてご説明します。',
  robots: { index: false, follow: false },
}

export default function AboutPage() {
  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', padding: '48px 20px 80px' }}>
      <div style={{ marginBottom: '24px' }}>
        <Link href="/" style={{ fontSize: '12px', color: '#6b7280', textDecoration: 'none' }}>← トップに戻る</Link>
      </div>

      <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', marginBottom: '8px' }}>運営について</h1>
      <p style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '40px' }}>最終更新日：2026年3月30日</p>

      <div style={{ fontSize: '15px', lineHeight: '1.9', color: '#374151' }}>

        <Section title="サイト概要">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            {[
              ['サイト名', 'QOL media'],
              ['URL', 'https://www.qolmedia.info'],
              ['コンセプト', 'QOL（生活の質）を高める情報をわかりやすく届けるメディア'],
              ['主なテーマ', 'ペットケア・睡眠・健康・暮らし'],
              ['開設', '2026年3月'],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 16px 10px 0', fontWeight: '600', color: '#6b7280', whiteSpace: 'nowrap', width: '30%' }}>{label}</td>
                <td style={{ padding: '10px 0' }}>{value}</td>
              </tr>
            ))}
          </table>
        </Section>

        <Section title="運営者情報">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            {[
              ['運営会社', '合同会社コア・リテール'],
              ['所在地', '東京都港区麻布十番1-2-7 ラフィネ麻布十番7F'],
              ['設立', '2018年2月'],
              ['事業内容', 'デジタルマーケティング・コンテンツ制作'],
              ['お問い合わせ', 'contact'],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 16px 10px 0', fontWeight: '600', color: '#6b7280', whiteSpace: 'nowrap', width: '30%' }}>{label}</td>
                <td style={{ padding: '10px 0' }}>
                  {label === 'お問い合わせ'
                    ? <Link href="/contact" style={{ color: '#2563eb' }}>お問い合わせフォームはこちら</Link>
                    : value}
                </td>
              </tr>
            ))}
          </table>
        </Section>

        <Section title="サイトの方針">
          <p>QOL mediaは、読者が日々の生活の質を少しでも上げるための情報を、わかりやすく・正直に届けることを目的としています。</p>
          <ul style={{ paddingLeft: '24px', margin: '12px 0' }}>
            <li style={{ marginBottom: '8px' }}><strong>正確性を重視：</strong>掲載情報は公的機関・学術情報・専門家の見解をもとに作成しています</li>
            <li style={{ marginBottom: '8px' }}><strong>広告の透明性：</strong>アフィリエイトリンクを含む記事には冒頭にPR表記を入れています</li>
            <li style={{ marginBottom: '8px' }}><strong>広告主から独立：</strong>記事内容は広告主の意向に左右されません。読者にとって有益な情報を優先します</li>
            <li style={{ marginBottom: '8px' }}><strong>定期的な更新：</strong>情報の鮮度を保つために記事を定期的に見直しています</li>
          </ul>
        </Section>

        <Section title="アフィリエイト広告について">
          <p>当サイトはアフィリエイトプログラムに参加しており、紹介した商品・サービスの購入により報酬を得ることがあります。</p>
          <p>ただし、報酬の有無にかかわらず、紹介する商品はユーザーにとって有益と判断したものに限定しています。広告主から金銭を受け取って特定の商品を優遇することはありません。</p>
        </Section>

        <Section title="免責事項">
          <p>当サイトの情報は可能な限り正確を期していますが、内容の完全性・正確性を保証するものではありません。掲載情報を参考にした行動により生じた損害について、当サイトは一切の責任を負いません。</p>
          <p>特に医療・健康・ペットの治療に関する情報は参考情報であり、具体的な判断は必ず専門家（医師・獣医師等）にご相談ください。</p>
        </Section>

        <Section title="お問い合わせ">
          <p>ご意見・ご質問・記事内容の誤りのご指摘は、お問い合わせページまたは下記メールアドレスよりご連絡ください。</p>
          <p style={{ marginTop: '12px' }}>
            <Link href="/contact" style={{ display: 'inline-block', backgroundColor: '#2563eb', color: '#fff', fontSize: '13px', fontWeight: '600', padding: '10px 24px', borderRadius: '6px', textDecoration: 'none' }}>
              お問い合わせフォームはこちら
            </Link>
          </p>
        </Section>

      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '36px' }}>
      <h2 style={{ fontSize: '17px', fontWeight: '700', color: '#111827', marginBottom: '12px', paddingBottom: '8px', borderBottom: '2px solid #f3f4f6' }}>
        {title}
      </h2>
      {children}
    </div>
  )
}
