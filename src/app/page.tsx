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
  const recentPosts = posts.slice(0, 10)

  return (
    <>
      <section className="bg-gradient-to-b from-gray-50 to-white pt-16 pb-12 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs tracking-widest text-gray-400 uppercase mb-5">Information site to enhance Quality Of Life</p>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-800 mb-3 leading-tight">生活の質を、もっと高く。</h1>
          <p className="text-sm text-gray-500 leading-relaxed max-w-md mx-auto">
            ペットケアから健康管理まで、あなたと大切な存在のQOLを高める情報をお届けします。
          </p>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 sm:px-6 py-10">
        <h2 className="text-xs font-semibold tracking-widest text-gray-400 uppercase mb-5">Categories</h2>
        <div className="grid grid-cols-3 gap-3 sm:gap-4">
          {CATEGORIES.map(cat => (
            <a key={cat.slug} href={"/" + cat.slug}
              className="group border border-gray-100 rounded-xl p-4 sm:p-6 hover:border-gray-300 hover:shadow-sm transition-all">
              <span className="text-2xl block mb-2">{cat.icon}</span>
              <span className="block font-bold text-sm text-gray-800 mb-1">{cat.label}</span>
              <span className="block text-xs text-gray-400 leading-relaxed hidden sm:block">{cat.desc}</span>
            </a>
          ))}
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-16">
        <h2 className="text-xs font-semibold tracking-widest text-gray-400 uppercase mb-5">Latest Articles</h2>
        {recentPosts.length === 0 ? (
          <p className="text-sm text-gray-400">記事がまだありません。</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentPosts.map(post => (
              <article key={post.slug} className="py-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{post.category}</span>
                  <time className="text-xs text-gray-400">{post.date}</time>
                </div>
                <h3 className="text-sm sm:text-base font-bold text-gray-800 mb-1 leading-snug">
                  <Link href={"/posts/" + post.slug} className="hover:text-gray-600 transition-colors">{post.title}</Link>
                </h3>
                <p className="text-xs text-gray-500 leading-relaxed">{post.description}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
