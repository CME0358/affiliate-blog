// Hosts already used as affiliate destinations in article bodies.
// sleep-guide.html trackAffiliateClick fires affiliate_click then cta_click.
const AFFILIATE_HOSTS = new Set([
  't.afi-b.com',
  'px.a8.net',
  'mttag.com',
  'amzn.to',
])

export const ARTICLE_CLICK_LOCATION = 'article'

export function isExistingAffiliateHref(href: string): boolean {
  try {
    const url = new URL(href, 'https://www.qolmedia.info')
    return AFFILIATE_HOSTS.has(url.hostname)
  } catch {
    return false
  }
}

export type AffiliateEventParams = {
  event_category: string
  event_label: string
  worry_type: string
  link_location?: string
  cta_location?: string
}

export function articleAffiliateEvents(label: string): Array<{
  name: 'affiliate_click' | 'cta_click'
  params: AffiliateEventParams
}> {
  const event_label = label || 'unknown'
  return [
    {
      name: 'affiliate_click' as const,
      params: {
        event_category: 'cv',
        event_label,
        worry_type: 'none',
        link_location: ARTICLE_CLICK_LOCATION,
      },
    },
    {
      name: 'cta_click' as const,
      params: {
        event_category: 'affiliate',
        event_label,
        worry_type: 'none',
        cta_location: ARTICLE_CLICK_LOCATION,
      },
    },
  ]
}
