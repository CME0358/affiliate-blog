import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'QOL media | Quality Of Life情報メディア', template: '%s | QOL media' },
  description: '生活の質（QOL）を高める情報をお届けするメディア。ペットケア・健康・暮らしのヒントを専門家視点でわかりやすく解説します。',
  robots: { index: true, follow: true },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-white text-gray-800 antialiased">
        <header className="border-b border-gray-100 bg-white sticky top-0 z-50">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
            <a href="/">
              <img src="/QOL_logo_transparent.png" alt="QOL media" className="h-8 w-auto" />
            </a>
            <nav className="flex items-center gap-6 text-sm text-gray-500">
              <a href="/pet" className="hover:text-gray-800 transition-colors">ペット</a>
              <a href="/health" className="hover:text-gray-800 transition-colors">健康</a>
              <a href="/life" className="hover:text-gray-800 transition-colors">暮らし</a>
            </nav>
          </div>
        </header>
        {children}
        <footer className="border-t border-gray-100 mt-24 bg-gray-50">
          <div className="max-w-4xl mx-auto px-6 py-12">
            <div className="flex flex-col items-center gap-4">
              <img src="/QOL_logo_transparent.png" alt="QOL media" className="h-7 w-auto opacity-40" />
              <p className="text-xs text-gray-400 text-center leading-relaxed">
                当サイトはアフィリエイト広告を含みます。<br />
                掲載情報は記事公開時点のものです。最新情報は各公式サイトをご確認ください。
              </p>
              <div className="flex gap-6 text-xs text-gray-400">
                <a href="/privacy" className="hover:text-gray-600">プライバシーポリシー</a>
                <a href="/about" className="hover:text-gray-600">運営について</a>
                <a href="/contact" className="hover:text-gray-600">お問い合わせ</a>
              </div>
              <p className="text-xs text-gray-300">© 2025 QOL media</p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  )
}
