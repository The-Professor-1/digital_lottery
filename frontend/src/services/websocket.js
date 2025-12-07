export class WebSocketService {
  constructor(gameId) {
    this.gameId = gameId
    this.ws = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.listeners = {}
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    
    // Auto-detect WebSocket URL based on current host (same logic as API service)
    let host
    if (import.meta.env.VITE_WS_URL) {
      // Use explicit WebSocket URL if set
      host = import.meta.env.VITE_WS_URL.replace('ws://', '').replace('wss://', '')
    } else if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      // Production: use same origin as the web app
      host = window.location.host
    } else {
      // Development: use localhost:8000
      host = 'localhost:8000'
    }
    
    const url = `${protocol}//${host}/ws/game/${this.gameId}/`
    
    console.log('🔌 Connecting to WebSocket:', url)
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('WebSocket connected')
      this.reconnectAttempts = 0
      this.emit('connected')
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // Handle message immediately without any delays
        this.handleMessage(data)
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      this.emit('error', error)
    }

    this.ws.onclose = () => {
      console.log('WebSocket disconnected')
      this.emit('disconnected')
      this.reconnect()
    }
  }

  reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
      console.log(`Reconnecting in ${delay}ms...`)
      setTimeout(() => this.connect(), delay)
    }
  }

  handleMessage(data) {
    const { type, data: messageData } = data
    
    switch (type) {
      case 'number_called':
        this.emit('number_called', messageData)
        break
      case 'card_selected':
        this.emit('card_selected', messageData)
        break
      case 'game_started':
        this.emit('game_started', messageData)
        break
      case 'game_ended':
        this.emit('game_ended', messageData)
        break
      case 'winner_declared':
        this.emit('winner_declared', messageData)
        break
      case 'admin_message':
        this.emit('admin_message', messageData)
        break
      default:
        this.emit('message', data)
    }
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = []
    }
    this.listeners[event].push(callback)
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback)
    }
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => callback(data))
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.listeners = {}
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN
  }

  get connected() {
    return this.isConnected()
  }
}

