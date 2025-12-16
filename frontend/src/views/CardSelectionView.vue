<template>
  <div class="card-selection-view">
    <!-- Game Paused Overlay -->
    <div v-if="isPaused" class="game-paused-overlay">
      <div class="game-paused-content">
        <h2>⏸️ ጨዋታ ቆሟል</h2>
        <p>ለመቀጠል "Continue" ይጫኑ።</p>
        <button @click="resumeGame" class="continue-btn">Continue</button>
      </div>
    </div>
    
    <!-- Top section with timer, wallet, and bid on same row -->
    <div class="top-section" v-if="game?.status === 'waiting'">
      <div class="timer-section-top">
        <span class="timer-label-text">ለመጀመር፡</span>
        <Timer :seconds="timerSeconds" />
      </div>
      <div class="wallet-section-top">
        <span class="wallet-label">ያለዎት ገንዘብ ፡</span>
        <span class="wallet-amount">{{ userBalance || 0 }} ብር</span>
      </div>
      <div class="bet-section-top">
        <span class="bet-label">መደብ ፡</span>
        <span class="bet-amount-top">{{ game?.bet_amount || 0 }} ብር</span>
      </div>
    </div>
    
    <!-- Notification Banner -->
    <NotificationBanner
      :message="notificationMessage"
      :type="notificationType"
      @dismiss="notificationMessage = null"
    />
    
    <!-- Select card text -->
    <div class="select-card-section" v-if="game?.status === 'waiting'">
      <div class="select-card-text">ካርቴላ ይምረጡ</div>
    </div>
    
    <!-- InfoBar only shown when game is active -->
    <InfoBar
      v-if="game?.status === 'active'"
      :derash="game?.total_derash || 0"
      :players="game?.total_players || 0"
      :bet="game?.bet_amount || 0"
      :call="game?.current_call_count || 0"
    />
    <GameStatus v-if="game?.status === 'active'" :status="game?.status || 'waiting'" />
    
    <div class="timer-section" v-if="game?.status === 'active' && !selectedCard">
      <div class="timer-label">ጨዋታው ተጀምሯል - ለመቀላቀል ካርቴላ ይምረጡ:</div>
    </div>
    
    <div class="card-selector-container">
      <CardSelector
        :available-cards="availableCards"
        :taken-cards="takenCards"
        :selected-card="selectedCard"
        :total-cards="game?.total_cards || 200"
        :disabled="!isAuthenticated || !isTelegramApp"
        @select-card="handleSelectCard"
      />
      <div v-if="!isAuthenticated || !isTelegramApp" class="view-only-notice">
        <p>⚠️ እባክዎ ይህንን ጨዋታ ለመጫወት ከቴሌግራም ቦት ይክፈቱ።</p>
        <p>አሁን ማየት ብቻ ይችላሉ።</p>
      </div>
    </div>
    
    <!-- Selected card display at bottom -->
    <div class="selected-card-section" v-if="selectedCard && userCard">
      <div class="selected-card-header">
        <h3>የተመረጠዎ ካርድ #{{ selectedCard }}</h3>
      </div>
      <UserCard
        :card-layout="userCard.card_layout"
        :card-number="userCard.card_number"
        :can-claim-bingo="false"
        :hide-bingo-button="true"
        class="selected-card-display compact"
      />
    </div>
  </div>
</template>

<script>
import InfoBar from '../components/InfoBar.vue'
import GameStatus from '../components/GameStatus.vue'
import CardSelector from '../components/CardSelector.vue'
import Timer from '../components/Timer.vue'
import UserCard from '../components/UserCard.vue'
import NotificationBanner from '../components/NotificationBanner.vue'
import { getCurrentGame, getAvailableCards, selectCard, getMyCard, getUserBalance, startGame } from '../services/api'
import { WebSocketService } from '../services/websocket'

