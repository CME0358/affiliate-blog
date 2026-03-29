import Link from 'next/link'
import { getAllPosts, getPostImage } from '@/lib/posts'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'QOL media | Quality Of Life情報メディア',
  description: '生活の質（QOL）を高める情報をお届けするメディア。',
}

const CATEGORIES = [
  { label: 'ペット', slug: 'pet', color: '#4ade80' },
  { label: '健康', slug: 'health', color: '#818cf8' },
  { label: '暮らし', slug: 'life', color: '#fb923c' },
]

const CATEGORY_COLOR: Record<string, string> = {
  'ペット': '#4ade80',
  '健康': '#818cf8',
  '暮らし': '#fb923c',
}

export default function Home() {
  const posts = getAllPosts()
  const featured = posts[0]
  const subFeatured = posts.slice(1, 4)
  const remaining = posts.slice(4)

  return (
    <div style={{backgroundColor:'#f3f4f6', minHeight:'100vh'}}>

      {/* ヒーロー featuredカード */}
      {featured && (
        <div style={{backgroundColor:'#111'}}>
          <div style={{maxWidth:'1080px', margin:'0 auto', padding:'0 20px'}}>
            <Link href={'/posts/' + featured.slug} style={{textDecoration:'none', display:'block'}}>
              <div style={{position:'relative', overflow:'hidden'}}>
                <img
                  src={getPostImage(featured)}
                  alt={featured.title}
                  style={{width:'100%', height:'420px', objectFit:'cover', display:'block', opacity:0.65}}
                />
                <div style={{position:'absolute', inset:0, background:'linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.1) 60%, transparent 100%)'}}>
                  <div style={{position:'absolute', bottom:0, left:0, right:0, padding:'32px 36px'}}>
                    <span style={{
                      display:'inline-block',
                      backgroundColor: CATEGORY_COLOR[featured.category] || '#9ca3af',
                      color:'#000', fontSize:'11px', fontWeight:'700',
                      padding:'3px 10px', borderRadius:'2px', marginBottom:'12px',
                    }}>{featured.category}</span>
                    <h2 style={{fontSize:'clamp(18px, 2.5vw, 28px)', fontWeight:'700', color:'#fff', lineHeight:'1.4', margin:'0 0 10px'}}>
                      {featured.title}
                    </h2>
                    <p style={{fontSize:'13px', color:'rgba(255,255,255,0.7)', lineHeight:'1.7', margin:0, maxWidth:'600px'}}>
                      {featured.description}
                    </p>
                  </div>
                </div>
              </div>
            </Link>
          </div>
        </div>
      )}

      {/* サブフィーチャー 3枚 */}
      <div style={{backgroundColor:'#111', paddingBottom:'20px'}}>
        <div style={{maxWidth:'1080px', margin:'0 auto', padding:'0 20px'}}>
          <div style={{display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:'3px', marginTop:'3px'}}>
            {subFeatured.map(post => (
              <Link key={post.slug} href={'/posts/' + post.slug} style={{textDecoration:'none', display:'block'}}>
                <div style={{position:'relative', overflow:'hidden'}}>
                  <img
                    src={getPostImage(post)}
                    alt={post.title}
                    style={{width:'100%', height:'180px', objectFit:'cover', display:'block', opacity:0.6}}
                  />
                  <div style={{position:'absolute', inset:0, background:'linear-gradient(to top, rgba(0,0,0,0.88) 0%, transparent 65%)'}}>
                    <div style={{position:'absolute', bottom:0, left:0, right:0, padding:'14px'}}>
                      <span style={{
                        display:'inline-block',
                        backgroundColor: CATEGORY_COLOR[post.category] || '#9ca3af',
                        color:'#000', fontSize:'10px', fontWeight:'700',
                        padding:'2px 7px', borderRadius:'2px', marginBottom:'6px',
                      }}>{post.category}</span>
                      <p style={{fontSize:'12px', fontWeight:'600', color:'#fff', lineHeight:'1.4', margin:0}}>
                        {post.title}
                      </p>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* カテゴリタブ */}
      <div style={{backgroundColor:'#fff', borderBottom:'1px solid #e5e7eb'}}>
        <div style={{maxWidth:'1080px', margin:'0 auto', padding:'0 20px', display:'flex', overflowX:'auto'}}>
          <a href="/" style={{padding:'12px 16px', fontSize:'12px', fontWeight:'700', color:'#111', textDecoration:'none', borderBottom:'2px solid #111', whiteSpace:'nowrap'}}>
            すべて
          </a>
          {CATEGORIES.map(cat => (
            <a key={cat.slug} href={'/' + cat.slug} style={{
              display:'flex', alignItems:'center', gap:'5px',
              padding:'12px 16px', fontSize:'12px', fontWeight:'600',
              color:'#6b7280', textDecoration:'none',
              borderBottom:'2px solid transparent', whiteSpace:'nowrap',
            }}>
              <span style={{width:'7px', height:'7px', borderRadius:'50%', backgroundColor:cat.color, display:'inline-block'}}></span>
              {cat.label}
            </a>
          ))}
        </div>
      </div>

      {/* 記事グリッド */}
      <div style={{maxWidth:'1080px', margin:'0 auto', padding:'28px 20px 60px'}}>
        <div style={{display:'flex', alignItems:'center', marginBottom:'16px'}}>
          <h2 style={{fontSize:'12px', fontWeight:'700', color:'#6b7280', letterSpacing:'0.12em', textTransform:'uppercase', margin:0}}>
            All Articles <span style={{color:'#9ca3af', fontWeight:'400'}}>— {posts.length}件</span>
          </h2>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px, 1fr))', gap:'16px'}}>
          {remaining.map(post => (
            <Link key={post.slug} href={'/posts/' + post.slug} style={{textDecoration:'none', display:'block'}}>
              <article style={{backgroundColor:'#fff', borderRadius:'6px', overflow:'hidden', border:'1px solid #e5e7eb'}}>
                <div style={{position:'relative'}}>
                  <img
                    src={getPostImage(post)}
                    alt={post.title}
                    style={{width:'100%', height:'150px', objectFit:'cover', display:'block'}}
                  />
                  <span style={{
                    position:'absolute', top:'8px', left:'8px',
                    backgroundColor: CATEGORY_COLOR[post.category] || '#9ca3af',
                    color:'#000', fontSize:'10px', fontWeight:'700',
                    padding:'2px 7px', borderRadius:'2px',
                  }}>{post.category}</span>
                </div>
                <div style={{padding:'14px'}}>
                  <h3 style={{fontSize:'13px', fontWeight:'700', color:'#111827', lineHeight:'1.5', margin:'0 0 8px'}}>
                    {post.title}
                  </h3>
                  <p style={{
                    fontSize:'12px', color:'#6b7280', lineHeight:'1.6', margin:'0 0 10px',
                    display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden',
                  } as React.CSSProperties}>
                    {post.description}
                  </p>
                  <time style={{fontSize:'11px', color:'#9ca3af'}}>{post.date}</time>
                </div>
              </article>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
