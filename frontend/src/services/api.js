import axios from 'axios'

// Auto-detect API URL based on current host
const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `${window.location.origin}/api`
  }
  return 'http://localhost:8000/api'
}

const API_BASE_URL = getApiUrl()

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const csrfToken = document.cookie
    .split('; ')
    .find((row) => row.startsWith('csrftoken='))
    ?.split('=')[1]
  if (csrfToken) {
    config.headers['X-CSRFToken'] = csrfToken
  }
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    if (config.headers && typeof config.headers.delete === 'function') {
      config.headers.delete('Content-Type')
    } else if (config.headers) {
      delete config.headers['Content-Type']
      delete config.headers['content-type']
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 413) {
      error.response.data = {
        error: 'The uploaded image is too large. Please choose a smaller screenshot.',
        status: 413,
      }
    } else if (
      error.response &&
      typeof error.response.data === 'string' &&
      error.response.data.trim().startsWith('<')
    ) {
      error.response.data = {
        error: 'Server returned HTML instead of JSON. This may be a CSRF or authentication error.',
        status: error.response.status,
        message: 'Please refresh the page and try again.',
      }
    }
    return Promise.reject(error)
  }
)

function getToken() {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get('token') || localStorage.getItem('auth_token')
}

export function setToken(token) {
  localStorage.setItem('auth_token', token)
}

export async function authenticateTelegram(token) {
  const response = await api.post('/auth/telegram/', { token })
  if (response.data.token) setToken(response.data.token)
  return response.data
}

export async function registerTelegram(initData) {
  const response = await api.post('/auth/telegram-register/', { initData })
  if (response.data.token) setToken(response.data.token)
  return response.data
}

export async function updateUserPhone(phoneNumber) {
  const response = await api.post('/users/phone/', { phone_number: phoneNumber })
  return response.data
}

export async function adminDashboardLogin(username, password) {
  const response = await api.post('/admin-dashboard/login/', { username, password })
  return response.data
}

export async function lotteryAdminBootstrap() {
  const response = await api.get('/admin-dashboard/lottery-bootstrap/')
  return response.data
}

export async function getSecondAdminCredentials() {
  const response = await api.get('/admin-dashboard/second-admin-credentials/')
  return response.data
}

export async function saveSecondAdminCredentials(username, password) {
  const response = await api.post('/admin-dashboard/second-admin-credentials/', {
    username,
    password,
  })
  return response.data
}

export async function secondAdminLogin(username, password) {
  const response = await api.post('/admin-view/login/', { username, password })
  return response.data
}

export async function secondAdminLogout() {
  const response = await api.post('/admin-view/logout/')
  return response.data
}

export async function getLotteryUsersAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-users/', { params })
  return response.data
}

export async function deleteLotteryUser({
  user_id = null,
  phone = null,
  from_admin_view = false,
} = {}) {
  const response = await api.post('/admin-dashboard/lottery-users/delete/', {
    user_id,
    phone,
    from_admin_view: !!from_admin_view,
  })
  return response.data
}

export async function getLotteryDeletedAdmin() {
  const response = await api.get('/admin-dashboard/lottery-deleted/')
  return response.data
}

export async function getLotterySettings() {
  const response = await api.get('/lottery/settings/')
  return response.data
}

export async function getLotteryMe() {
  const response = await api.get('/lottery/me/')
  return response.data
}

export async function setLotteryLanguage(language) {
  const response = await api.post('/lottery/language/', { language })
  return response.data
}

export async function getLotteryTickets(phone) {
  const response = await api.get('/lottery/tickets/', { params: { phone } })
  return response.data
}

export async function submitLotteryPurchase(payload) {
  const response = await api.post('/lottery/purchase/', payload)
  return response.data
}

export async function getLotterySettingsAdmin() {
  const response = await api.get('/admin-dashboard/lottery-settings/')
  return response.data
}

export async function restartLotteryRoundAdmin(payload = {}) {
  const response = await api.post('/admin-dashboard/lottery-restart-round/', payload)
  return response.data
}

export async function startLotteryDrawAdmin(payload = {}) {
  const response = await api.post('/admin-dashboard/lottery-start-draw/', payload)
  return response.data
}

export async function updateLotterySettingsAdmin(payload, file = null) {
  const form = new FormData()
  Object.entries(payload).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    if (key === 'payment_accounts' || key === 'admin_blocked_numbers') {
      form.append(key, JSON.stringify(value))
    } else if (typeof value === 'boolean') {
      form.append(key, value ? 'true' : 'false')
    } else {
      form.append(key, String(value))
    }
  })
  if (file) form.append('car_image', file)
  const response = await api.post('/admin-dashboard/lottery-settings/', form)
  return response.data
}

