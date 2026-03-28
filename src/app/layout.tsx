import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'My Affiliate Blog', template: '%s | My Affiliate Blog' },
  description: '厳選情報・おすすめ商品レビュー',
  robots: { index: true, follow: true },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-white text-gray-900 antialiased">
        <nav className="border-b border-gray-100">
          <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
            <a href="/" className="font-bold text-gray-900 hover:text-indigo-600 transition-colors">
              My Affiliate Blog
            </a>
            <div className="text-xs text-gray-400">おすすめ情報まとめ</div>
          </div>
        </nav>
        {children}
        <footer className="border-t border-gray-100 mt-20">
          <div className="max-w-3xl mx-auto px-4 py-8 text-center text-xs text-gray-400">
            <p>当サイトはアフィリエイト広告を含みます。</p>
          </div>
        </footer>
      </body>
    </html>
  )
}
