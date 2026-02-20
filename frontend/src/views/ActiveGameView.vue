<template>
  <div class="active-game-view">
    <!-- Game Paused Overlay -->
    <div v-if="isPaused" class="game-paused-overlay">
      <div class="game-paused-content">
        <h2>⏸️ ጨዋታ ቆሟል</h2>
        <p>ለመቀጠል "Continue" ይጫኑ።</p>
        <button @click="resumeGame" class="continue-btn">Continue</button>
      </div>
    </div>
    
    <!-- Notification Banner -->
    <NotificationBanner
      :message="notificationMessage"
      :type="notificationType"
      @dismiss="notificationMessage = null"
    />
    
    <InfoBar
      :derash="game?.total_derash || 0"
      :players="game?.total_players || 0"
      :bet="game?.bet_amount || 0"
      :call="game?.current_call_count || 0"
    />
    
    <!-- Mode Selection Dropdown -->
    <div class="mode-selector" v-if="userCard && game?.automatic_mode_enabled">
      <label for="game-mode">የጨዋታ አይነት:</label>
      <select id="game-mode" v-model="gameMode" @change="handleModeChange">
        <option value="manual">Manual</option>
        <option value="automatic">Automatic</option>
      </select>
    </div>
    
    <div class="game-content">
      <!-- Bingo grid at top -->
      <div class="bingo-screen">
        <BingoGrid
          :called-numbers="calledNumbers"
          :current-number="currentCall"
        />
      </div>
      
      <!-- User card section with called number display on top -->
      <div class="user-card-section">
        <div class="game-started-text">ጨዋታው ጀምሯል</div>
        <!-- Countdown before first number -->
        <div v-if="showStartCountdown" class="start-countdown">
          <div class="countdown-number-small">{{ startCountdownSeconds }}</div>
          <div class="countdown-text-small">ቁጥሮች ለመጥራት በመጀመር ላይ...</div>
        </div>
        <NumberCallDisplay
          v-else
          :current-call="currentCall"
          :recent-calls="recentCalls"
          class="compact-call-display"
        />
        <UserCard
          v-if="userCard"
          :card-layout="userCard.card_layout"
          :card-number="userCard.card_number"
          :can-claim-bingo="canClaimBingo"
          @mark-number="handleMarkNumber"
          @claim-bingo="handleClaimBingo"
        />
        <!-- Show "wait" when no card and banner not yet shown: active game, or completed but winner not yet received, or winner declared but banner delayed (e.g. 3s for fake user) -->
        <div v-else-if="(!userCard && !showWinnerBanner) && ( (game && (game.status === 'active' || (game.status === 'completed' && !winner && (!winners || !winners.length)))) || _winnerBannerActive )" class="no-card-message">
          <div class="wait-message-box">
            <h3>⏳ ይህ ጨዋታ እስኪጠናቀቅ ይጠብቁ</h3>
          </div>
        </div>
      </div>
    </div>
    
    <!-- No Winner Message -->
    <div v-if="noWinner" class="no-winner-overlay">
      <div class="no-winner-box">
        <h2>No User Wins This Round</h2>
        <p>ሁሉም ቁጥሮች ተጠርተዋል ግን አሸናፊ የለም።</p>
        <p>ወደ ካርድ ምርጫ በመመለስ ላይ...</p>
      </div>
    </div>
    
    <WinnerBanner
      v-if="showWinnerBanner"
      :winner="winner"
      :winners="winners"
      :prize="winnerPrize"
      :total-prize="totalPrize"
      :winner-card="winnerCard"
      :is-current-user="isCurrentUserWinner"
      :winning-pattern="winnerCard?.winning_pattern || (winners && winners.length > 0 ? winners[0].winning_pattern : null)"
      :current-user-id="userCard?.user?.id"
      @redirect="handleWinnerRedirect"
    />
  </div>
</template>

<script>
import InfoBar from '../components/InfoBar.vue'
import NumberCallDisplay from '../components/NumberCallDisplay.vue'
import BingoGrid from '../components/BingoGrid.vue'
import UserCard from '../components/UserCard.vue'
import WinnerBanner from '../components/WinnerBanner.vue'
import NotificationBanner from '../components/NotificationBanner.vue'
import { getCurrentGame, getMyCard, markNumber, claimBingo, getCard, updateGameMode } from '../services/api'
import { WebSocketService } from '../services/websocket'

