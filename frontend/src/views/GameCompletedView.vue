<template>
  <div class="completed-view">
    <InfoBar
      :derash="game?.total_derash || 0"
      :players="game?.total_players || 0"
      :bet="game?.bet_amount || 0"
      :call="game?.current_call_count || 0"
    />
    <GameStatus status="completed" />
    <WinnerBanner
      v-if="game?.winner"
      :winner="game.winner"
      :prize="game.total_derash"
      :winner-card="winnerCard"
    />
    <Timer :seconds="timerSeconds" />
    <div class="next-game-message">
      <p>የሚቀጥለውን ጨዋታ ለመጀመር...</p>
    </div>
  </div>
</template>

<script>
import InfoBar from '../components/InfoBar.vue'
import GameStatus from '../components/GameStatus.vue'
import WinnerBanner from '../components/WinnerBanner.vue'
import Timer from '../components/Timer.vue'
import { getCurrentGame, getCard } from '../services/api'

export default {
  name: 'GameCompletedView',
  components: {
    InfoBar,
    GameStatus,
    WinnerBanner,
    Timer
  },
  data() {
    return {
      game: null,
      timerSeconds: 30, // Will be set from game.card_selection_timer
      interval: null,
      timerInterval: null,
      winnerCard: null
    }
  },
  async mounted() {
    await this.loadGame()
    this.startTimer()
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
        
        // Update timer seconds from game settings if available and timer not started
        if (game && game.card_selection_timer && !this.timerInterval) {
          this.timerSeconds = game.card_selection_timer
        }
        
        // Load winner's card if there's a winner
        if (game.winner && game.gamecards && game.gamecards.length > 0) {
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
        
        // Redirect if new game starts
        if (game.status === 'waiting') {
          this.$router.push('/select-card')
        } else if (game.status === 'active') {
          this.$router.push('/game')
        }
      } catch (error) {
        // No game found, create new one after timer
        if (error.response?.status === 404 && this.timerSeconds <= 0) {
          this.createNewGame()
        }
      }
    },
    startTimer() {
      // Get timer value from game settings, default to 30 if not available
      const timerValue = this.game?.card_selection_timer || 30
      this.timerSeconds = timerValue
      
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
        if (game.status === 'waiting') {
          this.$router.push('/select-card')
        }
      } catch (error) {
        // No game exists, redirect to waiting page
        // The backend should auto-create games, but for now just redirect
        this.$router.push('/waiting')
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

.next-game-message {
  text-align: center;
  padding: 20px;
  margin-top: 20px;
}

.next-game-message p {
  font-size: 18px;
  color: var(--purple-dark);
  font-weight: bold;
}
</style>