export async function sendLotteryMessage(payload) {
  const response = await api.post('/admin-dashboard/lottery-send-message/', payload)
  return response.data
}

export async function getLotteryPurchasesAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-purchases/', { params })
  return response.data
}

export async function lotteryPurchaseAction(id, action, note = '', from_admin_view = false) {
  const response = await api.post(`/admin-dashboard/lottery-purchases/${id}/action/`, {
    action,
    note,
    from_admin_view: !!from_admin_view,
  })
  return response.data
}

export async function announceLotteryWinner(winner_number, message) {
  const response = await api.post('/admin-dashboard/lottery-announce-winner/', {
    winner_number,
    message,
  })
  return response.data
}

export async function setManualLotteryWinners(payload) {
  const response = await api.post('/admin-dashboard/lottery-set-manual-winners/', payload)
  return response.data
}

export async function holdLotteryTicketAdmin(payload) {
  const response = await api.post('/admin-dashboard/lottery-hold-ticket/', payload)
  return response.data
}

export async function getLotteryFailedDepositsAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-failed-deposits/', { params })
  return response.data
}

export async function lotteryFailedDepositAction(id, action, transaction_ref = '') {
  const response = await api.post(`/admin-dashboard/lottery-failed-deposits/${id}/action/`, {
    action,
    transaction_ref,
    txn_no: transaction_ref,
  })
  return response.data
}

export async function runLotteryDraw() {
  const response = await api.post('/lottery/draw/')
  return response.data
}

export async function notifyLotteryWinners() {
  const response = await api.post('/lottery/notify-winners/')
  return response.data
}

export async function startLotteryNextRound() {
  const response = await api.post('/lottery/next-round/')
  return response.data
}



export async function getLotteryItems() {
  const response = await api.get('/lottery/items/')
  return response.data
}

export async function getLotteryItemDetail(itemId) {
  const response = await api.get('/lottery/items/' + itemId + '/')
  return response.data
}

export async function getLotteryItemsAdmin() {
  const response = await api.get('/admin-dashboard/lottery-items/')
  return response.data
}

export async function saveLotteryItemAdmin(formData) {
  const response = await api.post('/admin-dashboard/lottery-items/', formData)
  return response.data
}

export async function deleteLotteryItemAdmin(id) {
  const response = await api.post('/admin-dashboard/lottery-items/', { action: 'delete', id })
  return response.data
}

export async function getHeldNumbersAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-held-numbers/', { params })
  return response.data
}

export async function addHeldNumberAdmin(payload) {
  const response = await api.post('/admin-dashboard/lottery-held-numbers/', { action: 'add', ...payload })
  return response.data
}

export async function checkHeldNumbersAdmin(payload) {
  const response = await api.post('/admin-dashboard/lottery-held-numbers/', { action: 'check', ...payload })
  return response.data
}

export async function bulkHeldNumbersAdmin(payload) {
  const response = await api.post('/admin-dashboard/lottery-held-numbers/', { action: 'bulk', ...payload })
  return response.data
}

export async function deleteHeldNumberAdmin(id, lottery_item_id = null) {
  const response = await api.post('/admin-dashboard/lottery-held-numbers/', {
    action: 'delete',
    id,
    lottery_item_id: lottery_item_id || undefined,
  })
  return response.data
}

export async function getLotteryWinnersAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-winners/', { params })
  return response.data
}

export async function lookupWinnerTicket(payload) {
  const response = await api.post('/admin-dashboard/lottery-winner-lookup/', payload)
  return response.data
}

export async function announceItemWinner(payload) {
  const response = await api.post('/admin-dashboard/lottery-announce-item-winner/', payload)
  return response.data
}

export async function clearLotteryHistoryAdmin() {
  const response = await api.post('/admin-dashboard/lottery-clear-history/')
  return response.data
}

export async function deleteLotteryWinnerAdmin(id) {
  const response = await api.post('/admin-dashboard/lottery-winners/', { action: 'delete', id })
  return response.data
}

export async function getPushVapidKey() {
  const response = await api.get('/admin-dashboard/push/vapid-key/')
  return response.data?.public_key || ''
}

export async function pushSubscribe(subscription) {
  const response = await api.post('/admin-dashboard/push/subscribe/', { subscription })
  return response.data
}

export async function pushUnsubscribe(endpoint) {
  const response = await api.post('/admin-dashboard/push/unsubscribe/', { endpoint })
  return response.data
}


export async function uploadPrizeImage(file) {
  const form = new FormData()
  form.append('image', file)
  const response = await api.post('/admin-dashboard/lottery-prize-image/', form)
  return response.data
}

export default api
