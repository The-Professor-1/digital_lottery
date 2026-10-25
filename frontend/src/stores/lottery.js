import { reactive } from 'vue'
import { featuredRaffle, padNumber, banks as defaultBanks } from '../data/mock'
import {
  getLotterySettings, getLotteryItems, getLotteryItemDetail, getLotteryMe,
  getLotteryTickets, submitLotteryPurchase, setToken,
} from '../services/api'

const THEME_KEY = 'gfj_theme'
const GUEST_NAME_KEY = 'gfj_guest_name'
const GUEST_PHONE_KEY = 'gfj_guest_phone'
const GUEST_TOKEN_KEY = 'gfj_guest_token'

export const store = reactive({
  theme: localStorage.getItem(THEME_KEY) || 'dark',
  brandName: 'Digital Lottery',
  banks: defaultBanks.map((b) => ({ ...b })),
  phone: '',
  quantity: 1,
  selectedNumbers: [],
  takenNumbers: new Set(),
  verifiedTakenNumbers: new Set(),
  showPicker: false,
  showCheckout: false,
  checkoutStep: 1,
  fullName: '',
  selectedBankId: null,
  receiptSms: '',
  paymentProofFile: null,
  paymentProofName: '',
  paidFromAccount: '',
  orderDone: false,
  orderVerified: false,
  submitError: '',
  submitErrorKey: '',
  submitMessage: '',
  submitting: false,
  verifying: false,
  conflictDialog: false,
  conflictMessage: '',
  conflictMessageKey: '',
  conflictAvailable: [],
  conflictKept: [],
  conflictPicked: [],
  tickets: [],
  ticketStats: { active: 0, pending: 0, total: 0 },
  raffle: { ...featuredRaffle, soldCount: 0 },
  filter: 'all',
  settingsLoaded: false,
  homeRefreshKey: 0,
  items: [],
  winners: [],
  activeItemId: null,
  landingTexts: {},
  landingLoaded: false,
})

export function landingText(key, fallback = '') {
  const value = store.landingTexts?.[key]
  return typeof value === 'string' && value.trim() ? value : fallback
}

export function isTaken(n) {
  return store.takenNumbers.has(Number(n))
}

export function applyPublicSettings(data) {
  if (!data) return
  if (data.landing_texts && typeof data.landing_texts === 'object') {
    store.landingTexts = { ...data.landing_texts }
  }
  if (data.brand_name) {
    store.brandName = data.brand_name
    if (typeof document !== 'undefined' && data.brand_name) {
      document.title = data.brand_name
    }
  }
  if (store.activeItemId || store.items.length) {
    // Keep the per-item raffle selected by the landing page. Global settings are
    // only a fallback for installations with no lottery items.
    if (Array.isArray(data.payment_accounts) && data.payment_accounts.length) {
      store.banks = data.payment_accounts.map((a, i) => ({
        id: a.id || 'acc-' + i,
        name: a.name || '',
        holder: a.holder || '',
        account: a.account || '',
      }))
    }
    store.settingsLoaded = true
    return
  }
  const nextMode =
    data.draw_mode === 'date' || data.draw_mode === 'sold_out' || data.draw_mode === 'manual'
      ? data.draw_mode
      : store.raffle.drawMode || 'date'
  store.raffle = {
    ...store.raffle,
    id: store.raffle.id || 'lottery-1',
    name: data.display_name || data.car_name || store.raffle.name || store.brandName,
    displayName: data.display_name || store.raffle.displayName || store.brandName,
    color: data.car_color || store.raffle.color,
    heroTitle: data.hero_title || store.raffle.heroTitle || store.brandName,
    prize1st: data.prize_1st ?? store.raffle.prize1st ?? 0,
    prize2nd: data.prize_2nd ?? store.raffle.prize2nd ?? 0,
    prize3rd: data.prize_3rd ?? store.raffle.prize3rd ?? 0,
    winner1st: data.winner_1st ?? null,
    winner2nd: data.winner_2nd ?? null,
    winner3rd: data.winner_3rd ?? null,
    drawCompleted: !!data.draw_completed,
    nextRoundAt: data.next_round_at_ms || 0,
    nextRoundMinutes: data.next_round_minutes ?? store.raffle.nextRoundMinutes ?? 10,
    winnerRevealSeconds: data.winner_reveal_seconds ?? store.raffle.winnerRevealSeconds ?? 6,
    winnersNotified: !!data.winners_notified,
    automaticAnnouncement: data.automatic_announcement !== false,
    drawMode: nextMode,
    drawTimerSeconds: data.draw_timer_seconds ?? store.raffle.drawTimerSeconds ?? 60,
    image: data.car_image_url || store.raffle.image,
    ticketPrice: data.ticket_price ?? store.raffle.ticketPrice,
    totalTickets: data.total_tickets ?? store.raffle.totalTickets,
    soldCount: data.sold_count ?? 0,
    // Non-date modes: no public deadline until admin Start Draw
    endsAt: nextMode === 'date' ? (data.ends_at_ms || 0) : (data.ends_at_ms || 0),
    participants: data.sold_count ?? 0,
  }
  if (Array.isArray(data.payment_accounts) && data.payment_accounts.length) {
    store.banks = data.payment_accounts.map((a, i) => ({
      id: a.id || `acc-${i}`,
      name: a.name || '',
      holder: a.holder || '',
      account: a.account || '',
    }))
  }
  const taken = new Set()
  for (const n of data.taken_numbers || []) {
    taken.add(Number(n))
  }
  store.takenNumbers = taken
  const verified = new Set()
  for (const n of data.verified_taken_numbers || []) {
    verified.add(Number(n))
  }
  store.verifiedTakenNumbers = verified
  store.settingsLoaded = true
}



