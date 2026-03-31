import type { Metadata } from 'next'
import Script from 'next/script'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'QOL media | Quality Of Life情報メディア', template: '%s | QOL media' },
  description: '生活の質（QOL）を高める情報をお届けするメディア。ペットケア・健康・暮らしのヒントをわかりやすく解説します。',
  robots: { index: true, follow: true },
  icons: {
    icon: [
      { url: '/favicon.png', sizes: '32x32', type: 'image/png' },
      { url: '/favicon_16.png', sizes: '16x16', type: 'image/png' },
    ],
    apple: { url: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
    shortcut: '/favicon.png',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body style={{margin:0, padding:0, fontFamily:'-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif', backgroundColor:'#fff', color:'#1a1a1a'}}>

        {/* Google Ads tag */}
        <Script
          src="https://www.googletagmanager.com/gtag/js?id=AW-18052634530"
          strategy="afterInteractive"
        />
        <Script id="google-ads" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'AW-18052634530');
          `}
        </Script>

        <header style={{borderBottom:'1px solid #e5e7eb', backgroundColor:'#fff', position:'sticky', top:0, zIndex:50}}>
          <div style={{maxWidth:'1080px', margin:'0 auto', padding:'0 20px', height:'56px', display:'flex', alignItems:'center', justifyContent:'space-between'}}>
            <a href="/" style={{textDecoration:'none'}}>
              <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'26px', width:'auto', maxWidth:'150px', display:'block'}} />
            </a>
            <nav style={{display:'flex', alignItems:'center', gap:'8px'}}>
              <a href="/pet"    style={{fontSize:'12px', fontWeight:'600', color:'#16a34a', backgroundColor:'#dcfce7', padding:'5px 14px', borderRadius:'999px', textDecoration:'none', whiteSpace:'nowrap'}}>ペット</a>
              <a href="/health" style={{fontSize:'12px', fontWeight:'600', color:'#7c3aed', backgroundColor:'#ede9fe', padding:'5px 14px', borderRadius:'999px', textDecoration:'none', whiteSpace:'nowrap'}}>健康</a>
              <a href="/life"   style={{fontSize:'12px', fontWeight:'600', color:'#ea580c', backgroundColor:'#ffedd5', padding:'5px 14px', borderRadius:'999px', textDecoration:'none', whiteSpace:'nowrap'}}>暮らし</a>
              <a href="/sleep"  style={{fontSize:'12px', fontWeight:'600', color:'#2563eb', backgroundColor:'#dbeafe', padding:'5px 14px', borderRadius:'999px', textDecoration:'none', whiteSpace:'nowrap'}}>睡眠</a>
            </nav>
          </div>
        </header>
        <main style={{minHeight:'calc(100vh - 56px - 160px)'}}>
          {children}
        </main>
        <footer style={{borderTop:'1px solid #e5e7eb', backgroundColor:'#f9fafb', marginTop:'60px'}}>
          <div style={{maxWidth:'1080px', margin:'0 auto', padding:'40px 20px', textAlign:'center'}}>
            <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'18px', width:'auto', maxWidth:'110px', opacity:0.35, margin:'0 auto 12px', display:'block'}} />
            <p style={{fontSize:'11px', color:'#9ca3af', lineHeight:'1.8', marginBottom:'12px'}}>
              当サイトはアフィリエイト広告を含みます。<br />
              掲載情報は記事公開時点のものです。最新情報は各公式サイトをご確認ください。
            </p>
            <div style={{display:'flex', justifyContent:'center', gap:'20px', marginBottom:'12px'}}>
              <a href="/privacy" style={{fontSize:'11px', color:'#9ca3af', textDecoration:'none'}}>プライバシーポリシー</a>
              <a href="/about" style={{fontSize:'11px', color:'#9ca3af', textDecoration:'none'}}>運営について</a>
              <a href="/contact" style={{fontSize:'11px', color:'#9ca3af', textDecoration:'none'}}>お問い合わせ</a>
            </div>
            <p style={{fontSize:'11px', color:'#d1d5db'}}>© 2026 QOL media</p>
          </div>
        </footer>
      </body>
    </html>
  )
}