export default {
  name: 'ActiveGameView',
  components: {
    InfoBar,
    NumberCallDisplay,
    BingoGrid,
    UserCard,
    WinnerBanner,
    NotificationBanner
  },
  data() {
    return {
      game: null,
      userCard: null,
      calledNumbers: [],
      currentCall: null,
      recentCalls: [],
      canClaimBingo: false,
      winner: null,
      winners: null, // Array of all winners (for split prizes)
      winnerPrize: 0,
      totalPrize: null, // Total prize before split
      showWinnerBanner: false, // Separate flag for banner visibility (independent of winner data)
      gameMode: 'manual', // 'manual' or 'automatic'
      automaticallyMarkedNumbers: new Set(), // Track numbers marked automatically
      ws: null,
      wsConnected: false, // Track WebSocket connection state
      interval: null,
      redirectingToCardSelection: false,
      noWinner: false,
      winnerCard: null,
      isCurrentUserWinner: false,
      notificationMessage: null,
      notificationType: 'info',
      currentCallTimeout: null,
      pendingCalls: [], // Queue for calls that need to be displayed
      processedCalls: null, // Set to track processed WebSocket calls to prevent duplicates
      isPaused: false,
      visibilityHandler: null,
      showStartCountdown: false, // Show countdown when game just started
      startCountdownSeconds: 0,
      countdownInterval: null, // Store countdown interval reference
      _countdownInitialized: false, // Flag to prevent countdown from starting multiple times
      isMarkingNumber: false, // Prevent duplicate number marking
      lastMarkedNumber: null, // Track last marked number to prevent duplicates
      lastMarkedTime: 0, // Track when number was last marked
      winnerBannerShownAt: null, // Timestamp when winner banner was shown (to enforce 8-second display)
      _winnerBannerActive: false, // Flag to prevent loadGame from interfering with winner banner
      _completedRedirectTimeoutId: null // Clear this when winner_declared is received so we show banner instead of redirecting
    }
  },
  async mounted() {
    // Load game (router guard ensures we only mount when game exists)
    await this.loadGame()
    this.setupWebSocket()
    // Only start polling if WebSocket is not connected (fallback)
    // Polling will be stopped when WebSocket connects
    if (!this.wsConnected) {
      this.startPolling()
    }
    
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
    if (this.currentCallTimeout) {
      clearTimeout(this.currentCallTimeout)
    }
    if (this.countdownInterval) {
      clearInterval(this.countdownInterval)
    }
    if (this._completedRedirectTimeoutId) {
      clearTimeout(this._completedRedirectTimeoutId)
      this._completedRedirectTimeoutId = null
    }
    if (this.ws) {
      this.ws.disconnect()
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
    }
    // Reset all flags
    this._countdownInitialized = false
    this._winnerBannerActive = false
  },
  methods: {
    async loadGame() {
      try {
        // CRITICAL: When winner is declared (e.g. fake user) we set _winnerBannerActive immediately
        // but may delay showing the banner by 3s. Do NOT fetch or update anything in that window.
        if (this._winnerBannerActive) {
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          return
        }
        const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
        // Use the independent showWinnerBanner flag instead of checking winner data
        const isBannerShowing = this.showWinnerBanner || this._winnerBannerActive
        
        // If banner was shown less than 8 seconds ago, stop all polling and preserve state
        if (isBannerShowing && timeSinceBannerShown < 8000) {
          // Stop interval to prevent any interference
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          console.log('Winner banner is showing, preserving state and stopping polling')
          return // Don't do anything that might affect the banner
        }
        
        // Clear the flag if 8 seconds have passed
        if (this._winnerBannerActive && timeSinceBannerShown >= 8000) {
          this._winnerBannerActive = false
        }
        
        const game = await getCurrentGame()
        
        // If winner was declared while we were awaiting (e.g. fake user, 3s delay), don't touch state - preserve user card and UI
        if (this._winnerBannerActive) {
          return
        }
        
        // FIX: Always use calledNumbers.length as the source of truth for current_call_count
        // This prevents the count from being reset to 0 when loadGame() is called with stale server data
        this.game = game
        
        // CRITICAL: Always sync current_call_count from calledNumbers array (source of truth)
        // This ensures the count never shows 0 when we have called numbers
        if (this.calledNumbers && this.calledNumbers.length > 0) {
          this.game.current_call_count = this.calledNumbers.length
        } else if (game.called_numbers && game.called_numbers.length > 0) {
          // If calledNumbers is empty but server has called_numbers, use server count
          this.game.current_call_count = game.called_numbers.length
        } else {
          // Fallback to server's current_call_count only if we have no called numbers
          this.game.current_call_count = game.current_call_count || 0
        }
        
        if (game) {
          // Only redirect if game status actually changed
          // Don't redirect immediately if winner banner is showing - let it show first
          if (game.status === 'completed') {
            // Check if winner banner was shown recently (within last 8 seconds)
            
            // If we have a winner, don't redirect - let the banner show for minimum 8 seconds
            if (this.winner && this.winner !== null) {
              // Stop interval but don't redirect - banner will handle it after 8 seconds
              if (this.interval) {
                clearInterval(this.interval)
                this.interval = null
              }
              // Prevent any state changes if banner was shown less than 8 seconds ago
              if (timeSinceBannerShown < 8000) {
                console.log('Game completed with winner, keeping banner visible (enforcing 8-second display)')
                return
              }
              console.log('Game completed with winner, keeping banner visible')
              return
            }
            // If we have winners array, also don't redirect
            if (this.winners && this.winners.length > 0) {
              if (this.interval) {
                clearInterval(this.interval)
                this.interval = null
              }
              // Prevent any state changes if banner was shown less than 8 seconds ago
              if (timeSinceBannerShown < 8000) {
                console.log('Game completed with winners, keeping banner visible (enforcing 8-second display)')
                return
              }
              console.log('Game completed with winners, keeping banner visible')
              return
            }
            // No winner set yet, wait for winner_declared WebSocket (or 8s then redirect)
            if (this.interval) {
              clearInterval(this.interval)
              this.interval = null
            }
            if (this._completedRedirectTimeoutId) {
              clearTimeout(this._completedRedirectTimeoutId)
              this._completedRedirectTimeoutId = null
            }
            console.log('Game completed without winner set, waiting for winner_declared or 8s...')
            this._completedRedirectTimeoutId = setTimeout(() => {
              this._completedRedirectTimeoutId = null
              const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
              if (timeSinceBannerShown < 8000) return
              if ((!this.winner || this.winner === null) && (!this.winners || this.winners.length === 0)) {
                console.log('No winner after delay, redirecting')
                this.$router.push('/completed')
              }
            }, 8000)
            return
          } else if (game.status === 'waiting') {
            // Game is waiting - redirect to card selection (router guard should have caught this, but handle it anyway)
            if (this.interval) {
              clearInterval(this.interval)
              this.interval = null
            }
            this.$router.push('/select-card')
            return
          } else if (game.status === 'completed') {
            // Game is completed - wait for winner_declared WebSocket so we can show banner for ALL players (real + fake winner)
            // Only redirect after a delay if winner_declared never arrives
            if (this.interval) {
              clearInterval(this.interval)
              this.interval = null
            }
            if (this._completedRedirectTimeoutId) {
              clearTimeout(this._completedRedirectTimeoutId)
              this._completedRedirectTimeoutId = null
            }
            this._completedRedirectTimeoutId = setTimeout(() => {
              this._completedRedirectTimeoutId = null
              const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
              if (timeSinceBannerShown < 8000) return
              if ((!this.winner && (!this.winners || this.winners.length === 0)) || timeSinceBannerShown >= 8000) {
                this.$router.push('/completed')
              }
            }, 3500)
            return
          }
          
          // CRITICAL: If winner banner is showing, don't load card or do anything that might affect state
          if (isBannerShowing && timeSinceBannerShown < 8000) {
            console.log('Winner banner is showing, skipping card load and state updates')
            return
          }
          
          // Load user's card
          try {
            const card = await getMyCard(game.id)
            this.userCard = card
            
            // Initialize gameMode from card's mode_history
            if (card.mode_history && card.mode_history.length > 0) {
              const lastModeEntry = card.mode_history[card.mode_history.length - 1]
              this.gameMode = lastModeEntry.mode || 'manual'
            } else {
              // Default to manual if no mode history
              this.gameMode = 'manual'
            }
            
            // Don't check bingo pattern if winner banner is showing
            // Only check pattern (to update canClaimBingo), but don't auto-claim unless in automatic mode
            if (!isBannerShowing || timeSinceBannerShown >= 8000) {
              this.checkBingoPattern()
            }
          } catch (error) {
            console.error('Error loading card:', error)
            // User doesn't have a card
            if (error.response?.status === 404) {
              // If game is waiting, redirect to card selection
              if (game.status === 'waiting') {
                if (this.interval) {
                  clearInterval(this.interval)
                  this.interval = null
                }
                this.$router.push('/select-card').catch(() => {})
                return
              }
              // Don't clear userCard when winner is declared, game already completed, or we had a card.
              const winnerDeclared = this._winnerBannerActive || this.winner || (this.winners && this.winners.length)
              const hadCard = !!this.userCard
              const gameAlreadyCompleted = this.game && this.game.status === 'completed'
              if (!winnerDeclared && !hadCard && !gameAlreadyCompleted) {
                // Spectator in active game: no card to show
                this.userCard = null
              }
            }
          }
          
          // Reset countdown and frozen player count if game status changed from active
          if (game.status !== 'active') {
            if (this._countdownInitialized) {
              this._countdownInitialized = false
            }
          }
          
          // Check if game just started and no numbers called yet - show countdown
          // Use _countdownInitialized flag to prevent multiple countdown starts
          if (game.status === 'active' && (!game.called_numbers || game.called_numbers.length === 0) && !this.showStartCountdown && !this.countdownInterval && !this._countdownInitialized) {
            // Game just started, show 3-second countdown
            this._countdownInitialized = true // Mark as initialized to prevent duplicate starts
            this.showStartCountdown = true
            this.startCountdownSeconds = 3
            this.countdownInterval = setInterval(() => {
              if (this.startCountdownSeconds > 1) {
                this.startCountdownSeconds--
              } else {
                clearInterval(this.countdownInterval)
                this.countdownInterval = null
                this.showStartCountdown = false
                // Countdown finished - immediately check for first number
                // Reduce polling interval temporarily to catch first number faster
                // Only if WebSocket is not connected
                if (!this.wsConnected) {
                  if (this.interval) {
                    clearInterval(this.interval)
                  }
                  this.interval = setInterval(this.loadGame, 500) // Poll every 500ms for first number
                  // After 2 seconds, restore normal polling
                  setTimeout(() => {
                    if (!this.wsConnected && this.interval) {
                      clearInterval(this.interval)
                      this.interval = setInterval(this.loadGame, 10000) // Back to 10 seconds (reduced from 2s)
                    }
                  }, 2000)
                }
                // Force immediate check
                this.loadGame()
              }
            }, 1000)
          }
          
          // Load called numbers - only update if WebSocket hasn't already processed them
          // This prevents race conditions between polling and WebSocket
          if (game.called_numbers) {
            const newCalledNumbers = game.called_numbers.map(cn => cn.number)
            // Only update if there are new numbers we haven't seen
            const hasNewNumbers = newCalledNumbers.some(num => !this.calledNumbers.includes(num))
            
            // FIX: Only hide countdown if it has finished (3 seconds passed)
            // This ensures called numbers are only shown after countdown completes
            if (game.called_numbers.length > 0 && this.showStartCountdown && this.startCountdownSeconds <= 0) {
              this.showStartCountdown = false
              if (this.countdownInterval) {
                clearInterval(this.countdownInterval)
                this.countdownInterval = null
              }
              // Restore normal polling interval if it was changed (only if WS not connected)
              if (!this.wsConnected) {
                if (this.interval) {
                  clearInterval(this.interval)
                }
                this.interval = setInterval(this.loadGame, 10000) // Normal 10 second polling (reduced from 2s)
              }
            } else if (game.called_numbers.length > 0 && this.showStartCountdown && this.startCountdownSeconds > 0) {
              // Countdown still running - don't process called numbers yet
              // Numbers will be processed after countdown finishes
              console.log('Countdown still running, ignoring called numbers until countdown finishes')
            }
            
            // FIX: Only process called numbers if countdown has finished
            if (hasNewNumbers && (!this.showStartCountdown || this.startCountdownSeconds <= 0)) {
              this.calledNumbers = newCalledNumbers
              
              // ATOMIC FIX: Update current_call_count to match actual called numbers length
              // This ensures the count displayed matches the actual numbers on the bingo board
              // CRITICAL: Always update immediately to prevent showing 0
              if (this.game) {
                this.game.current_call_count = this.calledNumbers.length
                console.log(`✅ [SYNC] Updated call count to ${this.calledNumbers.length} from calledNumbers array`)
              }
            } else if (!hasNewNumbers && game.called_numbers && game.called_numbers.length > 0) {
              // Even if no new numbers, ensure count is synced (prevents showing 0)
              if (this.game && this.calledNumbers.length !== game.called_numbers.length) {
                this.calledNumbers = newCalledNumbers
                this.game.current_call_count = this.calledNumbers.length
                console.log(`✅ [SYNC] Synced call count to ${this.calledNumbers.length} (no new numbers but count was wrong)`)
              }
              
              if (game.called_numbers.length > 0) {
                const lastCall = game.called_numbers[game.called_numbers.length - 1]
                const callKey = `${lastCall.letter}-${lastCall.number}`
                
                // CRITICAL: During active game, drive the big display (currentCall) from WebSocket only,
                // so numbers appear one-by-one at the right interval. Only set currentCall from polling when:
                // we don't have one yet (initial load / catch-up) or game is not active.
                const shouldUpdateCurrentCallFromPolling =
                  (!this.processedCalls || !this.processedCalls.has(callKey) || !this.currentCall) &&
                  (!this.currentCall || game.status !== 'active')
                if (shouldUpdateCurrentCallFromPolling) {
                  if (!this.currentCall || this.currentCall.number !== lastCall.number) {
                    if (this.currentCall) {
                      const existsInRecent = this.recentCalls.some(call => 
                        call.number === this.currentCall.number && call.letter === this.currentCall.letter
                      )
                      if (!existsInRecent) {
                        this.recentCalls.push({
                          number: this.currentCall.number,
                          letter: this.currentCall.letter
                        })
                        if (this.recentCalls.length > 3) {
                          this.recentCalls = this.recentCalls.slice(-3)
                        }
                      }
                    }
                    this.currentCall = {
                      number: lastCall.number,
                      letter: lastCall.letter
                    }
                    if (!this.processedCalls) {
                      this.processedCalls = new Set()
                    }
                    this.processedCalls.add(callKey)
                  }
                }
                
                // Update recent calls from game data (last 3 unique, excluding current)
                const uniqueRecent = []
                const seen = new Set()
                for (let i = game.called_numbers.length - 2; i >= 0 && uniqueRecent.length < 3; i--) {
                  const call = game.called_numbers[i]
                  const key = `${call.letter}-${call.number}`
                  if (!seen.has(key) && call.number !== this.currentCall?.number) {
                    seen.add(key)
                    uniqueRecent.unshift({
                      number: call.number,
                      letter: call.letter
                    })
                  }
                }
                this.recentCalls = uniqueRecent
              }
            }
            
            // In automatic mode, mark any new numbers that were called (only if no winner yet)
            if (this.gameMode === 'automatic' && this.userCard && hasNewNumbers &&
                !this.winner && !(this.winners && this.winners.length > 0) &&
                game.status === 'active' && !this.userCard.is_winner) {
              newCalledNumbers.forEach(number => {
                if (!this.automaticallyMarkedNumbers.has(number)) {
                  this.autoMarkNumber(number)
                }
              })
            }
            
            // Check if all 75 numbers have been called and no winner
            if (game.called_numbers.length >= 75 && game.status === 'active' && !game.winner) {
              // Wait 3 seconds to see if someone claims BINGO, then check again
              setTimeout(() => {
                this.loadGame().then(() => {
                  if (this.game && this.game.status === 'active' && !this.game.winner && this.calledNumbers.length >= 75) {
                    this.handleNoWinner()
                  }
                })
              }, 3000) // Hardcoded 3 seconds
            }
          }
        } else {
          // No game found - router guard should have prevented this, but redirect anyway
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/completed')
          return
        }
      } catch (error) {
        console.error('Error loading game:', error)
        // If 404, redirect to completed view (router guard should have prevented this, but handle it anyway)
        if (error.response?.status === 404) {
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/completed')
          return
        }
        // For other errors, log but don't redirect (might be temporary network issue)
        console.error('Error loading game (non-404):', error)
      }
    },
    setupWebSocket() {
      if (!this.game) return
      // Room separation: game view = player room (see docs/WEBSOCKET_EVENTS.md)
      this.ws = new WebSocketService(this.game.id, { role: 'player' })
      
      this.ws.on('connected', () => {
        console.log('WebSocket connected successfully')
        this.wsConnected = true
        // Stop polling when WebSocket connects - we get real-time updates via WS
        this.stopPolling()
      })
      
      this.ws.on('error', (error) => {
        console.error('WebSocket error:', error)
        // On error, ensure polling is active as fallback
        if (!this.wsConnected) {
          this.startPolling()
        }
      })
      
      this.ws.on('disconnected', () => {
        console.log('WebSocket disconnected')
        this.wsConnected = false
        // Resume polling when WebSocket disconnects - fallback to HTTP polling
        this.startPolling()
      })
      
      this.ws.on('number_called', (data) => {
        console.log('Number called via WebSocket:', data)
        
        // CRITICAL: Always process every number - never drop. If countdown is running, hide it first then process.
        // This fixes "only first number shows then stuck" when numbers arrive during or right after countdown.
        if (this.showStartCountdown) {
          this.showStartCountdown = false
          if (this.countdownInterval) {
            clearInterval(this.countdownInterval)
            this.countdownInterval = null
          }
        }
        
        // Prevent duplicate processing - use a flag to prevent race conditions
        const callKey = `${data.letter}-${data.number}`
        if (this.processedCalls && this.processedCalls.has(callKey)) {
          console.log('Call already processed, skipping:', callKey)
          return
        }
        
        if (!this.processedCalls) {
          this.processedCalls = new Set()
        }
        this.processedCalls.add(callKey)
        
        // Add to called numbers if not already there
        if (!this.calledNumbers.includes(data.number)) {
          this.calledNumbers.push(data.number)
        }
        
        // ATOMIC FIX: Update game's current_call_count to match actual called numbers length
        // This ensures the count displayed matches the actual numbers on the bingo board
        if (this.game) {
          // Use the actual length of calledNumbers array as the source of truth
          this.game.current_call_count = this.calledNumbers.length
          // Also update from WebSocket data if provided (for consistency)
          if (data.call_count !== undefined) {
            // Ensure it matches our array length
            this.game.current_call_count = Math.max(this.calledNumbers.length, data.call_count)
          }
        }
        
        // Clear any existing timeout
        if (this.currentCallTimeout) {
          clearTimeout(this.currentCallTimeout)
          this.currentCallTimeout = null
        }
        
        // If there's a current call, move it to recent calls first (only if it's different)
        if (this.currentCall && (this.currentCall.number !== data.number || this.currentCall.letter !== data.letter)) {
          // Check if it's not already in recent calls
          const existsInRecent = this.recentCalls.some(call => 
            call.number === this.currentCall.number && call.letter === this.currentCall.letter
          )
          if (!existsInRecent) {
            this.recentCalls.push({
              number: this.currentCall.number,
              letter: this.currentCall.letter
            })
            // Keep only last 3 unique calls
            if (this.recentCalls.length > 3) {
              this.recentCalls = this.recentCalls.slice(-3)
            }
          }
        }
        
        // CRITICAL FIX: Set new current call immediately to show the latest number
        // This ensures the UI always shows the most recently called number
        this.currentCall = {
          number: data.number,
          letter: data.letter
        }
        
        // Force immediate UI update to show the new number
        this.$forceUpdate()
        
        // Get time between calls from game settings (default 3 seconds)
        const timeBetweenCalls = (this.game && this.game.time_between_calls) || 3
        
        // Keep current call visible for the time interval between calls
        // This ensures each number is displayed for the correct duration
        this.currentCallTimeout = setTimeout(() => {
          // After timeout, current call stays visible until next number is called
          // Don't move it to recent here - let the next call handle it
        }, timeBetweenCalls * 1000) // Use time_between_calls from settings
        
        // In automatic mode, mark the number on the card automatically (only if no winner yet and banner not shown)
        const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
        if (this.gameMode === 'automatic' && this.userCard &&
            !this.winner && !(this.winners && this.winners.length > 0) &&
            this.game && this.game.status === 'active' && !this.userCard.is_winner &&
            timeSinceBannerShown >= 8000) {
          this.autoMarkNumber(data.number)
        }
        
        // Always check bingo pattern to update button state (canClaimBingo)
        // tryAutoClaimBingo() will only auto-claim in automatic mode
        this.checkBingoPattern()
        
        // Check if all 75 numbers have been called
        if (this.calledNumbers.length >= 75 && this.game && this.game.status === 'active' && !this.game.winner) {
          // Wait 3 seconds to see if someone claims BINGO
          setTimeout(() => {
            if (this.game && this.game.status === 'active' && !this.game.winner && this.calledNumbers.length >= 75) {
              this.handleNoWinner()
            }
          }, 3000)
        }
      })
      
      this.ws.on('admin_message', (data) => {
        // Show admin message to players
        if (data && data.message) {
          let messageText = data.message
          if (data.refund && data.cancel) {
            messageText += '\n\n⏰ ከ5 ሰከንድ በኋላ ገንዘብዎ ይመለስና ጨዋታው ይተዋል።'
          } else if (data.refund) {
            messageText += '\n\n💰 ገንዘብዎ ይመለስናል።'
          } else if (data.cancel) {
            messageText += '\n\n❌ ጨዋታው ተሰርዟል።'
          }
          this.showNotification(messageText, 'warning')
          
          // If both refund and cancel, wait 5 seconds then refresh
          if (data.refund && data.cancel) {
            setTimeout(() => {
              window.location.reload()
            }, 5000)
          } else if (data.cancel) {
            // If cancel only, redirect to home/card selection after a delay
            setTimeout(() => {
              window.location.href = '/'
            }, 3000)
          }
        }
      })
      
      this.ws.on('game_cancelled', (data) => {
        if (data && data.message) {
          this.showNotification(data.message, 'warning')
        }
        setTimeout(() => {
          this.$router.push('/completed').catch(() => {})
        }, 2000)
      })
      
      this.ws.on('game_ended', (data) => {
        console.log('Game ended via WebSocket:', data)
        
        // CRITICAL FIX: Update game status immediately when game_ended event is received
        // This ensures all users see the game as completed, not just the winner
        if (this.game && data && data.status === 'completed') {
          this.game.status = 'completed'
          if (data.completed_at) {
            this.game.completed_at = data.completed_at
          }
        }
        
        // Check if no winner
        if (data && data.no_winner) {
          this.handleNoWinner()
        } else {
          // Don't redirect immediately - let winner_declared show banner first for ALL players
          // Give winner_declared time to arrive (same or next tick); then redirect if still no winner
          if (!this.winner && (!this.winners || this.winners.length === 0)) {
            setTimeout(() => {
              if (!this.winner && (!this.winners || this.winners.length === 0)) {
                this.$router.push('/completed')
              }
            }, 2500)
          }
        }
      })
      
      this.ws.on('winner_declared', (data) => {
        console.log('Winner declared via WebSocket:', data)
        
        // Clear any pending "completed with no winner" redirect so we show banner instead
        if (this._completedRedirectTimeoutId) {
          clearTimeout(this._completedRedirectTimeoutId)
          this._completedRedirectTimeoutId = null
        }
        
        const isFakeUserWinner = (data.winners && data.winners.length > 0 && data.winners[0].is_fake) ||
                                 (data.winner && data.winner.is_fake) ||
                                 (data.winners && data.winners.length > 0 && data.winners[0].winner && data.winners[0].winner.is_fake) ||
                                 (data.is_fake)
        
        // For real user winner: set game completed now. For fake user: wait 3s then set completed
        // so real players can still tick called numbers during the 3s delay (no "not called yet" error).
        if (this.game && !isFakeUserWinner) {
          this.game.status = 'completed'
        }
        
        // ATOMIC FIX: Stop all polling and state updates BEFORE showing banner
        if (this.interval) {
          clearInterval(this.interval)
          this.interval = null
        }
        
        // Stop ALL automatic mode behavior immediately when winner is declared
        this.canClaimBingo = false
        this.automaticallyMarkedNumbers.clear()
        this.gameMode = 'manual' // Force switch to manual mode to prevent any automatic actions
        this.isMarkingNumber = false // Stop any pending marking operations
        
        // CRITICAL: Stop the interval IMMEDIATELY to prevent loadGame() from interfering
        if (this.interval) {
          clearInterval(this.interval)
          this.interval = null
        }
        
        // Set flag to prevent loadGame from running and interfering with banner
        this._winnerBannerActive = true
        
        // Helper function to set winner data and show banner (and set game completed when called for fake user)
        const showWinnerBanner = () => {
          // For fake user: set game completed only when we show the banner (after 3s delay)
          if (this.game && isFakeUserWinner) {
            this.game.status = 'completed'
          }
          // Record when winner banner is shown - enforce 8-second minimum display
          this.winnerBannerShownAt = Date.now()
          
          // Set banner visibility flag
          this.showWinnerBanner = true
          this._winnerBannerActive = true
          
          // Force update to show banner
          this.$forceUpdate()
        }
        
        // Handle multiple winners (new format)
        if (data.winners && data.winners.length > 0) {
          this.winners = data.winners
          // For fake users, winner might be null but username is in the winner data
          // Use winner object if available, otherwise create one from username
          if (data.winners[0].winner) {
            this.winner = data.winners[0].winner
          } else if (data.winners[0].username) {
            // Fake user - create winner object from username
            this.winner = {
              id: null,
              username: data.winners[0].username,
              name: data.winners[0].username,
              is_fake: true
            }
          } else {
            this.winner = data.winners[0].winner || null
          }
          this.winnerPrize = data.prize || data.winners[0].prize || 0
          this.totalPrize = data.total_prize || null
          
          // Check if current user is among the winners
          if (this.userCard && this.userCard.user) {
            const currentUserId = this.userCard.user.id
            const currentUserWinner = data.winners.find(w => 
              w.winner && (w.winner.id === currentUserId || w.winner.id === Number(currentUserId))
            )
            
            if (currentUserWinner) {
              this.isCurrentUserWinner = true
              this.winnerCard = {
                card_layout: currentUserWinner.card_layout,
                card_number: currentUserWinner.card_number,
                winning_pattern: currentUserWinner.winning_pattern,
                selected_numbers: currentUserWinner.selected_numbers || [],
                called_numbers: currentUserWinner.called_numbers || [],
                last_called_number: currentUserWinner.last_called_number || null
              }
            } else {
              this.isCurrentUserWinner = false
              // Use first winner's card as default (for fake users or other real users)
              if (data.winners[0].card_layout) {
                this.winnerCard = {
                  card_layout: data.winners[0].card_layout,
                  card_number: data.winners[0].card_number,
                  winning_pattern: data.winners[0].winning_pattern,
                  selected_numbers: data.winners[0].selected_numbers || [],
                  called_numbers: data.winners[0].called_numbers || [],
                  last_called_number: data.winners[0].last_called_number || null
                }
              }
            }
          }
        } else {
          // Single winner (backward compatible format)
          this.winners = null
          // For fake users, winner might be null but username is available
          if (data.winner) {
            this.winner = data.winner
          } else if (data.username) {
            // Fake user - create winner object from username
            this.winner = {
              id: null,
              username: data.username,
              name: data.username,
              is_fake: data.is_fake || false
            }
          } else {
            this.winner = data.winner || null
          }
          this.winnerPrize = data.prize || this.game?.total_derash || 0
          
          // Set winnerCard for single winner format
          if (data.card_layout) {
            this.winnerCard = {
              card_layout: data.card_layout,
              card_number: data.card_number,
              winning_pattern: data.winning_pattern,
              selected_numbers: data.selected_numbers || [],
              called_numbers: data.called_numbers || [],
              last_called_number: data.last_called_number || null
            }
          }
        this.totalPrize = null
        // Record when winner banner is shown (if not already set)
        if (!this.winnerBannerShownAt) {
          this.winnerBannerShownAt = Date.now()
        }
          
          // Check if current user is the winner
          if (this.userCard && data.winner && this.userCard.user && 
              (this.userCard.user.id === data.winner.id || this.userCard.user === data.winner.id)) {
            this.isCurrentUserWinner = true
            this.winnerCard = {
              ...this.userCard,
              winning_pattern: data.winning_pattern,
              selected_numbers: data.selected_numbers || this.userCard.selected_numbers || [],
              called_numbers: data.called_numbers || [],
              last_called_number: data.last_called_number || null
            }
          } else {
            this.isCurrentUserWinner = false
            // Load winner's card if available
            if (data.card_id || data.card_number) {
              // Try to get winner's card
              this.loadWinnerCard(data)
            } else if (data.card_layout) {
              // Use card layout from WebSocket data
              this.winnerCard = {
                card_layout: data.card_layout,
                card_number: data.card_number,
                winning_pattern: data.winning_pattern,
                selected_numbers: data.selected_numbers || [],
                called_numbers: data.called_numbers || [],
                last_called_number: data.last_called_number || null
              }
            }
          }
        }
        
        console.log('Winner banner state:', {
          winner: this.winner,
          winners: this.winners,
          winnerPrize: this.winnerPrize,
          totalPrize: this.totalPrize,
          winnerCard: this.winnerCard,
          isCurrentUserWinner: this.isCurrentUserWinner,
          isFakeUserWinner: isFakeUserWinner
        })
        
        // FIX: Show banner immediately for real users, after 3-second delay for fake users
        // (gives real players chance to claim bingo with same number)
        if (isFakeUserWinner) {
          setTimeout(() => {
            showWinnerBanner()
          }, 3000)
        } else {
          showWinnerBanner()
        }
        
        // Redirect to completed view after 8 seconds (handled by WinnerBanner timer)
      })
      
      this.ws.connect()
    },
    startPolling() {
      // PHASE 2 OPTIMIZATION #4: Reduced polling frequency from 2s to 10s
      // Only start polling if WebSocket is not connected and interval is not already running
      if (!this.wsConnected && !this.interval) {
        console.log('Starting HTTP polling (WebSocket not connected)')
        this.interval = setInterval(this.loadGame, 10000) // Poll every 10 seconds (reduced from 2s)
      }
    },
    stopPolling() {
      // Stop polling when WebSocket is connected
      if (this.interval) {
        console.log('Stopping HTTP polling (WebSocket connected)')
        clearInterval(this.interval)
        this.interval = null
      }
    },
    async handleMarkNumber(number) {
      if (!this.userCard) {
        // User doesn't have a card, show message
        return
      }
      
      // Prevent duplicate clicks - debounce
      const now = Date.now()
      if (this.isMarkingNumber || (this.lastMarkedNumber === number && now - this.lastMarkedTime < 500)) {
        return // Ignore duplicate clicks within 500ms
      }
      
      // Check if number was called
      if (!this.calledNumbers.includes(number)) {
        this.showNotification('ይህ ቁጥር እስካሁን አልተጠራም!', 'error')
        return
      }
      
      // Set flag to prevent duplicate clicks
      this.isMarkingNumber = true
      this.lastMarkedNumber = number
      this.lastMarkedTime = now
      
      // Check if already marked (prevent re-marking)
      const layout = this.userCard.card_layout
      if (layout) {
        for (let row of layout) {
          for (let cell of row) {
            if (cell.number === number && cell.marked) {
              // Already marked, just reset flag
              this.isMarkingNumber = false
              return
            }
          }
        }
      }
      
      // OPTIMISTIC UPDATE: Mark the number immediately in UI
      if (layout) {
        for (let row of layout) {
          for (let cell of row) {
            if (cell.number === number && !cell.marked && cell.letter !== 'FREE') {
              cell.marked = true
              // Force Vue reactivity
              this.$forceUpdate()
              // Always check bingo pattern to update button state (canClaimBingo)
              // tryAutoClaimBingo() will only auto-claim in automatic mode
              this.checkBingoPattern()
              break
            }
          }
        }
      }
      
      // Then sync with backend (fire and forget for faster response)
      markNumber(this.userCard.id, number)
        .then(updatedCard => {
          // Update with server response to ensure consistency
          if (updatedCard.card_layout) {
            this.userCard.card_layout = updatedCard.card_layout
            // Always check bingo pattern to update button state (canClaimBingo)
            // tryAutoClaimBingo() will only auto-claim in automatic mode
            this.checkBingoPattern()
          }
          this.isMarkingNumber = false
        })
        .catch(error => {
          // Revert optimistic update on error
          if (layout) {
            for (let row of layout) {
              for (let cell of row) {
                if (cell.number === number) {
                  cell.marked = false
                  this.$forceUpdate()
                  break
                }
              }
            }
          }
          this.isMarkingNumber = false
          const errorMsg = error.response?.data?.error || 'Failed to mark number'
          if (!errorMsg.includes('not found on your card')) {
            let translatedMsg = errorMsg
            if (errorMsg.includes('Insufficient balance') || errorMsg.includes('insufficient')) {
              translatedMsg = 'በቂ ሂሳብ የሎትም'
            } else if (errorMsg.includes('Failed to mark number')) {
              translatedMsg = 'ቁጥርን ለመለየት ስህተት ተፈጥሯል'
            }
            this.showNotification(translatedMsg, 'error')
          }
        })
    },
    async handleClaimBingo() {
      if (!this.userCard) return
      
      // Stop automatic mode behavior immediately when claiming
      this.canClaimBingo = false
      this.automaticallyMarkedNumbers.clear()
      
      // OPTIMISTIC UPDATE: Show winner banner immediately
      // Record when winner banner is shown - enforce 8-second minimum display
      this.winnerBannerShownAt = Date.now()
      
      // CRITICAL: Set banner visibility flag IMMEDIATELY - independent of winner data
      // This prevents banner from disappearing due to state updates/re-renders
      this.showWinnerBanner = true
      this._winnerBannerActive = true
      
      const prize = this.game?.total_derash || 0
      this.winner = {
        username: 'You',
        id: this.userCard.user
      }
      this.winnerPrize = prize
      this.isCurrentUserWinner = true
      
      // Stop the interval to prevent immediate redirect
      if (this.interval) {
        clearInterval(this.interval)
        this.interval = null
      }
      
      // Get winning pattern from card layout immediately
      if (this.userCard && this.userCard.card_layout) {
        const layout = this.userCard.card_layout
        let winningPattern = null
        
        // Check which pattern won
        const isCellMarked = (cell) => {
          if (cell.letter === 'FREE') return true
          return cell.marked || false
        }
        
        // Check horizontal
        for (let rowIdx = 0; rowIdx < layout.length; rowIdx++) {
          if (layout[rowIdx].every(cell => isCellMarked(cell))) {
            winningPattern = `row_${rowIdx}`
            break
          }
        }
        
        // Check vertical
        if (!winningPattern) {
          for (let colIdx = 0; colIdx < 5; colIdx++) {
            if (layout.every(row => isCellMarked(row[colIdx]))) {
              winningPattern = `col_${colIdx}`
              break
            }
          }
        }
        
        // Check diagonals
        if (!winningPattern) {
          if (layout.every((row, idx) => isCellMarked(row[idx]))) {
            winningPattern = 'diagonal_1'
          } else if (layout.every((row, idx) => isCellMarked(row[4 - idx]))) {
            winningPattern = 'diagonal_2'
          } else if (layout.every(row => row.every(cell => isCellMarked(cell)))) {
            winningPattern = 'full_card'
          }
        }
        
        this.winnerCard = {
          ...this.userCard,
          winning_pattern: winningPattern,
          selected_numbers: this.userCard.selected_numbers || [],
          called_numbers: this.calledNumbers || [],
          last_called_number: this.currentCall?.number || null
        }
      }
      
      // Force immediate UI update
      this.$forceUpdate()
      
      // Then sync with backend (fire and forget for faster response)
      claimBingo(this.userCard.id)
        .then(result => {
          if (result.success) {
            // Update with server response
            const serverPrize = result.prize || prize
            this.winnerPrize = serverPrize
            console.log('BINGO claim confirmed by server:', result)
          }
        })
        .catch(error => {
          const errorMsg = error.response?.data?.error || 'Invalid BINGO claim'
          
          // If error is "already won" or "ተቀድመዋል", check if we're actually a winner
          // This can happen in automatic mode when the claim succeeds but response is delayed
          if (errorMsg.includes('already won') || errorMsg.includes('ተቀድመዋል') || 
              errorMsg.includes('not active')) {
            // Check if the card actually won (might be a race condition)
            if (this.userCard && this.userCard.is_winner) {
              // Card actually won, keep the winner banner - don't revert
              console.log('Card won but got error (likely race condition), keeping winner banner')
              return
            }
            // Another player won first, revert optimistic update
            // BUT: Don't clear banner if it's already showing (user might be a legitimate winner in race condition)
            // Only clear if banner wasn't shown via WebSocket
            if (!this.showWinnerBanner) {
              this.winner = null
              this.winnerPrize = 0
              this.isCurrentUserWinner = false
              this.winnerCard = null
              this.winnerBannerShownAt = null
              const translatedMsg = errorMsg.includes('ተቀድመዋል') ? errorMsg : 'በሌላ ተጫዋች ተቀድመዋል!'
              this.showNotification(translatedMsg, 'error')
            }
          } else {
            // Other errors - revert optimistic update
            // BUT: Don't clear banner if it's already showing (user might be a legitimate winner)
            // Only clear if banner wasn't shown via WebSocket
            if (!this.showWinnerBanner) {
              this.winner = null
              this.winnerPrize = 0
              this.isCurrentUserWinner = false
              this.winnerCard = null
              this.winnerBannerShownAt = null
            }
            
            let translatedMsg = errorMsg
            if (errorMsg.includes('Invalid BINGO claim') || errorMsg.includes('BINGO pattern not complete')) {
              translatedMsg = 'ቢንጎ አልሰሩም'
            } else if (errorMsg.includes('not called')) {
              translatedMsg = 'ይህ ቁጥር አልተጠራም'
            }
            this.showNotification(translatedMsg, 'error')
          }
          this.$forceUpdate()
        })
    },
    checkBingoPattern() {
      if (!this.userCard || !this.userCard.card_layout) {
        this.canClaimBingo = false
        return
      }
      
      // Stop checking if there's already a winner (game is over) or banner is showing
      const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
      if (this.winner || (this.winners && this.winners.length > 0) || 
          (this.game && this.game.status === 'completed') ||
          (this.userCard && this.userCard.is_winner) ||
          timeSinceBannerShown < 5000) {
        this.canClaimBingo = false
        return
      }
      
      const layout = this.userCard.card_layout
      
      // Helper function to check if a cell is marked (including FREE space)
      const isCellMarked = (cell) => {
        if (cell.letter === 'FREE') {
          return true  // FREE is always considered marked
        }
        return cell.marked || false
      }
      
      // Check horizontal lines (any row)
      for (let row of layout) {
        if (row.every(cell => isCellMarked(cell))) {
          this.canClaimBingo = true
          // ONLY auto-claim in automatic mode - in manual mode, user must click button
          this.tryAutoClaimBingo()
          return
        }
      }
      
      // Check vertical lines (any column)
      for (let col = 0; col < 5; col++) {
        if (layout.every(row => isCellMarked(row[col]))) {
          this.canClaimBingo = true
          // ONLY auto-claim in automatic mode - in manual mode, user must click button
          this.tryAutoClaimBingo()
          return
        }
      }
      
      // Check diagonal (top-left to bottom-right)
      if (layout.every((row, idx) => isCellMarked(row[idx]))) {
        this.canClaimBingo = true
        // ONLY auto-claim in automatic mode - in manual mode, user must click button
        this.tryAutoClaimBingo()
        return
      }
      
      // Check diagonal (top-right to bottom-left)
      if (layout.every((row, idx) => isCellMarked(row[4 - idx]))) {
        this.canClaimBingo = true
        // ONLY auto-claim in automatic mode - in manual mode, user must click button
        this.tryAutoClaimBingo()
        return
      }
      
      // Check corner bingo (4 corners + FREE cell: top-left, top-right, bottom-left, bottom-right, center)
      const corners = [
        layout[0][0],  // Top-left
        layout[0][4],  // Top-right
        layout[4][0],  // Bottom-left
        layout[4][4],  // Bottom-right
        layout[2][2]   // FREE cell (center) - included for visual appeal
      ]
      if (corners.every(cell => isCellMarked(cell))) {
        this.canClaimBingo = true
        // ONLY auto-claim in automatic mode - in manual mode, user must click button
        this.tryAutoClaimBingo()
        return
      }
      
      // Check full card (all cells marked)
      const allCellsMarked = layout.every(row => row.every(cell => isCellMarked(cell)))
      if (allCellsMarked) {
        this.canClaimBingo = true
        // ONLY auto-claim in automatic mode - in manual mode, user must click button
        this.tryAutoClaimBingo()
        return
      }
      
      this.canClaimBingo = false
    },
    tryAutoClaimBingo() {
      // CRITICAL: Only auto-claim in automatic mode
      // In manual mode, user must manually click the bingo button
      if (this.gameMode !== 'automatic') {
        // Manual mode - just set canClaimBingo and wait for user to click
        return
      }
      
      // Automatic mode - check conditions and auto-claim
      const timeSinceBannerShown = this.winnerBannerShownAt ? Date.now() - this.winnerBannerShownAt : Infinity
      if (!this.winner && !this.userCard.is_winner && 
          !(this.winners && this.winners.length > 0) && timeSinceBannerShown >= 5000) {
        this.autoClaimBingo()
      }
    },
    async handleModeChange() {
      // Update mode on backend
      if (this.userCard) {
        try {
          await updateGameMode(this.userCard.id, this.gameMode)
        } catch (error) {
          console.error('Error updating mode:', error)
          // Revert mode if update failed
          this.gameMode = this.gameMode === 'automatic' ? 'manual' : 'automatic'
          this.showNotification('Mode update failed. Please try again.', 'error')
          return
        }
      }
      
      // When switching to automatic mode, mark all already-called numbers
      if (this.gameMode === 'automatic' && this.userCard) {
        this.calledNumbers.forEach(number => {
          if (!this.automaticallyMarkedNumbers.has(number)) {
            this.autoMarkNumber(number)
          }
        })
      }
    },
    async autoMarkNumber(number) {
      // Stop if there's already a winner or game is completed
      if (!this.userCard || this.automaticallyMarkedNumbers.has(number) ||
          this.winner || (this.winners && this.winners.length > 0) ||
          (this.game && this.game.status === 'completed') ||
          (this.userCard && this.userCard.is_winner)) {
        return // Already marked, no card, or game is over
      }
      
      // Check if the number exists on the card
      const layout = this.userCard.card_layout
      let numberFound = false
      
      for (let row of layout) {
        for (let cell of row) {
          if (cell.number === number && !cell.marked && cell.letter !== 'FREE') {
            numberFound = true
            break
          }
        }
        if (numberFound) break
      }
      
      if (numberFound) {
        try {
          await markNumber(this.userCard.id, number)
          this.automaticallyMarkedNumbers.add(number)
          // Refresh user card to get updated layout
          if (this.game) {
            const card = await getMyCard(this.game.id)
            this.userCard = card
            // Check again if winner was declared during the API call
            if (card.is_winner || (this.game && this.game.status === 'completed')) {
              return // Game is over, stop processing
            }
          }
          // Always check bingo pattern to update button state (canClaimBingo)
          // tryAutoClaimBingo() will only auto-claim in automatic mode
          if (!this.winner && !(this.winners && this.winners.length > 0) &&
              this.game && this.game.status === 'active' && !this.userCard.is_winner) {
            this.checkBingoPattern()
          }
        } catch (error) {
          console.error('Error auto-marking number:', error)
          // If error is "game not active" or similar, that's expected - ignore it
          const errorMsg = error.response?.data?.error || error.message || ''
          if (errorMsg.includes('not active') || errorMsg.includes('ተቀድመዋል')) {
            // Expected error - game ended, just ignore
            return
          }
        }
      }
    },
    async autoClaimBingo() {
      // Stop if there's already a winner or game is completed
      if (!this.canClaimBingo || !this.userCard || 
          this.winner || (this.winners && this.winners.length > 0) ||
          (this.game && this.game.status === 'completed') ||
          (this.userCard && this.userCard.is_winner)) {
        return
      }
      
      // Small delay to ensure all marks are processed
      setTimeout(async () => {
        // Double-check before claiming (winner might have been declared during delay)
        if (this.winner || (this.winners && this.winners.length > 0) ||
            (this.game && this.game.status === 'completed') ||
            (this.userCard && this.userCard.is_winner)) {
          return
        }
        
        try {
          await this.handleClaimBingo()
        } catch (error) {
          console.error('Error auto-claiming bingo:', error)
          // If error is "already won" or "game not active", that's expected - ignore it
          const errorMsg = error.response?.data?.error || error.message || ''
          if (errorMsg.includes('already won') || errorMsg.includes('ተቀድመዋል') || 
              errorMsg.includes('not active')) {
            // Expected error - another player won or game ended, just ignore
            return
          }
        }
      }, 500)
    },
    async handleNoWinner() {
      if (this.noWinner) return // Already handling
      
      this.noWinner = true
      
      // End the game on backend
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
        await fetch(`${apiUrl}/admin/games/${this.game.id}/end/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
      } catch (error) {
        console.error('Error ending game:', error)
      }
      
      // Show message for 3 seconds then redirect
      setTimeout(() => {
        if (this.interval) {
          clearInterval(this.interval)
          this.interval = null
        }
        this.$router.push('/select-card')
      }, 3000)
    },
    resumeGame() {
      this.isPaused = false
      // Refresh the page to restore current state
      window.location.reload()
    },
    async loadWinnerCard(data) {
      // Try to get winner's card from game data or card_id
      if (data.card_id) {
        try {
          const card = await getCard(data.card_id)
          this.winnerCard = {
            ...card,
            winning_pattern: data.winning_pattern,
            selected_numbers: data.selected_numbers || card.selected_numbers || [],
            called_numbers: data.called_numbers || [],
            last_called_number: data.last_called_number || null
          }
        } catch (error) {
          console.error('Error loading winner card:', error)
          // Fallback to WebSocket data
          if (data.card_layout) {
            this.winnerCard = {
              card_layout: data.card_layout,
              card_number: data.card_number,
              winning_pattern: data.winning_pattern,
              selected_numbers: data.selected_numbers || [],
              called_numbers: data.called_numbers || [],
              last_called_number: data.last_called_number || null
            }
          }
        }
      } else if (data.card_layout) {
        // Use card layout from WebSocket data
        this.winnerCard = {
          card_layout: data.card_layout,
          card_number: data.card_number,
          winning_pattern: data.winning_pattern,
          selected_numbers: data.selected_numbers || [],
          called_numbers: data.called_numbers || [],
          last_called_number: data.last_called_number || null
        }
      } else if (this.game && this.game.gamecards) {
        const winnerCardData = this.game.gamecards.find(card => 
          card.is_winner || (card.user && card.user.id === data.winner?.id)
        )
        if (winnerCardData) {
          try {
            const card = await getCard(winnerCardData.id)
            this.winnerCard = {
              ...card,
              winning_pattern: data.winning_pattern,
              selected_numbers: data.selected_numbers || card.selected_numbers || [],
              called_numbers: data.called_numbers || [],
              last_called_number: data.last_called_number || null
            }
          } catch (error) {
            console.error('Error loading winner card:', error)
          }
        }
      }
    },
    handleWinnerRedirect() {
      // ATOMIC TRANSITION: Ensure all state is clean before redirecting
      // Stop all intervals and WebSocket connections
      if (this.interval) {
        clearInterval(this.interval)
        this.interval = null
      }
      if (this.ws) {
        this.ws.disconnect()
        this.ws = null
      }
      
      // Reset winner banner flags
      this.showWinnerBanner = false
      this._winnerBannerActive = false
      this.winnerBannerShownAt = null
      
      // Redirect to completed view (which will then redirect to card selection if new game is ready)
      this.$router.push('/completed').catch(() => {
        // Ignore navigation errors
      })
    },
    showNotification(message, type = 'info') {
      this.notificationMessage = message
      this.notificationType = type
    }
  }
}
</script>

<style scoped>
.active-game-view {
  height: 100vh;
  background: var(--primary-light);
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.mode-selector {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 15px;
  background: white;
  margin: 5px;
  border-radius: 8px;
  font-size: 14px;
}

.mode-selector label {
  font-weight: bold;
  color: var(--primary-dark);
}

.mode-selector select {
  padding: 5px 10px;
  border: 2px solid var(--primary-light);
  border-radius: 5px;
  background: white;
  color: var(--primary-dark);
  font-size: 14px;
  cursor: pointer;
}

.mode-selector select:focus {
  outline: none;
  border-color: var(--primary-dark);
}

.game-content {
  display: flex;
  flex-direction: row;
  gap: 8px;
  padding: 2px 5px 5px 5px; /* Reduced top padding to move bingo grid up */
  align-items: stretch;
}

.bingo-screen {
  flex: 0 0 40%;
  min-width: 0;
  max-width: 40%;
  display: flex;
  flex-direction: column;
  align-self: stretch;
  min-height: 100%;
}

/* Ensure bingo grid background covers full section height */
.bingo-screen :deep(.bingo-grid) {
  flex: 1;
  min-height: 100%;
}

.user-card-section {
  flex: 0 0 60%;
  min-width: 0;
  max-width: 60%;
  background: rgb(255, 255, 255);
  padding: 8px;
  border-radius: 8px;
  margin: 5px;
  display: flex;
  flex-direction: column;
}

.compact-call-display {
  width: 100%;
  margin-bottom: 5px;
}

.game-started-text {
  text-align: center;
  font-weight: bold;
  color: var(--primary-dark);
  margin-bottom: 5px;
  font-size: 16px;
  padding: 5px;
  background: var(--primary-light);
  border-radius: 4px;
}

.card-label {
  text-align: center;
  font-weight: bold;
  color: var(--primary-dark);
  margin-bottom: 5px;
  font-size: 20px;
}

.no-card-message {
  text-align: center;
  padding: 10px;
  color: var(--gray-medium);
}

.wait-message-box {
  background: #fff3cd;
  border: 2px solid #ffc107;
  border-radius: 12px;
  padding: 15px 20px;
  margin: 10px 0;
  min-width: 140px;
  min-height: 280px;
  box-sizing: border-box;
  display:flex;
  align-items:center;
  justify-content: center;
}

.wait-message-box h3 {
  color: #856404;
  margin: 0 0 75px 0;
  font-size: 26px;
  display:flex;
  align-items:center;
  justify-content: center;
}

.wait-message-box p {
  color: #856404;
  margin: 10px 0;
  font-size: 18px;
}

.no-winner-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.no-winner-box {
  background: white;
  padding: 40px;
  border-radius: 15px;
  text-align: center;
  max-width: 400px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}

.no-winner-box h2 {
  color: var(--primary-dark);
  margin: 0 0 20px 0;
  font-size: 28px;
}

.no-winner-box p {
  color: var(--gray-medium);
  margin: 10px 0;
  font-size: 16px;
}

/* Tablet view */
@media (min-width: 768px) and (max-width: 1024px) {
  .game-content {
    gap: 6px;
    padding: 4px;
  }
  
  .bingo-screen {
    flex: 0 0 40%;
    max-width: 40%;
  }
  
  .user-card-section {
    flex: 0 0 60%;
    max-width: 60%;
  }
}

/* Mobile view */
@media (max-width: 767px) {
  .game-content {
    flex-direction: row;
    gap: 5px;
    padding: 3px;
  }
  
  .bingo-screen {
    flex: 0 0 40%;
    min-width: 0;
    max-width: 40%;
  }
  
  .user-card-section {
    flex: 0 0 60%;
    min-width: 0;
    max-width: 60%;
    padding: 5px;
    margin: 3px;
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
}

.start-countdown {
  text-align: center;
  padding: 24px;
  background: var(--primary-light);
  border-radius: 16px;
  margin-bottom: 12px;
  box-shadow: var(--card-shadow);
  border: 2px solid rgba(255, 255, 255, 0.5);
}

.countdown-number-small {
  font-size: 64px;
  font-weight: 700;
  color: var(--accent-coral);
  text-shadow: 0 0 15px rgba(255, 107, 107, 0.6);
  margin-bottom: 12px;
  animation: pulse 1s ease-in-out infinite;
}

.countdown-text-small {
  font-size: 18px;
  color: var(--primary-dark);
  font-weight: bold;
}
</style>