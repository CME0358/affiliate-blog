import Link from 'next/link'
import { getAllPosts, getPostImage } from '@/lib/posts'
import { HC_CLUSTER_POSTS, PET_CLUSTER_POSTS } from '@/lib/site'
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

const CATEGORY_META: Record<string, { title: string; description: string }> = {
  pet: {
    title: 'ペットケアの記事一覧｜フィラリア・ノミダニ薬の比較',
    description: 'フィラリア薬・ノミダニ薬の通販比較、個人輸入の注意、正規品の確認など犬・猫のケア記事一覧。ハブは pet-lp。効能は断定せず、獣医師への相談を前提にします。',
  },
  health: {
    title: '健康・AGA費用比較の記事一覧',
    description: 'AGA治療の費用比較（初月料金、オンライン診療、カウンセリングで聞くこと、薬と植毛の単位）など、健康カテゴリの記事一覧。料金や効果は断定しません。',
  },
  life: {
    title: '暮らしの記事一覧',
    description: '暮らしと資金繰りに役立つ比較・解説記事の一覧です。',
  },
  sleep: {
    title: '睡眠の記事一覧｜寝つき・中途覚醒の比較',
    description: '寝つき・夜中に目が覚める・朝のだるさなど、睡眠の対策と比較記事の一覧。サプリ・枕・マットレスの選び方は睡眠ガイドへ。料金や効能は断定しません。',
  },
}

export async function generateStaticParams() {
  return Object.keys(SLUG_TO_LABEL).map(category => ({ category }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { category } = await params
  const label = SLUG_TO_LABEL[category]
  if (!label) return {}
  const meta = CATEGORY_META[category]
  return {
    title: meta?.title ?? `${label}の記事一覧`,
    description: meta?.description ?? `QOL mediaの${label}カテゴリ記事一覧です。`,
    alternates: { canonical: `/${category}` },
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
          <h1 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', letterSpacing: '0.04em', margin: 0 }}>
            {label} <span style={{ color: '#9ca3af', fontWeight: '400' }}>— {posts.length}件</span>
          </h1>
        </div>

        {category === 'pet' && (
          <div style={{ marginBottom: '20px' }}>
            <a
              href="/pet-lp.html"
              style={{
                display: 'block',
                marginBottom: '12px',
                padding: '14px 16px',
                backgroundColor: '#dcfce7',
                border: '2px solid #16a34a',
                borderRadius: '8px',
                textDecoration: 'none',
              }}
            >
              <strong style={{ display: 'block', fontSize: '14px', color: '#166534', marginBottom: '4px' }}>
                フィラリア薬の通販比較ガイド
              </strong>
              <span style={{ fontSize: '12px', color: '#6b7280', lineHeight: 1.6 }}>
                動物病院との価格差、個人輸入の注意、正規品と副作用の確認。ペットカテゴリの第一導線です。料金・効能は断定しません。
              </span>
            </a>
            <p style={{ fontSize: '11px', fontWeight: 700, color: '#6b7280', letterSpacing: '0.08em', margin: '0 0 8px' }}>
              フィラリア・ノミダニの関連記事
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {PET_CLUSTER_POSTS.map(item => (
                <Link
                  key={item.slug}
                  href={'/posts/' + item.slug}
                  className="cluster-row"
                  style={{
                    padding: '10px 12px',
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    textDecoration: 'none',
                  }}
                >
                  <span className="cluster-label" style={{ fontSize: '13px', fontWeight: 600, color: '#111827' }}>{item.label}</span>
                  <span className="cluster-hint" style={{ fontSize: '12px', color: '#6b7280' }}>{item.hint}</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {category === 'health' && (
          <div style={{ marginBottom: '20px' }}>
            <a
              href="/hc-guide.html"
              style={{
                display: 'block',
                marginBottom: '12px',
                padding: '14px 16px',
                backgroundColor: '#f5f3ff',
                border: '2px solid #7c3aed',
                borderRadius: '8px',
                textDecoration: 'none',
              }}
            >
              <strong style={{ display: 'block', fontSize: '14px', color: '#5b21b6', marginBottom: '4px' }}>
                AGA治療の費用比較ガイド
              </strong>
              <span style={{ fontSize: '12px', color: '#6b7280', lineHeight: 1.6 }}>
                初月キャンペーンと総額の見方を整理し、無料カウンセリングで確認する流れをまとめています。健康カテゴリの第一導線です。
              </span>
            </a>
            <p style={{ fontSize: '11px', fontWeight: 700, color: '#6b7280', letterSpacing: '0.08em', margin: '0 0 8px' }}>
              AGA費用の関連記事
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {HC_CLUSTER_POSTS.map(item => (
                <Link
                  key={item.slug}
                  href={'/posts/' + item.slug}
                  className="cluster-row"
                  style={{
                    padding: '10px 12px',
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    textDecoration: 'none',
                  }}
                >
                  <span className="cluster-label" style={{ fontSize: '13px', fontWeight: 600, color: '#111827' }}>{item.label}</span>
                  <span className="cluster-hint" style={{ fontSize: '12px', color: '#6b7280' }}>{item.hint}</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {category === 'sleep' && (
          <div style={{ marginBottom: '20px' }}>
            <a
              href="/sleep-guide.html"
              style={{
                display: 'block',
                marginBottom: '12px',
                padding: '14px 16px',
                backgroundColor: '#eff6ff',
                border: '1px solid #bfdbfe',
                borderRadius: '8px',
                textDecoration: 'none',
              }}
            >
              <strong style={{ display: 'block', fontSize: '14px', color: '#1d4ed8', marginBottom: '4px' }}>
                寝つき・中途覚醒の対策比較ガイド
              </strong>
              <span style={{ fontSize: '12px', color: '#6b7280', lineHeight: 1.6 }}>
                サプリ・枕・マットレスの選び方と受診目安を整理。比較ランキング記事と悩み別の確認導線があります。料金・効能は断定しません。
              </span>
            </a>
            <Link
              href="/posts/suimin-supplement-ranking-2026"
              style={{
                display: 'block',
                padding: '10px 12px',
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                textDecoration: 'none',
              }}
            >
              <strong style={{ display: 'block', fontSize: '13px', color: '#111827', marginBottom: '2px' }}>
                睡眠サプリ比較ランキング2026
              </strong>
              <span style={{ fontSize: '12px', color: '#6b7280' }}>
                成分比較の読み方。詳細の悩み別導線は睡眠ガイドへ。
              </span>
            </Link>
          </div>
        )}

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
