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
  content: string
}

export function getCategoryImage(category: string): string {
  const map: Record<string, string> = {
    'ペット': '/og-pet.svg',
    '健康': '/og-health.svg',
    '暮らし': '/og-life.svg',
  }
  return map[category] || '/og-default.svg'
}

export function getPostImage(post: Post): string {
  return post.image || getCategoryImage(post.category)
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
    content,
  }
}
