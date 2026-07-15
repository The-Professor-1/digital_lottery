import { reactive } from 'vue'
import { featuredRaffle, padNumber, banks as defaultBanks } from '../data/mock'
import { getLotterySettings, getLotteryMe, getLotteryTickets, submitLotteryPurchase } from '../services/api'

const THEME_KEY = 'gfj_theme'

export const store = reactive({
  theme: localStorage.getItem(THEME_KEY) || 'dark',
  brandName: 'Getachew Fikadu',
  banks: defaultBanks.map((b) => ({ ...b })),
  phone: '',
  quantity: 1,
  selectedNumbers: [],
  takenNumbers: new Set(),
  showPicker: false,
  showCheckout: false,
  checkoutStep: 1,
  fullName: '',
  selectedBankId: null,
  paymentProofFile: null,
  paymentProofName: '',
  paidFromAccount: '',
  orderDone: false,
  submitError: '',
  submitMessage: '',
  submitting: false,
  tickets: [],
  ticketStats: { active: 0, pending: 0, total: 0 },
  raffle: { ...featuredRaffle, soldCount: 0 },
  filter: 'all',
  settingsLoaded: false,
  homeRefreshKey: 0,
})

export function isTaken(n) {
  return store.takenNumbers.has(Number(n))
}

export function applyPublicSettings(data) {
  if (!data) return
  if (data.brand_name) store.brandName = data.brand_name
  store.raffle = {
    ...store.raffle,
    id: store.raffle.id || 'gech-ev-1',
    name: data.car_name || store.raffle.name,
    displayName: data.display_name || store.raffle.displayName,
    color: data.car_color || store.raffle.color,
    // Always take API image when present so admin uploads replace the mock photo
    image: data.car_image_url || store.raffle.image,
    ticketPrice: data.ticket_price ?? store.raffle.ticketPrice,
    totalTickets: data.total_tickets ?? store.raffle.totalTickets,
    soldCount: data.sold_count ?? 0,
    endsAt: data.ends_at_ms || store.raffle.endsAt,
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
  store.settingsLoaded = true
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
      raffleName: store.raffle.displayName,
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
  return store.quantity * store.raffle.ticketPrice
}

export function toggleTheme() {
  store.theme = store.theme === 'dark' ? 'light' : 'dark'
  localStorage.setItem(THEME_KEY, store.theme)
}

export function setQuantity(q) {
  const next = Math.max(1, Math.min(10, q))
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
    return
  }
  if (store.selectedNumbers.length >= store.quantity) return
  store.selectedNumbers.push(n)
}

export function quickPick() {
  const need = store.quantity
  const available = []
  for (let i = 1; i <= store.raffle.totalTickets; i++) {
    if (!isTaken(i)) available.push(i)
  }
  for (let i = available.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[available[i], available[j]] = [available[j], available[i]]
  }
  store.selectedNumbers = available.slice(0, need)
}

export function openPicker() {
  store.showPicker = true
}

export function closePicker() {
  store.showPicker = false
}

export function confirmPicker() {
  if (store.selectedNumbers.length !== store.quantity) return
  store.showPicker = false
  store.checkoutStep = 1
  store.orderDone = false
  store.submitError = ''
  store.submitMessage = ''
  store.showCheckout = true
}

export function openCheckoutFromSelect() {
  if (store.selectedNumbers.length !== store.quantity) return
  store.checkoutStep = 1
  store.orderDone = false
  store.submitError = ''
  store.submitMessage = ''
  store.showCheckout = true
}

export function closeCheckout() {
  store.showCheckout = false
  store.checkoutStep = 1
  store.submitting = false
}

export async function submitOrder() {
  store.submitError = ''
  store.submitMessage = ''
  if (!store.paymentProofFile) {
    store.submitError = 'Please upload a payment receipt image.'
    return false
  }
  store.submitting = true
  try {
    const bank = store.banks.find((b) => b.id === store.selectedBankId)
    const form = new FormData()
    form.append('full_name', store.fullName)
    form.append('phone', store.phone)
    form.append('numbers', JSON.stringify(store.selectedNumbers))
    form.append('paid_from_account', store.paidFromAccount || '')
    form.append('bank_name', bank?.name || '')
    form.append('bank_holder', bank?.holder || '')
    form.append('bank_account', bank?.account || '')
    form.append('receipt', store.paymentProofFile)

    const res = await submitLotteryPurchase(form)
    store.orderDone = true
    store.checkoutStep = 3
    store.submitMessage = ''
    await loadPublicSettings()
    await loadTicketsForPhone(store.phone)
    return true
  } catch (e) {
    store.submitError =
      e.response?.data?.error || e.message || 'Could not submit. Try again.'
    return false
  } finally {
    store.submitting = false
  }
}

export function finishOrder() {
  store.showCheckout = false
  store.checkoutStep = 1
  store.orderDone = false
  store.selectedNumbers = []
  store.quantity = 1
  store.fullName = ''
  store.selectedBankId = null
  store.paymentProofFile = null
  store.paymentProofName = ''
  store.paidFromAccount = ''
  store.submitError = ''
  store.submitMessage = ''
}

export { padNumber }
