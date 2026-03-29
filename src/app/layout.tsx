import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'QOL media | Quality Of Life情報メディア', template: '%s | QOL media' },
  description: '生活の質（QOL）を高める情報をお届けするメディア。ペットケア・健康・暮らしのヒントをわかりやすく解説します。',
  robots: { index: true, follow: true },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body style={{margin:0, padding:0, fontFamily:'-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif', backgroundColor:'#fff', color:'#1a1a1a'}}>
        <header style={{borderBottom:'1px solid #e5e7eb', backgroundColor:'#fff', position:'sticky', top:0, zIndex:50}}>
          <div style={{maxWidth:'960px', margin:'0 auto', padding:'0 20px', height:'56px', display:'flex', alignItems:'center', justifyContent:'space-between'}}>
            <a href="/" style={{textDecoration:'none'}}>
              <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'26px', width:'auto', maxWidth:'150px', display:'block'}} />
            </a>
            <nav style={{display:'flex', alignItems:'center', gap:'24px'}}>
              <a href="/pet" style={{fontSize:'13px', color:'#6b7280', textDecoration:'none'}}>ペット</a>
              <a href="/health" style={{fontSize:'13px', color:'#6b7280', textDecoration:'none'}}>健康</a>
              <a href="/life" style={{fontSize:'13px', color:'#6b7280', textDecoration:'none'}}>暮らし</a>
            </nav>
          </div>
        </header>
        <main style={{minHeight:'calc(100vh - 56px - 160px)'}}>
          {children}
        </main>
        <footer style={{borderTop:'1px solid #e5e7eb', backgroundColor:'#f9fafb', marginTop:'60px'}}>
          <div style={{maxWidth:'960px', margin:'0 auto', padding:'40px 20px', textAlign:'center'}}>
            <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'18px', width:'auto', maxWidth:'110px', opacity:0.3, margin:'0 auto 12px', display:'block'}} />
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
