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

const API_BASE_URL = getApiUrl()

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Add token to requests if available
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
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

export async function restartGame() {
  const response = await api.post('/admin/games/restart/')
  return response.data
}

export default api

