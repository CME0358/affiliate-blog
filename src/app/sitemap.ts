import type { MetadataRoute } from 'next'
import { getAllPosts } from '@/lib/posts'

function getSiteUrl(): string {
  const raw =
    process.env.NEXT_PUBLIC_SITE_URL ||
    process.env.SITE_URL ||
    process.env.VERCEL_URL ||
    'http://localhost:3000'

  const withProto = raw.startsWith('http') ? raw : `https://${raw}`
  return withProto.replace(/\/+$/, '')
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
    lastModified: toLastModified(post.date) ?? now,
    changeFrequency: 'weekly',
    priority: 0.6,
  }))

  return [...staticRoutes, ...postRoutes]
}

