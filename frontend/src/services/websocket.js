export class WebSocketService {
  /**
   * @param {number|string} gameId
   * @param {{ role?: 'player'|'watcher' }} [options] - role=player if user has a card, role=watcher if only watching (room separation for scaling)
   */
  constructor(gameId, options = {}) {
    this.gameId = gameId
    this._intentionalDisconnect = false
    this.role = options.role || null
    this.ws = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.listeners = {}
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    
    let host
    if (import.meta.env.VITE_WS_URL) {
      host = import.meta.env.VITE_WS_URL.replace('ws://', '').replace('wss://', '')
    } else if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      host = window.location.host
    } else {
      host = 'localhost:8000'
    }
    
    let url = `${protocol}//${host}/ws/game/${this.gameId}/`
    if (this.role === 'player' || this.role === 'watcher') {
      url += `?role=${this.role}`
    }
    
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
      if (!this._intentionalDisconnect) {
        this.reconnect()
      }
      this._intentionalDisconnect = false
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

    // Backend may send batched events (batch_events) - process each so number_called appears sequentially
    if (type === 'batch_events' && messageData && Array.isArray(messageData.events)) {
      // winner_declared must run before game_ended (fake winner sets _pendingFakeWinnerDeclaration first)
      const rank = (t) => {
        if (t === 'winner_declared') return 0
        if (t === 'game_ended') return 1
        return 2
      }
      const events = [...messageData.events].sort((a, b) => {
        const ta = a.type || a.event_type || ''
        const tb = b.type || b.event_type || ''
        return rank(ta) - rank(tb)
      })
      events.forEach((evt) => {
        const evType = evt.type || evt.event_type
        const evData = evt.data || evt
        if (evType === 'number_called') {
          this.emit('number_called', evData)
        } else if (evType === 'winner_declared') {
          this.emit('winner_declared', evData)
        } else if (evType === 'game_ended') {
          this.emit('game_ended', evData)
        } else if (evType === 'game_started') {
          this.emit('game_started', evData)
        } else if (evType === 'card_selected') {
          this.emit('card_selected', evData)
        }
      })
      return
    }
    
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
      case 'game_cancelled':
        this.emit('game_cancelled', messageData)
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
      this._intentionalDisconnect = true
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