export default {
  name: 'CardSelectionView',
  components: {
    InfoBar,
    GameStatus,
    CardSelector,
    Timer,
    UserCard,
    NotificationBanner
  },
  data() {
    return {
      game: null,
      availableCards: [],
      takenCards: [],
      selectedCard: null,
      userCard: null,
      userBalance: 0,
      ws: null,
      wsConnected: false, // Track WebSocket connection state
      timerSeconds: 30, // Will be set from game.card_selection_timer
      timerInterval: null,
      startingGame: false,
      isRedirecting: false,
      notificationMessage: null,
      notificationType: 'info',
      isAuthenticated: false,
      isTelegramApp: false,
      isPaused: false,
      visibilityHandler: null,
    }
  },
  async mounted() {
    console.log('🎮 CardSelectionView mounted')
    
    // Check if running in Telegram Web App
    this.isTelegramApp = !!(window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData)
    
    // If in Telegram but not authenticated, try to authenticate
    if (this.isTelegramApp && !localStorage.getItem('auth_token')) {
      const { getInitData } = await import('../services/telegram')
      const { registerTelegram } = await import('../services/api')
      const initData = getInitData()
      if (initData && typeof initData === 'string' && initData.length > 0) {
        try {
          await registerTelegram(initData)
          console.log('✅ Authentication successful in CardSelectionView')
        } catch (error) {
          console.error('❌ Authentication failed in CardSelectionView:', error)
        }
      }
    }
    
    // Check authentication
    try {
      await this.loadUserBalance()
      this.isAuthenticated = true
    } catch (error) {
      this.isAuthenticated = false
      if (!this.isTelegramApp) {
        this.showNotification('እባክዎ ይህንን ጨዋታ ለመጫወት ከቴሌግራም ቦት ይክፈቱ።', 'warning')
      } else {
        // In Telegram but authentication failed - show error
        this.showNotification('የማረጋገጫ ስህተት። እባክዎ ገጹን ያድሱ።', 'error')
      }
    }
    
    await this.loadGame()
    this.setupWebSocket()
    // Only start polling if WebSocket is not connected (fallback)
    if (!this.wsConnected) {
      this.startPolling()
    }
    
    // Start timer after a short delay to ensure game is loaded
    this.$nextTick(() => {
      // Start timer if game is waiting (even if user has a card - they need to see when game starts)
      if (this.game && this.game.status === 'waiting' && !this.timerInterval) {
        console.log('🎮 Initial timer start - game status:', this.game.status, 'selectedCard:', this.selectedCard)
        this.startTimer()
      } else {
        console.log('🎮 Timer not started initially - game:', this.game?.status, 'selectedCard:', this.selectedCard, 'timerInterval:', this.timerInterval)
      }
    })
    
    // Setup visibility change handler for pause detection
    this.visibilityHandler = () => {
      if (document.hidden) {
        this.isPaused = true
      }
    }
    document.addEventListener('visibilitychange', this.visibilityHandler)
  },
  beforeUnmount() {
    if (this.interval) {
      clearInterval(this.interval)
    }
    if (this.timerInterval) {
      clearInterval(this.timerInterval)
    }
    if (this.ws) {
      this.ws.disconnect()
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
    }
  },
  methods: {
    async loadUserBalance() {
      try {
        const balanceData = await getUserBalance()
        console.log('Balance data received:', balanceData)
        // Handle both response formats: {balance: X} or just the number
        if (typeof balanceData === 'number') {
          this.userBalance = balanceData
        } else if (balanceData && typeof balanceData.balance !== 'undefined') {
          this.userBalance = parseFloat(balanceData.balance) || 0
        } else {
          this.userBalance = 0
        }
        console.log('User balance set to:', this.userBalance)
      } catch (error) {
        // 401 or 403 errors are expected for unauthenticated users - use default balance
        if (error.response?.status === 401 || error.response?.status === 403) {
          console.log('User not authenticated, using default balance')
          this.isAuthenticated = false
        } else {
          console.error('Error loading user balance:', error)
          console.error('Error response:', error.response?.data)
        }
        // Default balance for unauthenticated users
        this.userBalance = 0
      }
    },
    async loadGame() {
      try {
        const game = await getCurrentGame()
        this.game = game
        
        // Update timer seconds from game settings if available
        if (game && game.card_selection_timer && !this.timerInterval) {
          this.timerSeconds = game.card_selection_timer
        }
        
        // Refresh balance when game loads (in case it changed)
        if (this.isAuthenticated) {
          await this.loadUserBalance()
        }
        
        if (game) {
          // Check if user already has a card for this game
          try {
            const myCard = await getMyCard(game.id)
            if (myCard) {
              this.selectedCard = myCard.card_number
              this.userCard = myCard
              // User already has a card
              // If game is active, redirect to game view
              if (game.status === 'active') {
                if (this.interval) {
                  clearInterval(this.interval)
                  this.interval = null
                }
                if (this.timerInterval) {
                  clearInterval(this.timerInterval)
                  this.timerInterval = null
                }
                this.$router.push('/game')
                return
              }
            } else {
              this.userCard = null
            }
          } catch (error) {
            // User doesn't have a card yet, that's fine
            this.selectedCard = null
            this.userCard = null
          }
          
          const available = await getAvailableCards(game.id)
          this.availableCards = available.available_cards || []
          
          // Calculate taken cards using total_cards from game settings
          const totalCards = game.total_cards || 200
          const allCards = Array.from({ length: totalCards }, (_, i) => i + 1)
          this.takenCards = allCards.filter(num => !this.availableCards.includes(num))
          
          // Redirect if game status changes - but only if user has a card
          // If game is active and user has a card, redirect to game view
          // If game is active but user has NO card, allow them to select a card
          if (game.status === 'active' && !this.isRedirecting && this.selectedCard) {
            // User has a card and game is active - redirect to game view
            // Clear timer and interval if game becomes active
            if (this.timerInterval) {
              clearInterval(this.timerInterval)
              this.timerInterval = null
            }
            if (this.interval) {
              clearInterval(this.interval)
              this.interval = null
            }
            // Set redirecting flag
            this.isRedirecting = true
            // Redirect immediately
            this.$router.push('/game').catch(() => {
              // Ignore navigation errors
            })
            return // Stop further execution
          }
          // If game is active but user has no card, stay on card selection page (no timer needed)
          // Timer should only run when game is waiting
          else if (game.status === 'completed' && !this.isRedirecting) {
            // Clear timer if game is completed
            if (this.timerInterval) {
              clearInterval(this.timerInterval)
              this.timerInterval = null
            }
            if (this.interval) {
              clearInterval(this.interval)
              this.interval = null
            }
            this.isRedirecting = true
            this.$router.push('/completed').catch(() => {
              // Ignore navigation errors
            })
            return // Stop further execution
          } else if (game.status === 'waiting') {
            // Start timer if game is waiting (user may or may not have a card - they need to see countdown)
            // CRITICAL: Only start if timer is not already running
            // Don't reset timer if it's already counting down!
            if (!this.timerInterval) {
              console.log('🎮 Game is waiting, starting timer (user has card:', this.selectedCard, ')')
              this.startTimer()
            } else {
              // Timer is running - DO NOT RESTART IT!
              // Just verify it's still counting (don't log every time to reduce spam)
              const expectedTimerValue = this.game?.card_selection_timer || 30
              if (this.timerSeconds === expectedTimerValue && this.timerSeconds > 0) {
                console.warn('⚠️ Timer stuck at initial value! Restarting...')
                clearInterval(this.timerInterval)
                this.timerInterval = null
                this.startTimer()
              }
            }
            // Don't reset timer if it's already running - let it count down
          } else if (game.status === 'active' && !this.selectedCard) {
            console.log('🎮 Game is active but user has no card - clearing timer')
            // Game is active but user has no card - clear timer if running
            // No timer needed for active games
            if (this.timerInterval) {
              console.log('Game is active, clearing timer')
              clearInterval(this.timerInterval)
              this.timerInterval = null
            }
            // Reset timer display to show no countdown
            this.timerSeconds = 0
          }
        }
      } catch (error) {
        console.error('Error loading game:', error)
      }
    },
    setupWebSocket() {
      if (!this.game) return
      
      this.ws = new WebSocketService(this.game.id)
      
      this.ws.on('connected', () => {
        console.log('WebSocket connected successfully in CardSelectionView')
        this.wsConnected = true
        // Stop polling when WebSocket connects
        this.stopPolling()
      })
      
      this.ws.on('disconnected', () => {
        console.log('WebSocket disconnected in CardSelectionView')
        this.wsConnected = false
        // Resume polling when WebSocket disconnects
        this.startPolling()
      })
      
      this.ws.connect()
      
      this.ws.on('card_selected', (data) => {
        // Update taken cards IMMEDIATELY in real-time (optimistic update)
        console.log('Card selected/unselected via WebSocket:', data)
        
        // Handle card unselection (card_number is None)
        if (data.card_number === null || data.card_number === undefined) {
          // Card was unselected - refresh game data to get updated derash and player count
          this.loadGame()
          // Update available cards if provided
          if (data.available_cards) {
            this.availableCards = data.available_cards
            const totalCards = this.game?.total_cards || 200
            const allCards = Array.from({ length: totalCards }, (_, i) => i + 1)
            this.takenCards = allCards.filter(num => !this.availableCards.includes(num))
            this.$forceUpdate()
          }
          return
        }
        
        // Handle card selection
        // Use Vue.set or direct assignment for immediate reactivity
        if (data.card_number && !this.takenCards.includes(data.card_number)) {
          this.takenCards.push(data.card_number)
          this.availableCards = this.availableCards.filter(num => num !== data.card_number)
          // Force immediate UI update
          this.$forceUpdate()
          console.log(`Card ${data.card_number} is now taken`)
        }
        // Also update available cards list if provided (most up-to-date from server)
        if (data.available_cards) {
          this.availableCards = data.available_cards
          const totalCards = this.game?.total_cards || 200
          const allCards = Array.from({ length: totalCards }, (_, i) => i + 1)
          this.takenCards = allCards.filter(num => !this.availableCards.includes(num))
          // Force immediate UI update
          this.$forceUpdate()
        }
        
        // Refresh game data to get updated derash and player count
        this.loadGame()
      })
      
      this.ws.on('game_started', () => {
        // Clear timer and interval if game starts
        if (this.timerInterval) {
          clearInterval(this.timerInterval)
          this.timerInterval = null
        }
        if (this.interval) {
          clearInterval(this.interval)
          this.interval = null
        }
        // Set redirecting flag
        this.isRedirecting = true
        // Redirect immediately
        this.$router.push('/game').catch(() => {
          // Ignore navigation errors
        })
      })
    },
    startPolling() {
      // Only start polling if WebSocket is not connected and interval is not already running
      if (!this.wsConnected && !this.interval) {
        console.log('Starting HTTP polling in CardSelectionView (WebSocket not connected)')
        this.interval = setInterval(this.loadGame, 1000) // Poll every 1 second
      }
    },
    stopPolling() {
      // Stop polling when WebSocket is connected
      if (this.interval) {
        console.log('Stopping HTTP polling in CardSelectionView (WebSocket connected)')
        clearInterval(this.interval)
        this.interval = null
      }
    },
    startTimer() {
      // Only start timer if not already running
      if (this.timerInterval) {
        console.log('⏱️ Timer already running, skipping start. Current:', this.timerSeconds)
        return // Timer already running - don't reset it!
      }
      
      // Get timer value from game settings, default to 30 if not available
      const timerValue = this.game?.card_selection_timer || 30
      this.timerSeconds = timerValue
      console.log('⏱️ Starting timer from', this.timerSeconds, 'seconds (from settings)')
      
      // Use arrow function to preserve 'this' context
      this.timerInterval = setInterval(() => {
        // Check if timer is still valid
        if (!this.timerInterval) {
          console.log('⏱️ Timer interval was cleared, stopping')
          return
        }
        
        if (this.timerSeconds > 0) {
          this.timerSeconds--
          // Only log every 5 seconds to reduce console spam
          if (this.timerSeconds % 5 === 0 || this.timerSeconds <= 5) {
            console.log('⏱️ Timer tick:', this.timerSeconds, 'seconds remaining')
          }
        } else {
          // Timer ended, start game immediately (countdown will show in ActiveGameView)
          console.log('⏱️ Timer reached 0, starting game immediately!')
          clearInterval(this.timerInterval)
          this.timerInterval = null
          this.startGame()
        }
      }, 1000)
      
      console.log('✅ Timer interval created:', this.timerInterval)
    },
    async startGame() {
      if (!this.game) return
      
      // Prevent multiple calls
      if (this.startingGame) {
        return
      }
      this.startingGame = true
      
      // Stop the periodic loadGame calls
      if (this.interval) {
        clearInterval(this.interval)
        this.interval = null
      }
      
      try {
        // Call API to start game using the API service
        console.log('Calling start game API for game:', this.game.id)
        const gameData = await startGame(this.game.id)
        this.game = gameData
        
        // Update game status immediately
        this.game.status = 'active'
        
        console.log('Game started successfully:', gameData)
        
        // Set redirecting flag
        this.isRedirecting = true
        
        // Redirect immediately without delay
        this.$router.push('/game').catch(() => {
          // Ignore navigation errors (e.g., already navigating)
        })
      } catch (error) {
        console.error('Error starting game:', error)
        console.error('Error details:', error.response?.data || error.message)
        
        // Try to reload game status - maybe game was started by another user
        try {
          const game = await getCurrentGame()
          if (game.status === 'active') {
            console.log('Game is already active, redirecting')
            this.isRedirecting = true
            this.$router.push('/game').catch(() => {})
          } else if (this.selectedCard) {
            // User has a card, redirect anyway
            console.log('User has card, redirecting to game')
            this.isRedirecting = true
            this.$router.push('/game').catch(() => {})
          } else {
            // Restart interval if redirect failed (only if WS not connected)
            if (!this.wsConnected) {
              this.startPolling()
            }
            // Restart timer if game is still waiting
            if (this.game && this.game.status === 'waiting' && !this.timerInterval) {
              this.startTimer()
            }
          }
        } catch (e) {
          console.error('Error reloading game:', e)
          // If user has a card, redirect anyway
          if (this.selectedCard) {
            this.isRedirecting = true
            this.$router.push('/game').catch(() => {})
          } else {
            // Restart interval if redirect failed (only if WS not connected)
            if (!this.wsConnected) {
              this.startPolling()
            }
            // Restart timer if game is still waiting
            if (this.game && this.game.status === 'waiting' && !this.timerInterval) {
              this.startTimer()
            }
          }
        }
      } finally {
        this.startingGame = false
      }
    },
    // Helper function to create temporary card layout with all 0s
    createTemporaryCardLayout() {
      const layout = []
      const letters = ['B', 'I', 'N', 'G', 'O']
      
      for (let row = 0; row < 5; row++) {
        const layoutRow = []
        for (let col = 0; col < 5; col++) {
          // Center cell (row 2, col 2) is FREE
          if (row === 2 && col === 2) {
            layoutRow.push({
              number: null,
              letter: 'FREE',
              marked: true,
              row: row,
              col: col
            })
          } else {
            layoutRow.push({
              number: 0, // Temporary placeholder
              letter: letters[col],
              marked: false,
              row: row,
              col: col
            })
          }
        }
        layout.push(layoutRow)
      }
      
      return layout
    },
    async handleSelectCard(cardNumber) {
      if (!this.game) return
      
      // Security check: Only allow card selection if authenticated from Telegram
      if (!this.isAuthenticated || !this.isTelegramApp) {
        this.showNotification('እባክዎ ይህንን ጨዋታ ለመጫወት ከቴሌግራም ቦት ይክፈቱ። አሁን ማየት ብቻ ይችላሉ።', 'warning')
        return
      }
      
      // Check if user is unselecting the same card (allow this)
      const isUnselecting = this.selectedCard === cardNumber
      
      // Prevent selecting taken cards (unless it's the user's own card for unselection)
      if (this.takenCards.includes(cardNumber) && !isUnselecting) {
        this.showNotification('ይህ ካርቴላ ተይዟል!', 'error')
        return
      }
      
      // OPTIMISTIC UPDATE: Update UI immediately before API call
      const previousCard = this.selectedCard
      const previousUserCard = this.userCard
      
      // If selecting a new card (not unselecting)
      if (!isUnselecting) {
        // Immediately update UI - turn card green
        this.selectedCard = cardNumber
        
        // Show temporary layout with all 0s immediately
        this.userCard = {
          card_number: cardNumber,
          card_layout: this.createTemporaryCardLayout(),
          selected_numbers: [],
          is_winner: false
        }
        
        // Remove from available, add to taken
        if (!this.takenCards.includes(cardNumber)) {
          this.takenCards.push(cardNumber)
        }
        this.availableCards = this.availableCards.filter(num => num !== cardNumber)
        
        // If user had a previous card, make it available again
        if (previousCard && previousCard !== cardNumber) {
          if (this.takenCards.includes(previousCard)) {
            this.takenCards = this.takenCards.filter(num => num !== previousCard)
          }
          if (!this.availableCards.includes(previousCard)) {
            this.availableCards.push(previousCard)
            this.availableCards.sort((a, b) => a - b)
          }
        }
        
        // Force immediate UI update
        this.$forceUpdate()
      }
      
      // Then sync with backend (fire and forget for faster response)
      selectCard(this.game.id, cardNumber)
        .then(response => {
          // Check if this was an unselection
          if (response.unselected) {
            // Card was unselected and refunded
            this.selectedCard = null
            this.userCard = null
            
            // Update balance from response
            if (response.balance !== undefined) {
              this.userBalance = response.balance
            } else {
              this.loadUserBalance()
            }
            
            // Make the card available again
            if (this.takenCards.includes(cardNumber)) {
              this.takenCards = this.takenCards.filter(num => num !== cardNumber)
            }
            if (!this.availableCards.includes(cardNumber)) {
              this.availableCards.push(cardNumber)
              this.availableCards.sort((a, b) => a - b)
            }
            
            // Refresh game data to get updated derash and player count
            this.loadGame()
          
            this.$forceUpdate()
            return
          }
          
          // Card was selected - update with server response (real layout)
          this.selectedCard = cardNumber
          this.userCard = response // This contains the real card layout from server
          
          // Update balance from response
          if (response.balance !== undefined) {
            this.userBalance = response.balance
          } else {
            this.loadUserBalance()
          }
          
          // Update available cards from server response (most accurate)
          if (response.available_cards) {
            this.availableCards = response.available_cards
            const totalCards = this.game?.total_cards || 200
            const allCards = Array.from({ length: totalCards }, (_, i) => i + 1)
            this.takenCards = allCards.filter(num => !this.availableCards.includes(num))
          }
          
          this.$forceUpdate()
        })
        .catch(error => {
          // Revert optimistic update on error
          if (!isUnselecting) {
            this.selectedCard = previousCard
            this.userCard = previousUserCard // Restore previous card or null
            
            // Revert taken/available cards
            if (this.takenCards.includes(cardNumber)) {
              this.takenCards = this.takenCards.filter(num => num !== cardNumber)
            }
            if (!this.availableCards.includes(cardNumber)) {
              this.availableCards.push(cardNumber)
              this.availableCards.sort((a, b) => a - b)
            }
            
            // Restore previous card if it existed
            if (previousCard && previousCard !== cardNumber) {
              if (!this.takenCards.includes(previousCard)) {
                this.takenCards.push(previousCard)
              }
              this.availableCards = this.availableCards.filter(num => num !== previousCard)
            }
            
            this.$forceUpdate()
          }
          
          const errorMsg = error.response?.data?.error || 'Failed to select card'
          this.showNotification(errorMsg, 'error')
        })
      
      // If game is active and user just selected a card, redirect to game view
      if (this.game.status === 'active' && !isUnselecting) {
        // Clear intervals
        if (this.interval) {
          clearInterval(this.interval)
          this.interval = null
        }
        if (this.timerInterval) {
          clearInterval(this.timerInterval)
          this.timerInterval = null
        }
        // Redirect to game view
        this.isRedirecting = true
        this.$router.push('/game').catch(() => {})
      }
    },
    showNotification(message, type = 'info') {
      this.notificationMessage = message
      this.notificationType = type
    },
    resumeGame() {
      this.isPaused = false
      // Refresh the page to restore current state
      window.location.reload()
    }
  }
}
</script>

