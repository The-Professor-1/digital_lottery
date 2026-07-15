import axios from 'axios'

// Auto-detect API URL based on current host
const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }
  // In production (Telegram web app), use same origin
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `${window.location.origin}/api`
  }
  // Development fallback
  return 'http://localhost:8000/api'
}

// Admin dashboard and secondadmin are mounted at site root in Django (not under /api/)
const getAdminApiBaseUrl = () => {
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return window.location.origin
  }
  return 'http://localhost:8000'
}

const API_BASE_URL = getApiUrl()

// Create axios instance for /api/ endpoints
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  withCredentials: true, // Important for Django session cookies and CSRF
})

// Axios instance for admin-dashboard and secondadmin (mounted at root, not under /api/)
const adminApi = axios.create({
  baseURL: getAdminApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  withCredentials: true,
})
adminApi.interceptors.request.use((config) => {
  const csrfToken = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrftoken='))
    ?.split('=')[1]
  if (csrfToken) {
    config.headers['X-CSRFToken'] = csrfToken
  }
  // Let the browser set multipart boundary for FormData (default JSON Content-Type breaks save/uploads)
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
adminApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && typeof error.response.data === 'string' && error.response.data.trim().startsWith('<')) {
      console.error('Admin API received HTML instead of JSON:', error.response.data.substring(0, 200))
      error.response.data = {
        error: 'Server returned HTML instead of JSON. This may be a CSRF or authentication error.',
        status: error.response.status,
        message: 'Please log in to the admin dashboard and try again.'
      }
    }
    return Promise.reject(error)
  }
)

// Add token and CSRF to requests
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // CSRF for session-based admin requests (Django)
  const csrfToken = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrftoken='))
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

// Handle response errors - ensure we always get JSON
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If response data is HTML (starts with <), convert to JSON error
    if (error.response && typeof error.response.data === 'string' && error.response.data.trim().startsWith('<')) {
      console.error('Received HTML instead of JSON:', error.response.data.substring(0, 200))
      error.response.data = {
        error: 'Server returned HTML instead of JSON. This may be a CSRF or authentication error.',
        status: error.response.status,
        message: 'Please refresh the page and try again.'
      }
    }
    return Promise.reject(error)
  }
)

// Get token from URL or localStorage
function getToken() {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get('token') || localStorage.getItem('auth_token')
}

// Store token
function setToken(token) {
  localStorage.setItem('auth_token', token)
}

// Auth
export async function authenticateTelegram(token) {
  try {
    const response = await api.post('/auth/telegram/', { token })
    if (response.data.token) {
      setToken(response.data.token)
    }
    return response.data
  } catch (error) {
    console.error('Auth error:', error)
    throw error
  }
}

// Register/authenticate with Telegram Web App initData
export async function registerTelegram(initData) {
  try {
    const response = await api.post('/auth/telegram-register/', { 
      initData: initData 
    })
    if (response.data.token) {
      setToken(response.data.token)
    }
    return response.data
  } catch (error) {
    console.error('Telegram registration error:', error)
    throw error
  }
}

// User
export async function getCurrentUser() {
  const response = await api.get('/users/me/')
  return response.data
}

// Update user phone number
export async function updateUserPhone(phoneNumber) {
  const response = await api.post('/users/phone/', { phone_number: phoneNumber })
  return response.data
}

export async function getUserBalance() {
  const response = await api.get('/users/balance/')
  return response.data
}

// Games
export async function getCurrentGame() {
  const response = await api.get('/games/current/')
  return response.data
}

export async function getGame(gameId) {
  const response = await api.get(`/games/${gameId}/`)
  return response.data
}

export async function selectCard(gameId, cardNumber) {
  const response = await api.post(`/games/${gameId}/select_card/`, {
    card_number: cardNumber
  })
  return response.data
}

export async function getMyCard(gameId) {
  const response = await api.get(`/games/${gameId}/my_card/`)
  return response.data
}

export async function getAvailableCards(gameId) {
  const response = await api.get(`/games/${gameId}/available_cards/`)
  return response.data
}

// Cards
export async function getCard(cardId) {
  const response = await api.get(`/cards/${cardId}/`)
  return response.data
}

export async function markNumber(cardId, number) {
  const response = await api.post(`/cards/${cardId}/mark_number/`, {
    number
  })
  return response.data
}

export async function claimBingo(cardId) {
  const response = await api.post(`/cards/${cardId}/claim_bingo/`)
  return response.data
}

export async function updateGameMode(cardId, mode) {
  const response = await api.post(`/cards/${cardId}/update_mode/`, {
    mode
  })
  return response.data
}

// Deposits
export async function submitDeposit(amount, bankText) {
  const response = await api.post('/users/deposit/', {
    amount,
    bank_text: bankText
  })
  return response.data
}

