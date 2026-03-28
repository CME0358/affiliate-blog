import { getAllPosts, getPostBySlug } from '@/lib/posts'
import { MDXRemote } from 'next-mdx-remote/rsc'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import Link from 'next/link'

type Props = { params: Promise<{ slug: string }> }

export async function generateStaticParams() {
  return getAllPosts().map(p => ({ slug: p.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post) return {}
  return {
    title: post.title,
    description: post.description,
  }
}

export default async function PostPage({ params }: Props) {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post) notFound()

  return (
    <main className="max-w-3xl mx-auto px-4 py-12">
      <Link href="/" className="text-sm text-indigo-500 hover:underline mb-8 inline-block">
        ← 記事一覧に戻る
      </Link>
      <article>
        <header className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs font-medium bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
              {post.category}
            </span>
            <time className="text-xs text-gray-400">{post.date}</time>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 leading-tight mb-4">{post.title}</h1>
          <p className="text-gray-500 leading-relaxed">{post.description}</p>
        </header>
        <div className="prose prose-gray prose-lg max-w-none">
          <MDXRemote source={post.content} />
        </div>
      </article>
    </main>
  )
}