<style scoped>
.card-selection-view {
  min-height: 100vh;
  background: var(--purple-light);
  position: relative;
  display: flex;
  flex-direction: column;
}

.top-section {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.95);
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  flex-wrap: nowrap;
  min-width: 0;
  gap: 10px;
}

.timer-section-top {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  min-width: 0;
  overflow: hidden;
}

.timer-section-top :deep(.timer) {
  flex-shrink: 0;
}

.timer-label-text {
  font-size: 11px;
  font-weight: bold;
  color: var(--purple-dark);
  white-space: nowrap;
  flex-shrink: 0;
}

.wallet-section-top {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1 1 auto;
  justify-content: center;
  min-width: 0;
}

.wallet-label {
  font-size: 11px;
  font-weight: bold;
  color: var(--purple-dark);
  white-space: nowrap;
}

.wallet-amount {
  font-size: 11px;
  font-weight: bold;
  color: var(--green);
  white-space: nowrap;
}

.bet-section-top {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  min-width: 0;
}

.bet-label {
  font-size: 11px;
  font-weight: bold;
  color: var(--purple-dark);
  white-space: nowrap;
}

.bet-amount-top {
  font-size: 11px;
  font-weight: bold;
  color: var(--orange);
  white-space: nowrap;
}

.select-card-section {
  position: fixed;
  top: 45px; /* Adjust this value to change position below top section */
  left: 0;
  right: 0;
  padding: 8px;
  text-align: center;
  background: var(--purple-light);
  z-index: 99;
}

