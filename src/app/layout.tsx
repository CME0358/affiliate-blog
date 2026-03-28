import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'QOL media | Quality Of Life情報メディア', template: '%s | QOL media' },
  description: '生活の質（QOL）を高める情報をお届けするメディア。',
  robots: { index: true, follow: true },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-white text-gray-800 antialiased min-h-screen flex flex-col">
        <header className="border-b border-gray-100 bg-white sticky top-0 z-50">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
            <a href="/">
              <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'28px',width:'auto',maxWidth:'160px'}} />
            </a>
            <nav className="flex items-center gap-4 sm:gap-6">
              <a href="/pet" className="text-xs sm:text-sm text-gray-500 hover:text-gray-900 transition-colors">ペット</a>
              <a href="/health" className="text-xs sm:text-sm text-gray-500 hover:text-gray-900 transition-colors">健康</a>
              <a href="/life" className="text-xs sm:text-sm text-gray-500 hover:text-gray-900 transition-colors">暮らし</a>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-gray-100 bg-gray-50 mt-16">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 py-10">
            <div className="flex flex-col items-center gap-3">
              <img src="/QOL_logo_transparent.png" alt="QOL media" style={{height:'20px',width:'auto',maxWidth:'120px',opacity:0.35}} />
              <p className="text-xs text-gray-400 text-center leading-relaxed">
                当サイトはアフィリエイト広告を含みます。<br />
                掲載情報は記事公開時点のものです。最新情報は各公式サイトをご確認ください。
              </p>
              <div className="flex gap-5 text-xs text-gray-400">
                <a href="/privacy" className="hover:text-gray-600">プライバシーポリシー</a>
                <a href="/about" className="hover:text-gray-600">運営について</a>
                <a href="/contact" className="hover:text-gray-600">お問い合わせ</a>
              </div>
              <p className="text-xs text-gray-300">© 2026 QOL media</p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  )
}
