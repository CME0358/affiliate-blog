import assert from 'node:assert/strict'
import { test } from 'node:test'
import { articleAffiliateEvents, isExistingAffiliateHref } from './article-affiliate-click.ts'

test('existing affiliate hosts used in articles match', () => {
  assert.equal(
    isExistingAffiliateHref('https://t.afi-b.com/visit.php?a=46393a-U221067n&p=e855734s'),
    true,
  )
  assert.equal(
    isExistingAffiliateHref('https://px.a8.net/svt/ejp?a8mat=4AZS0R+6C130I+4KU6+61Z81'),
    true,
  )
  assert.equal(isExistingAffiliateHref('https://mttag.com/s/L7IrW864-jY'), true)
  assert.equal(isExistingAffiliateHref('https://amzn.to/4c9wbXX'), true)
})

test('internal links and other hosts are not affiliate clicks', () => {
  assert.equal(isExistingAffiliateHref('/hc-guide.html'), false)
  assert.equal(isExistingAffiliateHref('/posts/aga-hiyo-hikaku-2026'), false)
  assert.equal(isExistingAffiliateHref('https://www.qolmedia.info/sleep-guide.html'), false)
  assert.equal(isExistingAffiliateHref('https://example.com/out'), false)
  assert.equal(isExistingAffiliateHref('https://www.afi-b.com/upload_image/x.jpg'), false)
  assert.equal(isExistingAffiliateHref(''), false)
})

test('events match the LP payload and mark the click as article', () => {
  assert.deepEqual(articleAffiliateEvents('無料カウンセリングで総額の目安を聞く'), [
    {
      name: 'affiliate_click',
      params: {
        event_category: 'cv',
        event_label: '無料カウンセリングで総額の目安を聞く',
        worry_type: 'none',
        link_location: 'article',
      },
    },
    {
      name: 'cta_click',
      params: {
        event_category: 'affiliate',
        event_label: '無料カウンセリングで総額の目安を聞く',
        worry_type: 'none',
        cta_location: 'article',
      },
    },
  ])
})