// Withdrawals
export async function requestWithdraw(amount) {
  const response = await api.post('/users/withdraw/', {
    amount
  })
  return response.data
}

// Admin actions
export async function startGame(gameId) {
  const response = await api.post(`/admin/games/${gameId}/start/`)
  return response.data
}

export async function restartGame(params = {}) {
  const response = await api.post('/admin/games/restart/', params)
  return response.data
}

export async function callNumber(gameId, number) {
  const response = await api.post(`/admin/games/${gameId}/call-number/`, { number })
  return response.data
}

export async function endGame(gameId, options = {}) {
  const { force = false } = options
  const response = await api.post(`/admin/games/${gameId}/end/`, { force })
  return response.data
}

export async function sendTelegramBroadcast(message, amount = 0, target = 'broadcast') {
  const response = await api.post('/admin/send-telegram-message/', { message, amount, target })
  return response.data
}

export async function sendIndividualMessage(phoneOrId, message) {
  const body = { message }
  const trimmed = String(phoneOrId || '').trim()
  if (/^\d+$/.test(trimmed)) {
    body.user_id = trimmed
  } else {
    body.phone_number = trimmed
  }
  const response = await api.post('/admin/send-individual-message/', body)
  return response.data
}

export async function deleteBroadcast(broadcastId) {
  const response = await api.post(`/admin/broadcasts/${broadcastId}/delete/`)
  return response.data
}

// Admin user management (uses /api/ routes)
export async function getAdminUserDetail(userId) {
  const response = await api.get(`/admin/users/${userId}/`)
  return response.data
}

export async function editAdminUser(userId, payload) {
  const response = await api.put(`/admin/users/${userId}/edit/`, payload)
  return response.data
}

export async function deleteAdminUsers(userIds) {
  const response = await api.post('/admin/users/delete/', { user_ids: userIds })
  return response.data
}

// Admin Dashboard APIs — lottery admin uses /api/ prefix so nginx + JSON errors work reliably
export async function adminDashboardLogin(username, password) {
  const response = await api.post('/admin-dashboard/login/', { username, password })
  return response.data
}

export async function lotteryAdminBootstrap() {
  const response = await api.get('/admin-dashboard/lottery-bootstrap/')
  return response.data
}

export async function getAdminDashboardData(params = {}) {
  const response = await adminApi.get('/admin-dashboard/api/', { params })
  return response.data
}

export async function refreshDepositsWithdrawals() {
  const response = await adminApi.get('/admin-dashboard/api/refresh-deposits-withdrawals/')
  return response.data
}

export async function searchUser(query) {
  const response = await adminApi.get('/admin-dashboard/search-user/', { params: { phone: query } })
  return response.data
}

export async function updateUserBalance(userId, unwithdrawableBalance, withdrawableBalance, withdrawalApproved = undefined, freePlayAllowed = undefined) {
  const body = {
    unwithdrawable_balance: unwithdrawableBalance,
    withdrawable_balance: withdrawableBalance
  }
  if (withdrawalApproved !== undefined) body.withdrawal_approved = !!withdrawalApproved
  if (freePlayAllowed !== undefined) body.free_play_allowed = !!freePlayAllowed
  const response = await adminApi.post(`/admin-dashboard/users/${userId}/balance/`, body)
  return response.data
}

export async function searchTransaction(tx) {
  const response = await adminApi.get('/admin-dashboard/search-transaction/', { params: { tx: tx || undefined, transaction_number: tx || undefined } })
  return response.data
}

export async function approveDeposit(depositId, transactionNumber = null) {
  const body = transactionNumber ? { transaction_number: transactionNumber } : {}
  const response = await adminApi.post(`/admin-dashboard/deposits/${depositId}/approve/`, body)
  return response.data
}

export async function rejectDeposit(depositId) {
  const response = await adminApi.post(`/admin-dashboard/deposits/${depositId}/reject/`)
  return response.data
}

/** Delete multiple pending deposit requests (same as reject/delete per row). */
export async function bulkDeletePendingDeposits(ids) {
  const response = await adminApi.post('/admin-dashboard/deposits/pending/bulk-delete/', { ids })
  return response.data
}

export async function deleteFailedDeposit(failedId) {
  const response = await adminApi.post(`/admin-dashboard/failed-deposits/${failedId}/delete/`)
  return response.data
}

/** Delete multiple failed deposit records (same as Delete per row). */
export async function bulkDeleteFailedDeposits(ids) {
  const response = await adminApi.post('/admin-dashboard/failed-deposits/bulk-delete/', { ids })
  return response.data
}

