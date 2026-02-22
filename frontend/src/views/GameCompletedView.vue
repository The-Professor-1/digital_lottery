<template>
  <div class="completed-view">
    <GameStatus status="completed" />
    <WinnerBanner
      v-if="game?.winner"
      :winner="game.winner"
      :prize="game.total_derash"
      :winner-card="winnerCard"
    />
  </div>
</template>

<script>
import GameStatus from '../components/GameStatus.vue'
import WinnerBanner from '../components/WinnerBanner.vue'
import { getCurrentGame, getCard } from '../services/api'

export default {
  name: 'GameCompletedView',
  components: {
    GameStatus,
    WinnerBanner
  },
  data() {
    return {
      game: null,
      interval: null,
      winnerCard: null,
      redirecting: false
    }
  },
  async mounted() {
    // Load game immediately and redirect as soon as new game is available
    this.loadGame()
    // Poll more frequently for faster transition (1 second)
    this.interval = setInterval(this.loadGame, 1000)
  },
  beforeUnmount() {
    if (this.interval) {
      clearInterval(this.interval)
    }
  },
  methods: {
    async loadGame() {
      // Prevent multiple redirects
      if (this.redirecting) return
      
      try {
        const game = await getCurrentGame()
        this.game = game
        
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
        
        // Redirect: if game is completed, go to card selection for next round; if waiting/active, go to select or game
        if (game && (game.status === 'waiting' || game.status === 'active')) {
          this.redirecting = true
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          if (game.status === 'waiting') {
            this.$router.push('/select-card').catch(() => {})
          } else if (game.status === 'active') {
            this.$router.push('/game').catch(() => {})
          }
        } else if (game && game.status === 'completed') {
          // Game just finished - go to card selection to join next game
          this.redirecting = true
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/select-card').catch(() => {})
        }
      } catch (error) {
        // No game found - backend should create one soon, keep polling
        if (error.response?.status === 404) {
          console.log('No game found yet, waiting for backend to create one...')
        }
      }
    }
  }
}
</script>

<style scoped>
.completed-view {
  min-height: 100vh;
  background: var(--primary-light);
  position: relative;
}

</style>

