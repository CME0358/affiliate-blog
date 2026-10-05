'use client'

import type { MouseEvent, ReactNode } from 'react'
import {
  articleAffiliateEvents,
  isExistingAffiliateHref,
  type AffiliateEventParams,
} from '@/lib/article-affiliate-click'

type Gtag = (command: 'event', name: string, params?: AffiliateEventParams) => void

function labelFromAnchor(anchor: HTMLAnchorElement) {
  const text = (anchor.textContent || '').replace(/\s+/g, ' ').trim()
  if (text) return text.slice(0, 100)
  const alt = anchor.querySelector('img')?.getAttribute('alt')?.trim()
  if (alt) return alt.slice(0, 100)
  return 'unknown'
}

export function ArticleAffiliateClicks({ children }: { children: ReactNode }) {
  function onClick(event: MouseEvent<HTMLDivElement>) {
    const target = event.target
    if (!(target instanceof Element)) return
    const anchor = target.closest('a')
    if (!anchor || !event.currentTarget.contains(anchor)) return
    if (!isExistingAffiliateHref(anchor.href)) return

    const gtag = (window as Window & { gtag?: Gtag }).gtag
    if (typeof gtag !== 'function') return

    for (const item of articleAffiliateEvents(labelFromAnchor(anchor))) {
      gtag('event', item.name, item.params)
    }
  }

  return (
    <div onClick={onClick} style={{fontSize:'15px', lineHeight:'1.9', color:'#374151'}}>
      {children}
    </div>
  )
}
