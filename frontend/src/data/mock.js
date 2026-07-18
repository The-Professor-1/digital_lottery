const TOTAL_TICKETS = 3500
const SOLD_COUNT = 397

/** Deterministic sold-number set so the grid looks realistic */
function buildSoldNumbers(count, total) {
  const sold = new Set()
  let seed = 7919
  while (sold.size < count) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    const n = (seed % total) + 1
    sold.add(n)
  }
  return sold
}

export const soldNumbers = buildSoldNumbers(SOLD_COUNT, TOTAL_TICKETS)

export const banks = [
  {
    id: 'telebirr',
    name: 'Telebirr',
    holder: 'Getachew',
    account: '0924242419',
  },
  {
    id: 'cbe',
    name: 'Commercial Bank of Ethiopia',
    holder: 'Getachew Fikadu Jirata',
    account: '1000528139489',
  },
]

export const featuredRaffle = {
  id: 'gech-ev-1',
  name: 'Markos Digital Lottery',
  displayName: 'Markos Digital Lottery',
  color: '',
  heroTitle: 'markos digital lottery',
  prize1st: 100000,
  prize2nd: 50000,
  prize3rd: 25000,
  winner1st: null,
  winner2nd: null,
  winner3rd: null,
  drawCompleted: false,
  image: '',
  badge: 'trending',
  rating: 5.0,
  ticketPrice: 3000,
  totalTickets: TOTAL_TICKETS,
  soldCount: SOLD_COUNT,
  endsAt: Date.now() + (((12 * 24 + 10) * 60 + 24) * 60 + 45) * 1000,
  participants: 397,
  tags: ['all', 'popular', 'new'],
}

export const otherRaffles = []

/** Sample tickets for search demo */
export const sampleTickets = [
  {
    id: 't1',
    phone: '251952838412',
    raffleName: 'Gech EV Makina Ekub',
    numbers: ['061'],
    status: 'pending',
    amount: 3000,
    createdAt: '2026-07-10',
  },
  {
    id: 't2',
    phone: '251911223344',
    raffleName: 'Gech EV Makina Ekub',
    numbers: ['128', '129'],
    status: 'active',
    amount: 6000,
    createdAt: '2026-07-08',
  },
]

export function padNumber(n) {
  return String(n).padStart(3, '0')
}

export function formatBirr(n) {
  return `${Number(n).toLocaleString('en-US')} Birr`
}
