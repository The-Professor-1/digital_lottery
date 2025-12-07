<template>
  <div class="waiting-view">
    <InfoBar
      :derash="game?.total_derash || 0"
      :players="game?.total_players || 0"
      :bet="game?.bet_amount || 0"
      :call="game?.current_call_count || 0"
    />
    <GameStatus :status="game?.status || 'waiting'" />
    <div class="waiting-message">
      <p>ይህ ጨዋታ እስኪጠናቀቅ ይጠብቁ</p>
    </div>
  </div>
</template>

<script>
import InfoBar from '../components/InfoBar.vue'
import GameStatus from '../components/GameStatus.vue'
import { getCurrentGame } from '../services/api'

export default {
  name: 'WaitingView',
  components: {
    InfoBar,
    GameStatus
  },
  data() {
    return {
      game: null,
      interval: null
    }
  },
  async mounted() {
    await this.loadGame()
    this.interval = setInterval(this.loadGame, 3000) // Hardcoded 3 seconds
  },
  beforeUnmount() {
    if (this.interval) {
      clearInterval(this.interval)
    }
  },
  methods: {
    async loadGame() {
      try {
        const game = await getCurrentGame()
        this.game = game
        
        // Redirect if game status changes
        if (game.status === 'active') {
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/game')
        } else if (game.status === 'completed') {
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/completed')
        } else if (game.status === 'waiting') {
          // If game is waiting, redirect to card selection
          if (this.interval) {
            clearInterval(this.interval)
            this.interval = null
          }
          this.$router.push('/select-card')
        }
      } catch (error) {
        console.error('Error loading game:', error)
        // If no game exists, the backend should auto-create one
        // But if it still fails, show message
        if (error.response?.status === 404) {
          console.log('No active game found. The system will create one automatically...')
          // Stay on waiting page and retry after a delay
          // The backend should auto-create a game on next request
        }
      }
    }
  }
}
</script>

<style scoped>
.waiting-view {
  min-height: 100vh;
  background: var(--purple-light);
}

.waiting-message {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 20px;
}

.waiting-message p {
  font-size: 24px;
  font-weight: bold;
  color: var(--purple-dark);
  text-align: center;
}
</style>

