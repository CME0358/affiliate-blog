'use client'

import { useState } from 'react'
import Link from 'next/link'

// ★ GoogleフォームのURLをここに差し替える
// フォームを開いて「送信」→「<>」アイコン → iframeのsrc属性のURLをコピー
const GOOGLE_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSfUcAXwVcmRPhnN3fgMf-0C8O_O98yWdhgSrfj7EYcgVBKY5Q/viewform?usp=header'

export default function ContactPage() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <div style={{ maxWidth: '720px', margin: '0 auto', padding: '48px 20px 80px' }}>
        <div style={{ marginBottom: '24px' }}>
          <Link href="/" style={{ fontSize: '12px', color: '#6b7280', textDecoration: 'none' }}>← トップに戻る</Link>
        </div>

        <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', marginBottom: '8px' }}>お問い合わせ</h1>
        <p style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.8', marginBottom: '32px' }}>
          記事内容のご質問・誤りのご指摘・その他お問い合わせは下記フォームよりご連絡ください。<br />
          通常2〜3営業日以内にご返信いたします。
        </p>

        {/* フォーム起動ボタン */}
        <button
          onClick={() => setOpen(true)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: '8px',
            backgroundColor: '#2563eb', color: '#fff',
            fontSize: '14px', fontWeight: '700',
            padding: '14px 32px', borderRadius: '8px',
            border: 'none', cursor: 'pointer',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          お問い合わせフォームを開く
        </button>

        <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '16px' }}>
          ※ フォームはGoogleフォームを使用しています
        </p>
      </div>

      {/* ポップアップモーダル */}
      {open && (
        <div
          onClick={(e) => { if (e.target === e.currentTarget) setOpen(false) }}
          style={{
            position: 'fixed', inset: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '20px',
          }}
        >
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            width: '100%',
            maxWidth: '640px',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          }}>
            {/* モーダルヘッダー */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px',
              borderBottom: '1px solid #e5e7eb',
              flexShrink: 0,
            }}>
              <span style={{ fontSize: '14px', fontWeight: '700', color: '#111827' }}>お問い合わせフォーム</span>
              <button
                onClick={() => setOpen(false)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#6b7280', padding: '4px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>

            {/* Googleフォーム iframe */}
            <iframe
              src={GOOGLE_FORM_URL}
              style={{ width: '100%', flex: 1, border: 'none', minHeight: '520px' }}
              title="お問い合わせフォーム"
            />
          </div>
        </div>
      )}
    </>
  )
}
