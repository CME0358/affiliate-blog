import { getAllPosts, getPostBySlug } from '@/lib/posts'
import { MDXRemote } from 'next-mdx-remote/rsc'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import Link from 'next/link'
import remarkGfm from 'remark-gfm'

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

const mdxComponents = {
  table: (props: React.HTMLAttributes<HTMLTableElement>) => (
    <div style={{overflowX:'auto', margin:'24px 0', borderRadius:'8px', border:'1px solid #e5e7eb'}}>
      <table {...props} style={{width:'100%', borderCollapse:'collapse', fontSize:'14px', lineHeight:'1.6'}} />
    </div>
  ),
  thead: (props: React.HTMLAttributes<HTMLTableSectionElement>) => (
    <thead {...props} style={{backgroundColor:'#f3f4f6'}} />
  ),
  th: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th {...props} style={{padding:'12px 16px', textAlign:'left', fontWeight:'600', color:'#374151', borderBottom:'2px solid #e5e7eb', whiteSpace:'nowrap'}} />
  ),
  td: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td {...props} style={{padding:'12px 16px', borderBottom:'1px solid #f3f4f6', color:'#374151', verticalAlign:'top'}} />
  ),
  tr: (props: React.HTMLAttributes<HTMLTableRowElement>) => (
    <tr {...props} />
  ),
  h2: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 {...props} style={{fontSize:'20px', fontWeight:'700', color:'#111827', margin:'40px 0 16px', paddingBottom:'8px', borderBottom:'2px solid #f3f4f6'}} />
  ),
  h3: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 {...props} style={{fontSize:'17px', fontWeight:'700', color:'#1f2937', margin:'28px 0 12px'}} />
  ),
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p {...props} style={{margin:'0 0 16px', lineHeight:'1.9', color:'#374151'}} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul {...props} style={{margin:'0 0 16px', paddingLeft:'24px', lineHeight:'1.9', color:'#374151'}} />
  ),
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => (
    <ol {...props} style={{margin:'0 0 16px', paddingLeft:'24px', lineHeight:'1.9', color:'#374151'}} />
  ),
  li: (props: React.HTMLAttributes<HTMLLIElement>) => (
    <li {...props} style={{marginBottom:'6px'}} />
  ),
  strong: (props: React.HTMLAttributes<HTMLElement>) => (
    <strong {...props} style={{fontWeight:'700', color:'#111827'}} />
  ),
  a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      {...props}
      style={{color:'#2563eb', textDecoration:'underline', textUnderlineOffset:'2px'}}
      target={props.href?.startsWith('http') ? '_blank' : undefined}
      rel={props.href?.startsWith('http') ? 'noopener noreferrer' : undefined}
    />
  ),
  blockquote: (props: React.HTMLAttributes<HTMLQuoteElement>) => (
    <blockquote {...props} style={{borderLeft:'4px solid #e5e7eb', margin:'20px 0', padding:'12px 20px', backgroundColor:'#f9fafb', color:'#6b7280', borderRadius:'0 8px 8px 0'}} />
  ),
  code: (props: React.HTMLAttributes<HTMLElement>) => (
    <code {...props} style={{backgroundColor:'#f3f4f6', padding:'2px 6px', borderRadius:'4px', fontSize:'13px', color:'#374151'}} />
  ),
  hr: () => (
    <hr style={{border:'none', borderTop:'1px solid #f3f4f6', margin:'32px 0'}} />
  ),
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
          <MDXRemote
            source={post.content}
            components={mdxComponents}
            options={{ mdxOptions: { remarkPlugins: [remarkGfm] } }}
          />
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
