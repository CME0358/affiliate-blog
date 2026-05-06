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
  image?: string
  pickupImage?: string
  published?: boolean
  content: string
}

// FVヒーロー用画像（1枚目固定）
export const FV_IMAGE = '/fv-hero.png'

// ピックアップ用デフォルト画像（2〜4枚目）
export const PICKUP_DEFAULT_IMAGE = '/pickup-default.svg'

// カテゴリ別デフォルト画像（記事カード用）
export function getCategoryImage(category: string): string {
  const map: Record<string, string> = {
    'ペット': '/og-pet.svg',
    '健康': '/og-health.svg',
    '暮らし': '/og-life.svg',
    '睡眠': '/og-sleep.svg',
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

// content/posts/ 配下のすべての .md / .mdx ファイルを再帰的に収集
function collectFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  const files: string[] = []
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath))
    } else if (entry.name.endsWith('.md') || entry.name.endsWith('.mdx')) {
      files.push(fullPath)
    }
  }
  return files
}

export function getAllPosts(): Post[] {
  const files = collectFiles(postsDir)
  return files
    .map(filePath => {
      const slug = path.basename(filePath).replace(/\.mdx?$/, '')
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
        published: data.published !== false,
        content,
      }
    })
    .filter(post => post.published !== false)
    .sort((a, b) => (a.date < b.date ? 1 : -1))
}

export function getPostBySlug(slug: string): Post | null {
  // サブフォルダを含めて検索
  const files = collectFiles(postsDir)
  const filePath = files.find(f => path.basename(f).replace(/\.mdx?$/, '') === slug)
  if (!filePath) return null
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
    published: data.published !== false,
    content,
  }
}
