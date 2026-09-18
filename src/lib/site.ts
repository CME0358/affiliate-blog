export const SITE_URL = 'https://www.qolmedia.info'
export const SITE_NAME = 'QOL media'

export const HOME_TITLE = 'QOL media｜AGA費用比較・睡眠・ペットケア'
export const HOME_DESCRIPTION =
  'AGA治療の費用（初月と総額）の見方、睡眠の悩み別対策、ペット薬の選び方など、生活の質を高める比較ガイド。料金や効果は断定せず、公式情報と専門家への確認を前提に解説します。'

export const PET_CLUSTER_POSTS = [
  { slug: 'heartworm-medicine-cheapest-ranking', label: 'フィラリア薬最安ランキング', hint: '病院との価格差と正規品の確認' },
  { slug: 'flea-tick-medicine-cost-compare', label: 'ノミダニ薬コスパ比較', hint: '犬猫別の確認ポイント' },
  { slug: 'pet-medicine-personal-import-safe', label: '個人輸入の注意', hint: '正規品・品質リスクの見方' },
  { slug: 'heartworm-medicine-side-effects', label: 'フィラリア薬の副作用', hint: '個体差と受診の目安' },
] as const

export const HC_CLUSTER_POSTS = [
  { slug: 'aga-hiyo-hikaku-2026', label: '費用比較の読み方', hint: '初月と総額のチェックリスト' },
  { slug: 'aga-hatsugetsu-ryokin-mikata-2026', label: '初月料金の見方', hint: '広告と2ヶ月目以降の確認点' },
  { slug: 'aga-online-shinryo-hiyo-2026', label: 'オンライン診療の費用', hint: '送料・検査・対面との違い' },
  { slug: 'aga-counseling-kiku-koto-2026', label: 'カウンセリングで聞くこと', hint: '見積もりと契約前チェック' },
  { slug: 'aga-kusuri-shokumo-hiyo-chigai-2026', label: '薬と植毛の費用', hint: '継続コストと施術単位' },
] as const

export const HUBS = [
  {
    href: '/hc-guide.html',
    label: 'AGA費用比較',
    hint: '初月と総額の見方',
    primary: true,
  },
  {
    href: '/sleep-guide.html',
    label: '睡眠ガイド',
    hint: '寝つき・中途覚醒の比較',
    primary: false,
  },
  {
    href: '/pet-lp.html',
    label: 'ペット薬比較',
    hint: 'フィラリア・正規品の確認',
    primary: false,
  },
  {
    href: '/factoring-lp.html',
    label: 'ファクタリング',
    hint: '手数料と業者比較',
    primary: false,
  },
] as const