export function applyItemToRaffle(item) {
  if (!item) return
  store.activeItemId = item.id
  if (item.landing_texts && typeof item.landing_texts === 'object') {
    store.landingTexts = { ...item.landing_texts }
  }
  const prizes = Array.isArray(item.prizes) ? item.prizes : []
  store.raffle = {
    ...store.raffle,
    id: item.id,
    name: item.name || item.display_name || store.raffle.name,
    displayName: item.display_name || item.name || store.raffle.displayName,
    heroTitle: item.hero_title || item.name || store.brandName,
    description: item.description || '',
    image: item.image_url || '',
    prizes,
    prize1st: prizes[0]?.amount ?? 0,
    prize2nd: prizes[1]?.amount ?? 0,
    prize3rd: prizes[2]?.amount ?? 0,
    ticketPrice: item.ticket_price ?? store.raffle.ticketPrice,
    totalTickets: item.total_tickets ?? store.raffle.totalTickets,
    soldCount: item.sold_count ?? 0,
    participants: item.sold_count ?? 0,
    endsAt: item.ends_at_ms || 0,
    drawMode: item.draw_mode || 'date',
    drawTimerSeconds: item.draw_timer_seconds ?? 60,
    automaticAnnouncement: item.automatic_announcement !== false,
    winnerRevealSeconds: item.winner_reveal_seconds ?? 6,
    drawCompleted: !!item.draw_completed,
    winner1st: item.winner_1st ?? null,
    winner2nd: item.winner_2nd ?? null,
    winner3rd: item.winner_3rd ?? null,
    nextRoundAt: item.next_round_at_ms || 0,
    nextRoundMinutes: item.next_round_minutes ?? 10,
    winnersNotified: !!item.winners_notified,
  }
  if (Array.isArray(item.taken_numbers)) {
    store.takenNumbers = new Set(item.taken_numbers.map((n) => Number(n)))
  }
  if (Array.isArray(item.verified_taken_numbers)) {
    store.verifiedTakenNumbers = new Set(item.verified_taken_numbers.map((n) => Number(n)))
  }
}

export async function loadWinners() {
  try {
    const data = await getLotteryItems()
    store.winners = (data.winners || []).slice(0, 30)
    return store.winners
  } catch (e) {
    return []
  }
}

export async function loadLanding() {
  try {
    const data = await getLotteryItems()
    store.items = Array.isArray(data.items) ? data.items : []
    store.winners = (data.winners || []).slice(0, 30)
    if (data.landing_texts && typeof data.landing_texts === 'object') {
      store.landingTexts = { ...data.landing_texts }
    }
    if (data.brand_name) store.brandName = data.brand_name
    if (Array.isArray(data.payment_accounts) && data.payment_accounts.length) {
      store.banks = data.payment_accounts.map((a, i) => ({
        id: a.id || 'acc-' + i,
        name: a.name || '',
        holder: a.holder || '',
        account: a.account || '',
      }))
    }
    store.landingLoaded = true
    if (store.items.length === 1) {
      await activateItemById(store.items[0].id)
    } else if (!store.items.length) {
      store.activeItemId = null
    }
    return data
  } catch (e) {
    console.warn('Landing data unavailable, using defaults', e)
    store.landingLoaded = true
    return null
  }
}

