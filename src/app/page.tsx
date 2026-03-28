import Link from 'next/link'
import { getAllPosts } from '@/lib/posts'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'My Affiliate Blog',
  description: '厳選情報をお届けするアフィリエイトブログ',
}

export default function Home() {
  const posts = getAllPosts()

  return (
    <main className="max-w-3xl mx-auto px-4 py-12">
      <header className="mb-12">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">My Affiliate Blog</h1>
        <p className="text-gray-500">厳選情報・おすすめ商品レビュー</p>
      </header>
      {posts.length === 0 ? (
        <p className="text-gray-400">記事がまだありません。</p>
      ) : (
        <div className="space-y-8">
          {posts.map(post => (
            <article key={post.slug} className="border-b border-gray-100 pb-8">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-medium bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
                  {post.category}
                </span>
                <time className="text-xs text-gray-400">{post.date}</time>
              </div>
              <h2 className="text-xl font-bold mb-2">
                <Link href={"/posts/" + post.slug} className="text-gray-900 hover:text-indigo-600 transition-colors">
                  {post.title}
                </Link>
              </h2>
              <p className="text-gray-500 text-sm leading-relaxed mb-3">{post.description}</p>
              <div className="flex flex-wrap gap-2">
                {post.tags.map(tag => (
                  <span key={tag} className="text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded">
                    #{tag}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  )
}
