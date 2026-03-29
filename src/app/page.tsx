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

  return (
    <div>
      {/* Hero */}
      <div style={{background:'linear-gradient(to bottom, #f9fafb, #fff)', padding:'60px 20px 40px'}}>
        <div style={{maxWidth:'960px', margin:'0 auto', textAlign:'center'}}>
          <p style={{fontSize:'11px', letterSpacing:'0.15em', color:'#9ca3af', textTransform:'uppercase', marginBottom:'16px', margin:'0 0 16px 0'}}>
            Information site to enhance Quality Of Life
          </p>
          <h1 style={{fontSize:'clamp(24px, 5vw, 36px)', fontWeight:'700', color:'#111827', margin:'0 0 12px 0', lineHeight:'1.3'}}>
            生活の質を、もっと高く。
          </h1>
          <p style={{fontSize:'14px', color:'#6b7280', lineHeight:'1.8', maxWidth:'480px', margin:'0 auto'}}>
            ペットケアから健康管理まで、あなたと大切な存在のQOLを高める情報をお届けします。
          </p>
        </div>
      </div>

      {/* カテゴリ */}
      <div style={{maxWidth:'960px', margin:'0 auto', padding:'40px 20px 20px'}}>
        <p style={{fontSize:'11px', fontWeight:'600', letterSpacing:'0.12em', color:'#9ca3af', textTransform:'uppercase', margin:'0 0 16px 0'}}>
          Categories
        </p>
        <div style={{display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:'12px'}}>
          {CATEGORIES.map(cat => (
            <a key={cat.slug} href={'/' + cat.slug}
              style={{display:'block', border:'1px solid #e5e7eb', borderRadius:'12px', padding:'20px 16px', textDecoration:'none'}}>
              <span style={{fontSize:'24px', display:'block', marginBottom:'8px'}}>{cat.icon}</span>
              <span style={{display:'block', fontWeight:'700', fontSize:'14px', color:'#111827', marginBottom:'4px'}}>{cat.label}</span>
              <span style={{display:'block', fontSize:'11px', color:'#9ca3af', lineHeight:'1.6'}}>{cat.desc}</span>
            </a>
          ))}
        </div>
      </div>

      {/* 記事一覧 全件 */}
      <div style={{maxWidth:'960px', margin:'0 auto', padding:'20px 20px 60px'}}>
        <p style={{fontSize:'11px', fontWeight:'600', letterSpacing:'0.12em', color:'#9ca3af', textTransform:'uppercase', margin:'0 0 16px 0'}}>
          Articles ({posts.length})
        </p>
        {posts.length === 0 ? (
          <p style={{fontSize:'14px', color:'#9ca3af'}}>記事がまだありません。</p>
        ) : (
          <div>
            {posts.map(post => (
              <div key={post.slug} style={{borderBottom:'1px solid #f3f4f6', padding:'20px 0'}}>
                <div style={{display:'flex', alignItems:'center', gap:'8px', marginBottom:'8px'}}>
                  <span style={{fontSize:'11px', fontWeight:'500', backgroundColor:'#f3f4f6', color:'#6b7280', padding:'2px 8px', borderRadius:'4px'}}>
                    {post.category}
                  </span>
                  <time style={{fontSize:'11px', color:'#9ca3af'}}>{post.date}</time>
                </div>
                <h2 style={{fontSize:'15px', fontWeight:'700', color:'#111827', margin:'0 0 6px 0', lineHeight:'1.5'}}>
                  <Link href={'/posts/' + post.slug} style={{color:'#111827', textDecoration:'none'}}>
                    {post.title}
                  </Link>
                </h2>
                <p style={{fontSize:'12px', color:'#6b7280', lineHeight:'1.7', margin:0}}>{post.description}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
