import Link from 'next/link'
import { getAllPosts, getPostImage } from '@/lib/posts'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'

type Props = { params: Promise<{ category: string }> }

const SLUG_TO_LABEL: Record<string, string> = {
  pet:    'ペット',
  health: '健康',
  life:   '暮らし',
  sleep:  '睡眠',
}

const CATEGORY_COLOR: Record<string, string> = {
  'ペット': '#16a34a',
  '健康':   '#7c3aed',
  '暮らし': '#ea580c',
  '睡眠':   '#2563eb',
}

const CATEGORY_BG: Record<string, string> = {
  'ペット': '#dcfce7',
  '健康':   '#ede9fe',
  '暮らし': '#ffedd5',
  '睡眠':   '#dbeafe',
}

const CATEGORY_FV: Record<string, string> = {
  'ペット': '/fv-pet.jpg',
  '健康':   '/fv-health.jpg',
  '暮らし': '/fv-life.jpg',
  '睡眠':   '/fv-sleep.jpg',
}

export async function generateStaticParams() {
  return Object.keys(SLUG_TO_LABEL).map(category => ({ category }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { category } = await params
  const label = SLUG_TO_LABEL[category]
  if (!label) return {}
  return {
    title: `${label}の記事一覧 | QOL media`,
    description: `QOL mediaの${label}カテゴリ記事一覧です。`,
  }
}

export default async function CategoryPage({ params }: Props) {
  const { category } = await params
  const label = SLUG_TO_LABEL[category]
  if (!label) notFound()

  const posts = getAllPosts().filter(p => p.category === label)
  const color = CATEGORY_COLOR[label] || '#6b7280'
  const bg    = CATEGORY_BG[label]    || '#f3f4f6'

  const CATEGORIES = [
    { label: 'ペット', slug: 'pet',    color: '#16a34a' },
    { label: '健康',   slug: 'health', color: '#7c3aed' },
    { label: '暮らし', slug: 'life',   color: '#ea580c' },
    { label: '睡眠',   slug: 'sleep',  color: '#2563eb' },
  ]

  const fvImage = CATEGORY_FV[label] || '/fv-hero.png'

  return (
    <div style={{ backgroundColor: '#f3f4f6', minHeight: '100vh' }}>

      {/* カテゴリFV */}
      <div style={{ backgroundColor: '#f8fafc' }}>
        <div style={{ maxWidth: '1080px', margin: '0 auto', padding: '0 20px' }}>
          <img
            src={fvImage}
            alt={label}
            className="fv-pc"
            style={{ width: '100%', height: '420px', objectFit: 'cover', display: 'block', borderRadius: '0 0 4px 4px' }}
          />
          <img
            src={fvImage}
            alt={label}
            className="fv-mobile"
            style={{ width: '100%', height: '260px', objectFit: 'cover', display: 'none', borderRadius: '0 0 4px 4px' }}
          />
        </div>
      </div>

      {/* カテゴリタブ */}
      <div style={{ backgroundColor: '#fff', borderBottom: '1px solid #e5e7eb', borderTop: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: '1080px', margin: '0 auto', padding: '0 20px', display: 'flex', overflowX: 'auto' }}>
          <a href="/" style={{
            padding: '12px 16px', fontSize: '12px', fontWeight: '700',
            color: '#6b7280', textDecoration: 'none',
            borderBottom: '2px solid transparent', whiteSpace: 'nowrap',
          }}>
            すべて
          </a>
          {CATEGORIES.map(cat => (
            <a key={cat.slug} href={'/' + cat.slug} style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '12px 16px', fontSize: '12px', fontWeight: '600',
              color: cat.slug === category ? '#111' : '#6b7280',
              textDecoration: 'none',
              borderBottom: cat.slug === category ? `2px solid ${cat.color}` : '2px solid transparent',
              whiteSpace: 'nowrap',
            }}>
              <span style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: cat.color, display: 'inline-block' }} />
              {cat.label}
            </a>
          ))}
        </div>
      </div>

      {/* 記事グリッド */}
      <div style={{ maxWidth: '1080px', margin: '0 auto', padding: '28px 20px 60px' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
          <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: color, display: 'inline-block', marginRight: '8px' }} />
          <h2 style={{ fontSize: '12px', fontWeight: '700', color: '#6b7280', letterSpacing: '0.12em', textTransform: 'uppercase', margin: 0 }}>
            {label} <span style={{ color: '#9ca3af', fontWeight: '400' }}>— {posts.length}件</span>
          </h2>
        </div>

        {posts.length === 0 ? (
          <p style={{ color: '#9ca3af', fontSize: '14px' }}>記事がまだありません。</p>
        ) : (
          <div className="article-grid">
            {posts.map(post => (
              <Link key={post.slug} href={'/posts/' + post.slug} style={{ textDecoration: 'none', display: 'block' }}>
                <article className="article-card" style={{ backgroundColor: '#fff', borderRadius: '6px', overflow: 'hidden', border: '1px solid #e5e7eb' }}>
                  <div style={{ position: 'relative' }}>
                    <img
                      src={getPostImage(post)}
                      alt={post.title}
                      style={{ width: '100%', height: '150px', objectFit: 'cover', display: 'block' }}
                    />
                    <span style={{
                      position: 'absolute', top: '8px', left: '8px',
                      backgroundColor: bg,
                      color: color,
                      fontSize: '10px', fontWeight: '700',
                      padding: '2px 8px', borderRadius: '2px',
                    }}>{post.category}</span>
                  </div>
                  <div style={{ padding: '14px' }}>
                    <h3 style={{ fontSize: '13px', fontWeight: '700', color: '#111827', lineHeight: '1.5', margin: '0 0 8px' }}>
                      {post.title}
                    </h3>
                    <p style={{
                      fontSize: '12px', color: '#6b7280', lineHeight: '1.6', margin: '0 0 10px',
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    } as React.CSSProperties}>
                      {post.description}
                    </p>
                    <time style={{ fontSize: '11px', color: '#9ca3af' }}>{post.date}</time>
                  </div>
                </article>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
