import { reactive } from 'vue'
import { featuredRaffle, sampleTickets, soldNumbers, padNumber, banks as defaultBanks } from '../data/mock'
import { getLotterySettings } from '../services/api'

const THEME_KEY = 'gfj_theme'

export const store = reactive({
  theme: localStorage.getItem(THEME_KEY) || 'dark',
  brandName: 'Getachew Fikadu',
  banks: defaultBanks.map((b) => ({ ...b })),
  phone: '251952838412',
  quantity: 1,
  selectedNumbers: [],
  showPicker: false,
  showCheckout: false,
  checkoutStep: 1,
  fullName: '',
  selectedBankId: null,
  paymentProofName: '',
  paidFromAccount: '',
  orderDone: false,
  tickets: [...sampleTickets],
  raffle: { ...featuredRaffle },
  filter: 'all',
  settingsLoaded: false,
})

export function applyPublicSettings(data) {
  if (!data) return
  if (data.brand_name) store.brandName = data.brand_name
  store.raffle = {
    ...store.raffle,
    id: store.raffle.id || 'gech-ev-1',
    name: data.car_name || store.raffle.name,
    displayName: data.display_name || store.raffle.displayName,
    color: data.car_color || store.raffle.color,
    image: data.car_image_url || store.raffle.image,
    ticketPrice: data.ticket_price ?? store.raffle.ticketPrice,
    totalTickets: data.total_tickets ?? store.raffle.totalTickets,
    soldCount: data.sold_count ?? store.raffle.soldCount,
    endsAt: data.ends_at_ms || store.raffle.endsAt,
    participants: data.sold_count ?? store.raffle.participants,
  }
  if (Array.isArray(data.payment_accounts) && data.payment_accounts.length) {
    store.banks = data.payment_accounts.map((a, i) => ({
      id: a.id || `acc-${i}`,
      name: a.name || '',
      holder: a.holder || '',
      account: a.account || '',
    }))
  }
  store.settingsLoaded = true
}

export async function loadPublicSettings() {
  try {
    const data = await getLotterySettings()
    applyPublicSettings(data)
    return data
  } catch (e) {
    console.warn('Lottery settings unavailable, using mock defaults', e)
    store.settingsLoaded = true
    return null
  }
}

export function percentFilled() {
  return Math.round((store.raffle.soldCount / store.raffle.totalTickets) * 100)
}

export function remainingTickets() {
  return store.raffle.totalTickets - store.raffle.soldCount
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
  if (soldNumbers.has(n)) return
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
    if (!soldNumbers.has(i)) available.push(i)
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
  store.showCheckout = true
}

export function openCheckoutFromSelect() {
  if (store.selectedNumbers.length !== store.quantity) return
  store.checkoutStep = 1
  store.orderDone = false
  store.showCheckout = true
}

export function closeCheckout() {
  store.showCheckout = false
  store.checkoutStep = 1
}

export function submitOrder() {
  const numbers = store.selectedNumbers.map(padNumber)
  store.tickets.unshift({
    id: `local-${Date.now()}`,
    phone: store.phone,
    raffleName: store.raffle.displayName,
    numbers,
    status: 'pending',
    amount: totalPrice(),
    createdAt: new Date().toISOString().slice(0, 10),
  })
  store.orderDone = true
  store.checkoutStep = 3
}

export function finishOrder() {
  store.showCheckout = false
  store.checkoutStep = 1
  store.orderDone = false
  store.selectedNumbers = []
  store.quantity = 1
  store.fullName = ''
  store.selectedBankId = null
  store.paymentProofName = ''
  store.paidFromAccount = ''
}
