import type { MetadataRoute } from 'next'
import { getAllPosts } from '@/lib/posts'

function getSiteUrl(): string {
  return 'https://www.qolmedia.info'
}

function toLastModified(dateLike?: string): Date | undefined {
  if (!dateLike) return undefined
  const d = new Date(dateLike)
  return Number.isNaN(d.getTime()) ? undefined : d
}

export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = getSiteUrl()
  const now = new Date()

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${siteUrl}/`, lastModified: now, changeFrequency: 'daily', priority: 1 },
    // public/ 配下の静的LPはNext.jsのルート自動検出に含まれないため明示する
    { url: `${siteUrl}/factoring-lp.html`, lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${siteUrl}/hc-guide.html`, lastModified: now, changeFrequency: 'weekly', priority: 0.9 },
    { url: `${siteUrl}/sleep-guide.html`, lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${siteUrl}/pet-lp.html`, lastModified: now, changeFrequency: 'weekly', priority: 0.7 },
    { url: `${siteUrl}/pet`, lastModified: now, changeFrequency: 'daily', priority: 0.8 },
    { url: `${siteUrl}/health`, lastModified: now, changeFrequency: 'daily', priority: 0.8 },
    { url: `${siteUrl}/life`, lastModified: now, changeFrequency: 'daily', priority: 0.8 },
    { url: `${siteUrl}/sleep`, lastModified: now, changeFrequency: 'daily', priority: 0.8 },
    { url: `${siteUrl}/about`, lastModified: now, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${siteUrl}/privacy`, lastModified: now, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${siteUrl}/contact`, lastModified: now, changeFrequency: 'monthly', priority: 0.3 },
  ]

  const postRoutes: MetadataRoute.Sitemap = getAllPosts().map(post => ({
    url: `${siteUrl}/posts/${post.slug}`,
    lastModified: toLastModified(post.updated || post.date) ?? now,
    changeFrequency: 'weekly',
    priority: post.slug === 'aga-hiyo-hikaku-2026' ? 0.85 : 0.6,
  }))

  return [...staticRoutes, ...postRoutes]
}
