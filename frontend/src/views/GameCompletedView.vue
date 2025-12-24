<template>
  <div class="completed-view">
    <GameStatus status="completed" />
    <WinnerBanner
      v-if="game?.winner"
      :winner="game.winner"
      :prize="game.total_derash"
      :winner-card="winnerCard"
    />
    <div class="next-game-container">
      <div class="next-game-message">
        <p>የሚቀጥለውን ጨዋታ ለመጀመር...</p>
      </div>
      <div class="timer-container">
        <Timer :seconds="timerSeconds" :large="true" />
      </div>
    </div>
  </div>
</template>

<script>
import GameStatus from '../components/GameStatus.vue'
import WinnerBanner from '../components/WinnerBanner.vue'
import Timer from '../components/Timer.vue'
import { getCurrentGame, getCard } from '../services/api'

export default {
  name: 'GameCompletedView',
  components: {
    GameStatus,
    WinnerBanner,
    Timer
  },
  data() {
    return {
      game: null,
      timerSeconds: 10, // Changed from 30 to 10 seconds
      interval: null,
      timerInterval: null,
      winnerCard: null
    }
  },
  async mounted() {
    // Start timer immediately (don't wait for API call) to prevent blank page
    this.startTimer()
    // Load game in background (non-blocking)
    this.loadGame()
    this.interval = setInterval(this.loadGame, 3000) // Hardcoded 3 seconds
  },
  beforeUnmount() {
    if (this.interval) {
      clearInterval(this.interval)
    }
    if (this.timerInterval) {
      clearInterval(this.timerInterval)
    }
  },
  methods: {
    async loadGame() {
      try {
        const game = await getCurrentGame()
        this.game = game
        
        // Timer is fixed to 10 seconds, no need to update from settings
        
        // Load winner's card if there's a winner
        if (game && game.winner && game.gamecards && game.gamecards.length > 0) {
          const winnerCardData = game.gamecards.find(card => card.is_winner || card.user === game.winner.id)
          if (winnerCardData) {
            try {
              const card = await getCard(winnerCardData.id)
              this.winnerCard = card
            } catch (error) {
              console.error('Error loading winner card:', error)
            }
          }
        }
        
        // Redirect immediately if new game starts (don't wait for timer)
        if (game && game.status === 'waiting') {
          // Stop timer and redirect immediately
          if (this.timerInterval) {
            clearInterval(this.timerInterval)
            this.timerInterval = null
          }
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/select-card')
        } else if (game && game.status === 'active') {
          // Stop timer and redirect immediately
          if (this.timerInterval) {
            clearInterval(this.timerInterval)
            this.timerInterval = null
          }
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/game')
        }
      } catch (error) {
        // No game found - this is OK, we'll wait for timer to finish
        // The timer will handle redirecting to card selection
        if (error.response?.status === 404) {
          console.log('No game found, waiting for timer to finish...')
          // Don't redirect immediately - let timer finish first
        }
      }
    },
    startTimer() {
      // Fixed to 10 seconds for next game countdown
      this.timerSeconds = 10
      
      this.timerInterval = setInterval(() => {
        if (this.timerSeconds > 0) {
          this.timerSeconds--
        } else {
          clearInterval(this.timerInterval)
          this.timerInterval = null
          // Timer ended, create new game or redirect to card selection
          this.createNewGame()
        }
      }, 1000)
    },
    async createNewGame() {
      try {
        // Try to get current game first
        const game = await getCurrentGame()
        if (game && game.status === 'waiting') {
          this.$router.push('/select-card')
        } else if (game && game.status === 'active') {
          this.$router.push('/game')
        } else {
          // Game might be creating, wait a bit and check again
          setTimeout(async () => {
            try {
              const game = await getCurrentGame()
              if (game && game.status === 'waiting') {
                this.$router.push('/select-card')
              } else if (game && game.status === 'active') {
                this.$router.push('/game')
              }
            } catch (error) {
              // Still no game, redirect to card selection (backend should create one)
              this.$router.push('/select-card')
            }
          }, 1000)
        }
      } catch (error) {
        // No game exists yet, redirect to card selection
        // The backend should auto-create games, so card selection will trigger it
        this.$router.push('/select-card')
      }
    }
  }
}
</script>

<style scoped>
.completed-view {
  min-height: 100vh;
  background: var(--purple-light);
  position: relative;
}

.next-game-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 20px;
}

.next-game-message {
  text-align: center;
  padding: 20px;
  margin-bottom: 40px;
}

.next-game-message p {
  font-size: 24px;
  color: var(--purple-dark);
  font-weight: bold;
}

.timer-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
}
</style>

