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
    openGraph: {
      title: post.title,
      description: post.description,
      type: 'article',
      publishedTime: post.date,
    },
  }
}

export default async function PostPage({ params }: Props) {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post) notFound()

  return (
    <div style={{maxWidth:'720px', margin:'0 auto', padding:'32px 20px 60px'}}>
      <div style={{fontSize:'11px', color:'#9ca3af', backgroundColor:'#f9fafb', border:'1px solid #e5e7eb', borderRadius:'4px', padding:'6px 12px', display:'inline-block', marginBottom:'20px'}}>
        PR・広告を含む記事です
      </div>

      <div style={{marginBottom:'20px'}}>
        <Link href="/" style={{fontSize:'12px', color:'#6b7280', textDecoration:'none'}}>← トップに戻る</Link>
      </div>

      <article>
        <div style={{display:'flex', alignItems:'center', gap:'8px', marginBottom:'12px'}}>
          <span style={{fontSize:'11px', fontWeight:'500', backgroundColor:'#f3f4f6', color:'#6b7280', padding:'2px 8px', borderRadius:'4px'}}>
            {post.category}
          </span>
          <time style={{fontSize:'11px', color:'#9ca3af'}}>{post.date}</time>
        </div>

        <h1 style={{fontSize:'clamp(20px, 4vw, 28px)', fontWeight:'700', color:'#111827', lineHeight:'1.4', margin:'0 0 12px 0'}}>
          {post.title}
        </h1>
        <p style={{fontSize:'13px', color:'#6b7280', lineHeight:'1.8', margin:'0 0 16px 0'}}>{post.description}</p>

        <div style={{display:'flex', flexWrap:'wrap', gap:'6px', marginBottom:'32px'}}>
          {post.tags.map((tag: string) => (
            <span key={tag} style={{fontSize:'11px', color:'#9ca3af', backgroundColor:'#f9fafb', border:'1px solid #e5e7eb', padding:'2px 8px', borderRadius:'4px'}}>
              #{tag}
            </span>
          ))}
        </div>

        <div style={{fontSize:'15px', lineHeight:'1.9', color:'#374151'}}>
          <MDXRemote source={post.content} />
        </div>
      </article>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'Article',
            headline: post.title,
            description: post.description,
            datePublished: post.date,
            keywords: post.tags.join(', '),
            publisher: { '@type': 'Organization', name: 'QOL media' },
          }),
        }}
      />
    </div>
  )
}