export async function activateItemById(id) {
  const item =
    (await getLotteryItemDetail(id).catch(() => null)) ||
    store.items.find((it) => Number(it.id) === Number(id))
  if (!item) return null
  applyItemToRaffle(item)
  return item
}

export async function loadPublicSettings() {
  try {
    const data = await getLotterySettings()
    applyPublicSettings(data)
    return data
  } catch (e) {
    console.warn('Lottery settings unavailable, using defaults', e)
    store.takenNumbers = new Set()
    store.settingsLoaded = true
    return null
  }
}

export async function loadUserProfile() {
  try {
    const me = await getLotteryMe()
    if (me?.phone) {
      store.phone = String(me.phone).replace(/\D/g, '')
      if (store.phone.startsWith('0') && store.phone.length === 10) {
        store.phone = '251' + store.phone.slice(1)
      }
    }
    if (me?.preferred_language) {
      const { applyPreferredLocale } = await import('../composables/useI18n')
      applyPreferredLocale(me.preferred_language)
    }
  } catch (e) {
    // Not authenticated — leave phone empty for user input
  }
}

export function saveGuestSession({ name, phone, token } = {}) {
  try {
    if (name) localStorage.setItem(GUEST_NAME_KEY, String(name))
    if (phone) localStorage.setItem(GUEST_PHONE_KEY, String(phone).replace(/\D/g, ''))
    if (token) {
      localStorage.setItem(GUEST_TOKEN_KEY, String(token))
      setToken(token)
    }
  } catch (e) {
    // localStorage can be unavailable in private browsing.
  }
}

export function restoreGuestSession() {
  try {
    const name = localStorage.getItem(GUEST_NAME_KEY) || ''
    const phone = localStorage.getItem(GUEST_PHONE_KEY) || ''
    const token = localStorage.getItem(GUEST_TOKEN_KEY) || ''
    if (name) store.fullName = name
    if (phone) store.phone = String(phone).replace(/\D/g, '')
    if (token && !localStorage.getItem('auth_token')) setToken(token)
  } catch (e) {
    // Ignore storage failures.
  }
}

export async function loadTicketsForPhone(phone = store.phone) {
  if (!phone) {
    store.tickets = []
    store.ticketStats = { active: 0, pending: 0, total: 0 }
    return
  }
  try {
    const data = await getLotteryTickets(phone)
    store.tickets = (data.tickets || []).map((t) => ({
      id: t.id,
      phone: t.phone,
      lotteryItemId: t.lottery_item_id ?? null,
      raffleName: t.lottery_item_name || store.raffle.displayName,
      numbers: (t.numbers || []).map((n) => String(n).padStart(3, '0')),
      status: t.status === 'verified' ? 'active' : t.status,
      amount: t.amount,
      createdAt: (t.created_at || '').slice(0, 10),
    }))
    store.ticketStats = {
      active: data.active || 0,
      pending: data.pending || 0,
      total: data.total || 0,
    }
  } catch (e) {
    console.warn('Tickets load failed', e)
  }
}

export function percentFilled() {
  return Math.round((store.raffle.soldCount / store.raffle.totalTickets) * 100) || 0
}

export function remainingTickets() {
  return Math.max(0, store.raffle.totalTickets - store.raffle.soldCount)
}

export function totalPrice() {
  const n = store.selectedNumbers.length || store.quantity || 0
  return n * (store.raffle.ticketPrice || 0)
}

export function toggleTheme() {
  store.theme = store.theme === 'dark' ? 'light' : 'dark'
  localStorage.setItem(THEME_KEY, store.theme)
}

export function setQuantity(q) {
  const max = Math.max(1, store.raffle.totalTickets || 3500)
  const next = Math.max(1, Math.min(max, q))
  store.quantity = next
  if (store.selectedNumbers.length > next) {
    store.selectedNumbers = store.selectedNumbers.slice(0, next)
  }
}

export function toggleNumber(n) {
  if (isTaken(n)) return
  const idx = store.selectedNumbers.indexOf(n)
  if (idx >= 0) {
    store.selectedNumbers.splice(idx, 1)
    store.quantity = Math.max(1, store.selectedNumbers.length)
    return
  }
  const max = Math.max(1, store.raffle.totalTickets || 3500)
  if (store.selectedNumbers.length >= max) return
  store.selectedNumbers.push(n)
  store.quantity = store.selectedNumbers.length
}

export function openPicker() {
  store.showPicker = true
}

export function closePicker() {
  store.showPicker = false
}

