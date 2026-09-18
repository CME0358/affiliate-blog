import type { Metadata } from 'next'
import Script from 'next/script'
import './globals.css'
import { HOME_DESCRIPTION, HOME_TITLE, SITE_NAME, SITE_URL } from '@/lib/site'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: HOME_TITLE, template: '%s | QOL media' },
  description: HOME_DESCRIPTION,
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  alternates: {
    canonical: SITE_URL,
    types: {
      'text/plain': '/llms.txt',
    },
  },
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    locale: 'ja_JP',
    title: HOME_TITLE,
    description: HOME_DESCRIPTION,
    url: SITE_URL,
    images: [{ url: '/og-default.svg', width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: {
    card: 'summary_large_image',
    title: HOME_TITLE,
    description: HOME_DESCRIPTION,
    images: ['/og-default.svg'],
  },
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
      <head>
        <link rel="describedby" href={`${SITE_URL}/llms.txt`} />
      </head>
      <body style={{margin:0, padding:0, fontFamily:'-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif', backgroundColor:'#fff', color:'#1a1a1a'}}>

        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@graph': [
                {
                  '@type': 'Organization',
                  '@id': `${SITE_URL}/#organization`,
                  name: SITE_NAME,
                  url: SITE_URL,
                  logo: `${SITE_URL}/QOL_logo_transparent.png`,
                  description: HOME_DESCRIPTION,
                },
                {
                  '@type': 'WebSite',
                  '@id': `${SITE_URL}/#website`,
                  name: SITE_NAME,
                  url: SITE_URL,
                  inLanguage: 'ja-JP',
                  description: HOME_DESCRIPTION,
                  publisher: { '@id': `${SITE_URL}/#organization` },
                },
              ],
            }),
          }}
        />

        {/* --- Google AdSense --- */}
        <Script
          async
          src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7396006052703860"
          crossOrigin="anonymous"
          strategy="afterInteractive"
        />

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

        {/* Google Analytics GA4 */}
        <Script
          src="https://www.googletagmanager.com/gtag/js?id=G-BS30YQY1N7"
          strategy="afterInteractive"
        />
        <Script id="google-analytics" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-BS30YQY1N7');
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
