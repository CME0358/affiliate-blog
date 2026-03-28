import Link from 'next/link'
import { getAllPosts } from '@/lib/posts'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'QOL media | Quality Of Life情報メディア',
  description: '生活の質（QOL）を高める情報をお届けするメディア。',
}

const CATEGORIES = [
  { label: 'ペット', slug: 'pet', desc: 'フィラリア予防・ノミダニ対策・ペット医薬品', icon: '🐾' },
  { label: '健康', slug: 'health', desc: 'セルフケア・サプリ・予防医学', icon: '💊' },
  { label: '暮らし', slug: 'life', desc: '食・住・日常を豊かにするヒント', icon: '🏡' },
]

export default function Home() {
  const posts = getAllPosts()
  const recentPosts = posts.slice(0, 6)

  return (
    <main>
      <section className="bg-gradient-to-b from-gray-50 to-white py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-medium tracking-widest text-gray-400 uppercase mb-4">Information site to enhance Quality Of Life</p>
          <h1 className="text-3xl font-bold text-gray-800 mb-4 leading-tight">生活の質を、もっと高く。</h1>
          <p className="text-gray-500 text-sm leading-relaxed max-w-xl mx-auto">
            ペットケアから健康管理まで、あなたと大切な存在のQOLを高める情報をお届けします。
          </p>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-12">
        <h2 className="text-xs font-medium tracking-widest text-gray-400 uppercase mb-6">Categories</h2>
        <div className="grid grid-cols-3 gap-4">
          {CATEGORIES.map(cat => (
            <a key={cat.slug} href={"/" + cat.slug}
              className="border border-gray-100 rounded-xl p-6 hover:border-gray-300 hover:shadow-sm transition-all group">
              <div className="text-2xl mb-3">{cat.icon}</div>
              <div className="font-bold text-gray-800 mb-1 group-hover:text-gray-900">{cat.label}</div>
              <div className="text-xs text-gray-400 leading-relaxed">{cat.desc}</div>
            </a>
          ))}
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-6 py-12">
        <h2 className="text-xs font-medium tracking-widest text-gray-400 uppercase mb-6">Latest Articles</h2>
        {recentPosts.length === 0 ? (
          <p className="text-gray-400 text-sm">記事がまだありません。</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentPosts.map(post => (
              <article key={post.slug} className="py-6">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                    {post.category}
                  </span>
                  <time className="text-xs text-gray-400">{post.date}</time>
                </div>
                <h3 className="font-bold text-gray-800 mb-1 leading-snug">
                  <Link href={"/posts/" + post.slug} className="hover:text-gray-600 transition-colors">
                    {post.title}
                  </Link>
                </h3>
                <p className="text-xs text-gray-500 leading-relaxed">{post.description}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
