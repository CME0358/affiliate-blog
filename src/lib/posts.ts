import fs from 'fs'
import path from 'path'
import matter from 'gray-matter'

const postsDir = path.join(process.cwd(), 'content/posts')

export type Post = {
  slug: string
  title: string
  date: string
  description: string
  category: string
  tags: string[]
  image?: string        // 個別指定画像
  pickupImage?: string  // ピックアップ用個別画像
  content: string
}

// FVヒーロー用画像（1枚目固定）
export const FV_IMAGE = '/fv-hero.svg'

// ピックアップ用デフォルト画像（2〜4枚目）
export const PICKUP_DEFAULT_IMAGE = '/pickup-default.svg'

// カテゴリ別デフォルト画像（記事カード用）
export function getCategoryImage(category: string): string {
  const map: Record<string, string> = {
    'ペット': '/og-pet.svg',
    '健康': '/og-health.svg',
    '暮らし': '/og-life.svg',
  }
  return map[category] || '/og-default.svg'
}

// 記事カード用画像（個別指定 → カテゴリ別）
export function getPostImage(post: Post): string {
  return post.image || getCategoryImage(post.category)
}

// ピックアップ用画像（個別指定 → ピックアップデフォルト）
export function getPickupImage(post: Post): string {
  return post.pickupImage || post.image || PICKUP_DEFAULT_IMAGE
}

export function getAllPosts(): Post[] {
  if (!fs.existsSync(postsDir)) return []
  const files = fs.readdirSync(postsDir).filter(f => f.endsWith('.md'))
  return files
    .map(file => {
      const slug = file.replace(/\.md$/, '')
      const raw = fs.readFileSync(path.join(postsDir, file), 'utf-8')
      const { data, content } = matter(raw)
      return {
        slug,
        title: data.title || '',
        date: data.date || '',
        description: data.description || '',
        category: data.category || '未分類',
        tags: data.tags || [],
        image: data.image || '',
        pickupImage: data.pickupImage || '',
        content,
      }
    })
    .sort((a, b) => (a.date < b.date ? 1 : -1))
}

export function getPostBySlug(slug: string): Post | null {
  const filePath = path.join(postsDir, `${slug}.md`)
  if (!fs.existsSync(filePath)) return null
  const raw = fs.readFileSync(filePath, 'utf-8')
  const { data, content } = matter(raw)
  return {
    slug,
    title: data.title || '',
    date: data.date || '',
    description: data.description || '',
    category: data.category || '未分類',
    tags: data.tags || [],
    image: data.image || '',
    pickupImage: data.pickupImage || '',
    content,
  }
}