.select-card-text {
  font-size: 16px;
  font-weight: bold;
  color: var(--purple-dark);
  margin: 0;
}

.card-selector-container {
  position: fixed;
  top: 80px; /* Adjust this value - Start below top section and select card text */
  left: 0;
  right: 0;
  bottom: 40vh; /* Adjust this value - Leave space for selected card at bottom */
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px;
  background: var(--purple-light);
  z-index: 10;
}

.timer-section {
  text-align: center;
  padding: 20px;
  background: white;
  margin: 10px;
  border-radius: 10px;
}

.timer-label {
  font-size: 18px;
  font-weight: bold;
  color: var(--purple-dark);
  margin-bottom: 10px;
}

/* ============================================
   SELECTED CARD SECTION POSITION ADJUSTMENTS
   ============================================
   To adjust the position of the selected card section, modify these values:
   
   - bottom: 0          → Change to move up/down (e.g., bottom: 20px moves it up)
   - height: 40vh       → Change to make taller/shorter (e.g., 35vh or 45vh)
   - max-height: 40vh   → Should match height value
   - padding: 20px       → Change to adjust internal spacing
   ============================================ */
.selected-card-section {
  position: fixed;
  top: 90%; /* Change this to move the section up/down (e.g., bottom: 10px) */
  left: 0;
  right: 0;
  background: rgb(115, 69, 133);
  padding:0px; /* Adjust this to change internal spacing */
  border-top: 3px solid var(--purple-medium);
  box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
  z-index: 50;
  height: 20px; /* Adjust this to change height (e.g., 35vh, 45vh) */
  max-height: 40vh; /* Should match height value above */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.selected-card-header {
  text-align: center;
  margin-bottom: 5px;
  flex-shrink: 0;
}

.selected-card-header h3 {
  margin: 0;
  font-size: 12px;
  color: var(--purple-dark);
}

.selected-card-display.compact {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  overflow: visible;
  position: relative;
}

.selected-card-display.compact :deep(.user-card) {
  transform: scale(1.2);
}

.game-paused-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.game-paused-content {
  background: white;
  padding: 40px;
  border-radius: 15px;
  text-align: center;
  max-width: 400px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.game-paused-content h2 {
  margin: 0 0 20px 0;
  color: #e74c3c;
  font-size: 24px;
}

.game-paused-content p {
  margin: 0 0 30px 0;
  color: #333;
  font-size: 16px;
  line-height: 1.6;
}

.continue-btn {
  background: #3498db;
  color: white;
  padding: 12px 30px;
  font-size: 18px;
  font-weight: bold;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.3s;
}

.continue-btn:hover {
  background: #2980b9;
}

.selected-card-display.compact :deep(.card-cell) {
  font-size: 25px;
  min-height: 25px;
}

.selected-card-display.compact :deep(.card-number) {
  font-size: 25px;
}

.selected-card-display.compact :deep(.letter-cell) {
  font-size: 25px;
  min-height: 25px;
}
</style>

