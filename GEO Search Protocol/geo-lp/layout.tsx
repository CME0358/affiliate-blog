import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI検索・GEO無料診断｜MEO対策の次はGEO｜GEO Search Protocol',
  description: 'ChatGPT・Gemini・Perplexityにあなたの会社は表示されていますか？AI検索最適化（GEO）の無料診断を実施中。MEO対策済みの企業こそ、次はGEO対策が必要です。',
  keywords: 'GEO,AI検索最適化,MEO AI検索,GEOコンサル,AI検索 無料診断,SEO 無料診断,ChatGPT 表示,Gemini 企業検索',
  openGraph: {
    title: 'AIに「おすすめ企業」として表示されていますか？無料診断実施中',
    description: 'MEO対策の次はGEO。ChatGPT・Gemini・Perplexity・Claudeでの表示状況を無料で診断します。',
  }
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <head>
        {/* Google Fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Inter:wght@400;600;700&display=optional"
          rel="stylesheet"
        />

        {/* Google Analytics (GA4) */}
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-RTVYFRXR2M" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', 'G-RTVYFRXR2M');
            `,
          }}
        />

        {/* Google Ads */}
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-BS30YQY1N7" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', 'G-BS30YQY1N7');
            `,
          }}
        />

        {/* LinkedIn Insight Tag */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              _linkedin_partner_id = "8978180";
              window._linkedin_data_partner_ids = window._linkedin_data_partner_ids || [];
              window._linkedin_data_partner_ids.push(_linkedin_partner_id);
              (function(l) {
                if (!l){window.lintrk = function(a,b){window.lintrk.q.push([a,b])};
                window.lintrk.q=[]}
                var s = document.getElementsByTagName("script")[0];
                var b = document.createElement("script");
                b.type = "text/javascript";b.async = true;
                b.src = "https://snap.licdn.com/li.lms-analytics/insight.min.js";
                s.parentNode.insertBefore(b, s);
              })(window.lintrk);
            `,
          }}
        />

        {/* Schema.org 構造化データ */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@graph": [
                {
                  "@type": "Organization",
                  "@id": "https://aiscan.coaretail.com/#organization",
                  "name": "合同会社コア・リテール",
                  "alternateName": "CoaRetail G.K.",
                  "url": "https://www.coaretail.com",
                  "logo": "https://www.coaretail.com/logo.png",
                  "sameAs": ["https://www.coaretail.com"]
                },
                {
                  "@type": "WebPage",
                  "@id": "https://aiscan.coaretail.com/#webpage",
                  "url": "https://aiscan.coaretail.com",
                  "name": "AI表示診断｜GEO Search Protocol",
                  "description": "ChatGPT・Gemini・Perplexity・Claudeにあなたの会社は表示されていますか？4つのAIでの認識状況を無料で可視化します。",
                  "inLanguage": "ja",
                  "publisher": {
                    "@id": "https://aiscan.coaretail.com/#organization"
                  }
                },
                {
                  "@type": "Service",
                  "@id": "https://aiscan.coaretail.com/#service",
                  "name": "GEO Search Protocol — AI表示無料診断",
                  "alternateName": "Generative Engine Optimization",
                  "description": "ChatGPT・Gemini・Perplexity・ClaudeなどのAI検索エンジンにおける企業の表示状況を診断し、AI検索最適化（GEO）を支援するサービス。",
                  "url": "https://aiscan.coaretail.com",
                  "provider": {
                    "@id": "https://aiscan.coaretail.com/#organization"
                  },
                  "areaServed": {
                    "@type": "Country",
                    "name": "Japan"
                  },
                  "offers": {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "JPY",
                    "description": "AI表示診断（無料）"
                  },
                  "serviceType": "AI検索最適化（GEO）コンサルティング"
                }
              ]
            })
          }}
        />
      </head>
      <body>
        {children}
        {/* LinkedIn noscript fallback */}
        <noscript>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img height="1" width="1" style={{display:'none'}} alt="" src="https://px.ads.linkedin.com/collect/?pid=8978180&fmt=gif" />
        </noscript>
      </body>
    </html>
  )
}