export async function approveFailedDeposit(failedId, transactionNumber = null) {
  const body = transactionNumber ? { transaction_number: transactionNumber, reference: transactionNumber } : {}
  const response = await adminApi.post(`/admin-dashboard/failed-deposits/${failedId}/approve/`, body)
  return response.data
}

export async function addCbeReceiptRef(transactionNumber) {
  const response = await adminApi.post('/admin-dashboard/cbe-receipt-ref/add/', { transaction_number: transactionNumber })
  return response.data
}

export async function deleteCbeReceiptRef(transactionNumber) {
  const response = await adminApi.post('/admin-dashboard/cbe-receipt-ref/delete/', { transaction_number: transactionNumber })
  return response.data
}

export async function addTelebirrReceiptRef(reference) {
  const response = await adminApi.post('/admin-dashboard/telebirr-receipt-ref/add/', { reference })
  return response.data
}

export async function deleteTelebirrReceiptRef(reference) {
  const response = await adminApi.post('/admin-dashboard/telebirr-receipt-ref/delete/', { reference })
  return response.data
}

export async function getDepositPhoto(depositId) {
  const response = await adminApi.get(`/admin-dashboard/deposits/${depositId}/photo/`)
  return response.data
}

// Withdraw actions use api (baseURL /api) so they hit /api/admin-dashboard/withdraws/... (same as dashboard data when using /api)
export async function approveWithdraw(withdrawId) {
  const id = parseInt(withdrawId, 10)
  const response = await api.post(`/admin-dashboard/withdraws/${id}/approve/`)
  return response.data
}

export async function rejectWithdraw(withdrawId) {
  const id = parseInt(withdrawId, 10)
  const response = await api.post(`/admin-dashboard/withdraws/${id}/reject/`)
  return response.data
}

export async function deleteWithdraw(withdrawId) {
  const id = parseInt(withdrawId, 10)
  const response = await api.post(`/admin-dashboard/withdraws/${id}/delete/`)
  return response.data
}

/** Delete multiple pending withdraw requests (same as Delete per row; no user notification). */
export async function bulkDeletePendingWithdraws(ids) {
  const response = await api.post('/admin-dashboard/withdraws/pending/bulk-delete/', { ids })
  return response.data
}

export async function getGameSettings() {
  const response = await adminApi.get('/admin-dashboard/settings/')
  return response.data
}

export async function updateGameSettings(settings) {
  const response = await adminApi.post('/admin-dashboard/settings/', settings)
  return response.data
}

export async function getSecondAdminCredentials() {
  const response = await adminApi.get('/admin-dashboard/second-admin-credentials/')
  return response.data
}

export async function saveSecondAdminCredentials(username, password) {
  const response = await adminApi.post('/admin-dashboard/second-admin-credentials/', { username, password })
  return response.data
}

// Second Admin APIs
export async function secondAdminLogin(username, password) {
  const response = await adminApi.post('/secondadmin/login/', { username, password })
  return response.data
}

export async function secondAdminLogout() {
  const response = await adminApi.post('/secondadmin/logout/')
  return response.data
}

export async function getSecondAdminDashboardData() {
  const response = await adminApi.get('/secondadmin/api/')
  return response.data
}

export async function refreshSecondAdminDepositsWithdrawals() {
  const response = await adminApi.get('/secondadmin/api/refresh-deposits-withdrawals/')
  return response.data
}

/** Public lottery settings for the mini-app */
export async function getLotterySettings() {
  const response = await api.get('/lottery/settings/')
  return response.data
}

export async function getLotteryMe() {
  const response = await api.get('/lottery/me/')
  return response.data
}

export async function getLotteryTickets(phone) {
  const response = await api.get('/lottery/tickets/', { params: { phone } })
  return response.data
}

export async function submitLotteryPurchase(formData) {
  const response = await api.post('/lottery/purchase/', formData, {
    transformRequest: [(data, headers) => {
      if (headers) {
        if (typeof headers.delete === 'function') headers.delete('Content-Type')
        else {
          delete headers['Content-Type']
          delete headers['content-type']
        }
      }
      return data
    }],
  })
  return response.data
}

export async function getLotterySettingsAdmin() {
  const response = await api.get('/admin-dashboard/lottery-settings/')
  return response.data
}

export async function updateLotterySettingsAdmin(payload, file = null) {
  // Always use FormData so file + nested JSON fields save reliably with session auth
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
  if (file) {
    form.append('car_image', file)
  }
  const response = await api.post('/admin-dashboard/lottery-settings/', form)
  return response.data
}

export async function getLotteryPurchasesAdmin(params = {}) {
  const response = await api.get('/admin-dashboard/lottery-purchases/', { params })
  return response.data
}

export async function lotteryPurchaseAction(id, action, note = '') {
  const response = await api.post(`/admin-dashboard/lottery-purchases/${id}/action/`, {
    action,
    note,
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

export default api

