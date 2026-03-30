import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'プライバシーポリシー | QOL media',
  description: 'QOL mediaのプライバシーポリシーです。',
  robots: { index: false, follow: false },
}

export default function PrivacyPage() {
  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', padding: '48px 20px 80px' }}>
      <div style={{ marginBottom: '24px' }}>
        <Link href="/" style={{ fontSize: '12px', color: '#6b7280', textDecoration: 'none' }}>← トップに戻る</Link>
      </div>

      <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', marginBottom: '8px' }}>プライバシーポリシー</h1>
      <p style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '40px' }}>最終更新日：2026年3月30日</p>

      <div style={{ fontSize: '15px', lineHeight: '1.9', color: '#374151' }}>

        <p>QOL media（以下「当サイト」）は、ユーザーの個人情報の取り扱いについて、以下のとおりプライバシーポリシーを定めます。</p>

        <Section title="運営者情報">
          <p>運営：合同会社コア・リテール<br />
          所在地：東京都港区麻布十番1-2-7 ラフィネ麻布十番7F<br />
          お問い合わせ：<a href="mailto:info@qolmedia.info" style={{ color: '#2563eb' }}>info@qolmedia.info</a></p>
        </Section>

        <Section title="取得する情報と利用目的">
          <p>当サイトでは、以下の情報を取得することがあります。</p>
          <ul style={{ paddingLeft: '24px', margin: '12px 0' }}>
            <li style={{ marginBottom: '6px' }}>お問い合わせフォームからご入力いただいた氏名・メールアドレス・お問い合わせ内容</li>
            <li style={{ marginBottom: '6px' }}>Googleアナリティクスによるアクセスログ（IPアドレス、ブラウザ情報、閲覧ページ等）</li>
          </ul>
          <p>取得した情報は、お問い合わせへの回答、サービス改善、統計分析のみに使用し、その他の目的には使用しません。</p>
        </Section>

        <Section title="第三者への情報提供">
          <p>当サイトは、以下の場合を除き、取得した個人情報を第三者に提供しません。</p>
          <ul style={{ paddingLeft: '24px', margin: '12px 0' }}>
            <li style={{ marginBottom: '6px' }}>法令に基づく場合</li>
            <li style={{ marginBottom: '6px' }}>人の生命・身体・財産の保護のために必要な場合</li>
            <li style={{ marginBottom: '6px' }}>公衆衛生の向上または児童の健全育成のために特に必要な場合</li>
            <li style={{ marginBottom: '6px' }}>国または地方公共団体の事務遂行に協力する必要がある場合</li>
          </ul>
        </Section>

        <Section title="アフィリエイト広告について">
          <p>当サイトはアフィリエイトプログラムに参加しています。記事内のリンクから商品を購入された場合、当サイトに報酬が発生することがあります。ただし、掲載内容はユーザーの利益を第一に作成しており、広告主からの依頼による記事は存在しません。</p>
          <p>アフィリエイトリンクが含まれる記事には、記事冒頭に「PR・広告を含む記事です」と明記しています。</p>
        </Section>

        <Section title="Googleアナリティクスについて">
          <p>当サイトはGoogleアナリティクスを使用しています。Googleアナリティクスはクッキーを使用してアクセス情報を収集しますが、個人を特定する情報は収集しません。収集されたデータはGoogleのプライバシーポリシーに基づき管理されます。</p>
          <p>Googleアナリティクスのオプトアウトは<a href="https://tools.google.com/dlpage/gaoptout" target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>こちら</a>から設定できます。</p>
        </Section>

        <Section title="クッキー（Cookie）について">
          <p>当サイトはクッキーを使用することがあります。クッキーはブラウザの設定から拒否することが可能です。ただし、クッキーを無効にした場合、一部の機能が正常に動作しないことがあります。</p>
        </Section>

        <Section title="個人情報の開示・訂正・削除">
          <p>ユーザーご本人（または代理人）から、ご自身の個人情報の開示・訂正・削除を求められた場合は、合理的な範囲内で速やかに対応いたします。お問い合わせは下記メールアドレスまでご連絡ください。</p>
          <p><a href="mailto:info@qolmedia.info" style={{ color: '#2563eb' }}>info@qolmedia.info</a></p>
        </Section>

        <Section title="免責事項">
          <p>当サイトの情報は、可能な限り正確な情報の提供を心がけていますが、正確性・完全性を保証するものではありません。掲載情報に基づいた行動により生じた損害については、当サイトは一切の責任を負いません。最新情報は各公式サイトをご確認ください。</p>
        </Section>

        <Section title="プライバシーポリシーの変更">
          <p>当サイトは、必要に応じて本ポリシーを変更することがあります。変更後のポリシーは本ページに掲載した時点で効力を生じるものとします。</p>
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