export function confirmPicker() {
  if (store.selectedNumbers.length < 1) return
  store.quantity = store.selectedNumbers.length
  store.showPicker = false
  openCheckoutFromSelect()
}

export function openCheckoutFromSelect() {
  if (store.selectedNumbers.length < 1) return
  store.quantity = store.selectedNumbers.length
  store.checkoutStep = 1
  store.orderDone = false
  store.orderVerified = false
  store.submitError = ''
  store.submitErrorKey = ''
  store.submitMessage = ''
  store.conflictDialog = false
  store.conflictMessageKey = ''
  store.paymentProofFile = null
  store.paymentProofName = ''
  store.showCheckout = true
}

export function closeCheckout() {
  if (store.verifying) return
  store.showCheckout = false
  store.checkoutStep = 1
  store.submitting = false
  store.verifying = false
  store.conflictDialog = false
  store.submitError = ''
  store.submitErrorKey = ''
  store.conflictMessageKey = ''
}

export async function submitOrder() {
  store.submitError = ''
  store.submitErrorKey = ''
  store.submitMessage = ''
  const bank = store.banks.find((b) => b.id === store.selectedBankId) || {}
  if (!store.paymentProofFile) {
    store.submitErrorKey = 'uploadScreenshot'
    return false
  }

  store.submitting = true
  store.verifying = true
  try {
    const form = new FormData()
    form.append('full_name', store.fullName)
    form.append('phone', store.phone)
    form.append('numbers', JSON.stringify(store.selectedNumbers))
    form.append('paid_from_account', store.paidFromAccount || '')
    form.append('bank_id', bank.id || '')
    form.append('bank_name', bank.name || '')
    form.append('bank_holder', bank.holder || '')
    form.append('bank_account', bank.account || '')
    if (store.activeItemId) form.append('lottery_item_id', String(store.activeItemId))
    form.append('receipt', store.paymentProofFile)

    const res = await submitLotteryPurchase(form)
    store.orderDone = true
    store.orderVerified = !!res.verified
    store.submitMessage = res.message || ''
    if (res.manual_review && !res.verified) {
      store.orderVerified = false
    }
    const guestPhone = String(res.guest_phone || store.phone || '').replace(/\D/g, '')
    if (guestPhone) store.phone = guestPhone
    if (res.guest_token) {
      saveGuestSession({
        name: res.guest_name || store.fullName,
        phone: guestPhone,
        token: res.guest_token,
      })
    }
    if (store.activeItemId) {
      await activateItemById(store.activeItemId)
    } else {
      await loadPublicSettings()
    }
    await loadTicketsForPhone(guestPhone)
    return true
  } catch (e) {
    const data = e.response?.data || {}
    const code = data.error_code || ''
    if (code === 'numbers_taken' || (e.response?.status === 409 && Array.isArray(data.available))) {
      const taken = Array.isArray(data.taken) ? data.taken.map(Number) : []
      const kept = Array.isArray(data.kept)
        ? data.kept.map(Number)
        : store.selectedNumbers.filter((n) => !taken.includes(Number(n)))
      store.conflictMessage = data.error || ''
      store.conflictMessageKey = 'numbersTakenMessage'
      store.conflictAvailable = data.available || []
      store.conflictKept = kept
      store.conflictPicked = []
      store.conflictDialog = true
      return false
    }
    const errorKeys = {
      missing_fields: 'namePhoneRequired',
      missing_numbers: 'selectAtLeastOne',
      missing_receipt: 'receiptRequired',
      screenshot_required: 'receiptRequired',
      duplicate_receipt: 'duplicateReceipt',
    }
    if (errorKeys[code]) {
      store.submitErrorKey = errorKeys[code]
    } else {
      store.submitError = data.error || e.message || ''
    }
    return false
  } finally {
    store.submitting = false
    store.verifying = false
  }
}

export function finishOrder() {
  store.showCheckout = false
  store.checkoutStep = 1
  store.orderDone = false
  store.orderVerified = false
  store.selectedNumbers = []
  store.quantity = 1
  store.fullName = ''
  store.selectedBankId = null
  store.receiptSms = ''
  store.paymentProofFile = null
  store.paymentProofName = ''
  store.paidFromAccount = ''
  store.submitError = ''
  store.submitErrorKey = ''
  store.submitMessage = ''
  store.conflictDialog = false
  store.conflictMessageKey = ''
  store.conflictAvailable = []
  store.conflictKept = []
  store.conflictPicked = []
  store.conflictMessage = ''
}

export { padNumber }
