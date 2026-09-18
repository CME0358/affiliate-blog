import { getAllPosts, getPostBySlug, getPostImage } from '@/lib/posts'
import { MDXRemote } from 'next-mdx-remote/rsc'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import Link from 'next/link'
import remarkGfm from 'remark-gfm'
import { SITE_NAME, SITE_URL } from '@/lib/site'

type Props = { params: Promise<{ slug: string }> }

const CATEGORY_SLUG: Record<string, string> = {
  'ペット': 'pet',
  '健康': 'health',
  '睡眠': 'sleep',
  '暮らし': 'life',
}

export async function generateStaticParams() {
  return getAllPosts().map(p => ({ slug: p.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post) return {}
  const modified = post.updated || post.date
  return {
    title: post.title,
    description: post.description,
    alternates: {
      canonical: `/posts/${post.slug}`,
    },
    robots: { index: true, follow: true },
    openGraph: {
      title: post.title,
      description: post.description,
      type: 'article',
      publishedTime: post.date,
      modifiedTime: modified,
      url: `/posts/${post.slug}`,
      siteName: SITE_NAME,
      locale: 'ja_JP',
      images: [{ url: getPostImage(post), alt: post.title }],
    },
    twitter: {
      card: 'summary_large_image',
      title: post.title,
      description: post.description,
      images: [getPostImage(post)],
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
  aside: (props: React.HTMLAttributes<HTMLElement>) => (
    <aside
      {...props}
      style={{
        backgroundColor:'#f5f3ff',
        borderLeft:'4px solid #7c3aed',
        margin:'8px 0 24px',
        padding:'14px 16px',
        borderRadius:'0 8px 8px 0',
        color:'#1f2937',
        lineHeight:1.8,
      }}
    />
  ),
}

export default async function PostPage({ params }: Props) {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post) notFound()
  const categorySlug = CATEGORY_SLUG[post.category] || 'life'
  const modified = post.updated || post.date
  const canonical = `${SITE_URL}/posts/${post.slug}`

  return (
    <div style={{maxWidth:'720px', margin:'0 auto', padding:'32px 20px 60px'}}>
      <div style={{fontSize:'11px', color:'#9ca3af', backgroundColor:'#f9fafb', border:'1px solid #e5e7eb', borderRadius:'4px', padding:'6px 12px', display:'inline-block', marginBottom:'20px'}}>
        PR・広告を含む記事です
      </div>

      <div style={{marginBottom:'20px', fontSize:'12px', color:'#6b7280'}}>
        <Link href="/" style={{color:'#6b7280', textDecoration:'none'}}>トップ</Link>
        {' / '}
        <Link href={`/${categorySlug}`} style={{color:'#6b7280', textDecoration:'none'}}>{post.category}</Link>
      </div>

      <article>
        <div style={{display:'flex', alignItems:'center', gap:'8px', marginBottom:'12px'}}>
          <span style={{fontSize:'11px', fontWeight:'500', backgroundColor:'#f3f4f6', color:'#6b7280', padding:'2px 8px', borderRadius:'4px'}}>
            {post.category}
          </span>
          <time dateTime={post.date} style={{fontSize:'11px', color:'#9ca3af'}}>{post.date}</time>
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

        {post.faq && post.faq.length > 0 && (
          <section style={{marginTop:'40px'}}>
            <h2 style={{fontSize:'20px', fontWeight:700, color:'#111827', margin:'0 0 16px', paddingBottom:'8px', borderBottom:'2px solid #f3f4f6'}}>
              よくある質問
            </h2>
            <div style={{display:'flex', flexDirection:'column', gap:'12px'}}>
              {post.faq.map(item => (
                <div key={item.q} style={{backgroundColor:'#f9fafb', border:'1px solid #e5e7eb', borderRadius:'8px', padding:'16px 18px'}}>
                  <h3 style={{fontSize:'15px', fontWeight:700, color:'#111827', margin:'0 0 8px', lineHeight:1.6}}>
                    {item.q}
                  </h3>
                  <p style={{fontSize:'14px', color:'#374151', lineHeight:1.8, margin:0}}>
                    {item.a}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}
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
            dateModified: modified,
            url: canonical,
            inLanguage: 'ja-JP',
            mainEntityOfPage: {
              '@type': 'WebPage',
              '@id': canonical,
            },
            image: [`${SITE_URL}${getPostImage(post)}`],
            keywords: post.tags.join(', '),
            author: { '@type': 'Organization', name: SITE_NAME, url: `${SITE_URL}/about` },
            publisher: {
              '@type': 'Organization',
              name: SITE_NAME,
              url: SITE_URL,
              logo: { '@type': 'ImageObject', url: `${SITE_URL}/QOL_logo_transparent.png` },
            },
          }),
        }}
      />
      {post.faq && post.faq.length > 0 && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@type': 'FAQPage',
              mainEntity: post.faq.map(item => ({
                '@type': 'Question',
                name: item.q,
                acceptedAnswer: { '@type': 'Answer', text: item.a },
              })),
            }),
          }}
        />
      )}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'BreadcrumbList',
            itemListElement: [
              { '@type': 'ListItem', position: 1, name: SITE_NAME, item: `${SITE_URL}/` },
              { '@type': 'ListItem', position: 2, name: post.category, item: `${SITE_URL}/${categorySlug}` },
              { '@type': 'ListItem', position: 3, name: post.title, item: canonical },
            ],
          }),
        }}
      />
    </div>
  )
}
