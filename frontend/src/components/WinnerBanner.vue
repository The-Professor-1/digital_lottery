<template>
  <div class="winner-banner" v-if="(winner && winner !== null) || (winners && winners.length > 0)">
    <div class="banner-content">
      <h1>BINGO!</h1>
      
      <!-- Multiple Winners -->
      <div v-if="winners && winners.length > 1" class="multiple-winners">
        <div class="winners-header">
          <div class="winner-count-text">{{ winners.length }} አሸናፊዎች</div>
          <div class="split-prize-text">ሽልማት ተከፋፍሏል</div>
        </div>
        
        <div class="winners-list">
          <div 
            v-for="(winnerData, index) in winners" 
            :key="winnerData.card_id || index"
            class="winner-item"
          >
            <div class="winner-item-header">
              <div class="winner-badge">{{ index + 1 }}</div>
              <div class="winner-name-multiple">
                <span v-if="isWinnerCurrentUser(winnerData.winner)" class="winner-text-you-small">እርስዎ</span>
                <span v-else>{{ winnerData.winner?.username || 'Winner' }}</span>
              </div>
            </div>
            <UserCard
              v-if="winnerData.card_layout"
              :card-layout="winnerData.card_layout"
              :card-number="winnerData.card_number"
              :can-claim-bingo="false"
              :hide-bingo-button="true"
              :winning-pattern="winnerData.winning_pattern || winningPattern"
              :selected-numbers="winnerData.selected_numbers || []"
              :called-numbers="winnerData.called_numbers || []"
              :last-called-number="getLastCalledNumber(winnerData)"
              :is-winner-banner="true"
              class="winner-card-display-small"
            />
            <div class="winner-prize">ሽልማት: {{ winnerData.prize || prize }} ብር</div>
          </div>
        </div>
        
        <div class="total-prize-section">
          <div class="total-prize-label">ጠቅላላ ሽልማት:</div>
          <div class="total-prize-value">{{ totalPrize || prize }} ብር</div>
        </div>
      </div>
      
      <!-- Single Winner (backward compatible) -->
      <div v-else class="single-winner">
        <div class="winner-info">
          <div v-if="isCurrentUser" class="winner-message">
            <div class="winner-text-you">አሸንፈዋል</div>
          </div>
          <div v-else class="winner-message">
            <div class="winner-name">{{ displayWinner.username || displayWinner.name || 'Winner' }}</div>
            <div class="winner-text">ጨዋታውን አሸንፏል</div>
          </div>
        </div>
        <UserCard
          v-if="cardData"
          :card-layout="cardData.card_layout"
          :card-number="cardData.card_number"
          :can-claim-bingo="false"
          :hide-bingo-button="true"
          :winning-pattern="cardData.winning_pattern || winningPattern"
          :selected-numbers="cardData.selected_numbers || []"
          :called-numbers="cardData.called_numbers || []"
          :last-called-number="getLastCalledNumber(cardData)"
          class="winner-card-display"
        />
        <div class="prize">ሽልማት: {{ displayPrize }} ብር</div>
      </div>
      
      <div class="timer-section">
        <div class="timer-label">በመመለስ ላይ:</div>
        <div class="timer-value">{{ timer }}s</div>
      </div>
    </div>
  </div>
</template>

<script>
import UserCard from './UserCard.vue'

export default {
  name: 'WinnerBanner',
  components: {
    UserCard
  },
  props: {
    winner: {
      type: Object,
      default: null
    },
    winners: {
      type: Array,
      default: null
    },
    prize: {
      type: [Number, String],
      default: 0
    },
    totalPrize: {
      type: [Number, String],
      default: null
    },
    winnerCard: {
      type: Object,
      default: null
    },
    isCurrentUser: {
      type: Boolean,
      default: false
    },
    winningPattern: {
      type: String,
      default: null
    },
    currentUserId: {
      type: [Number, String],
      default: null
    }
  },
  data() {
    return {
      timer: 8,
      timerInterval: null,
      minDisplayTime: 8000,
      startTime: null,
      canRedirect: false
    }
  },
  computed: {
    displayWinner() {
      // First try to get from winner object
      if (this.winner && typeof this.winner === 'object' && Object.keys(this.winner).length > 0) {
        if (this.winner.username || this.winner.name) {
          return this.winner
        }
      }
      
      // If winner is null/empty, try to get username from winners array (for fake users)
      if (this.winners && this.winners.length > 0) {
        const firstWinner = this.winners[0]
        if (firstWinner.username) {
          return { username: firstWinner.username, name: firstWinner.username }
        }
        if (firstWinner.winner && firstWinner.winner.username) {
          return firstWinner.winner
        }
      }
      
      // Fallback to "Winner" if nothing found
      return { username: 'Winner', name: 'Winner' }
    },
    displayPrize() {
      const prize = this.prize !== null && this.prize !== undefined ? this.prize : 0
      return prize
    },
    cardData() {
      // First try winnerCard prop
      if (this.winnerCard && this.winnerCard.card_layout) {
        return this.winnerCard
      }
      // If not available, try winners array (for single winner case)
      if (this.winners && this.winners.length > 0 && this.winners[0].card_layout) {
        return this.winners[0]
      }
      // Return null if no card data available
      return null
    }
  },
  mounted() {
    this.startTime = Date.now()
    this.canRedirect = false
    // Ensure banner shows for minimum 8 seconds total
    // Start timer immediately, but don't allow redirect until 8 seconds have passed
    this.startTimer()
    setTimeout(() => {
      this.canRedirect = true
      // If timer already finished, trigger redirect now
      if (this.timer <= 0) {
        this.$emit('redirect')
      }
    }, this.minDisplayTime) // Wait 8 seconds before allowing redirect
  },
  beforeUnmount() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval)
    }
  },
  methods: {
    startTimer() {
      this.timer = 8 // Start at 8 seconds
      this.timerInterval = setInterval(() => {
        if (this.timer > 0) {
          this.timer--
        } else {
          clearInterval(this.timerInterval)
          this.timerInterval = null
          // Only redirect if minimum display time has passed
          if (this.canRedirect) {
            this.$emit('redirect')
          }
          // If not ready yet, wait for canRedirect to be set
        }
      }, 1000)
    },
    isWinnerCurrentUser(winner) {
      if (!this.currentUserId || !winner) return false
      return winner.id === this.currentUserId || winner.id === Number(this.currentUserId)
    },
    getLastCalledNumber(winnerData) {
      if (winnerData && winnerData.last_called_number !== null && winnerData.last_called_number !== undefined) {
        return winnerData.last_called_number
      }
      if (!winnerData || !winnerData.called_numbers || winnerData.called_numbers.length === 0) {
        return null
      }
      return winnerData.called_numbers[winnerData.called_numbers.length - 1]
    }
  }
}
</script>

<style scoped>
.winner-banner {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: linear-gradient(135deg, var(--accent-coral) 0%, var(--accent-coral-dark) 100%);
  color: white;
  padding: 20px;
  border-radius: 14px;
  text-align: center;
  z-index: 1000;
  box-shadow: var(--card-shadow-lg);
  border: 2px solid rgba(255, 255, 255, 0.2);
  min-width: 350px;
  max-width: 85vw;
  max-height: 85vh;
  overflow-y: auto;
}

.banner-content h1 {
  font-size: 40px;
  margin: 0 0 10px 0;
  text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
  font-weight: bold;
}

.winner-info {
  margin: 10px 0;
}

.winner-message {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.winner-name {
  display: inline-block;
  background: #2ecc71;
  color: white;
  padding: 8px 15px;
  border-radius: 8px;
  font-size: 22px;
  font-weight: bold;
}

.winner-text {
  display: inline-block;
  font-size: 20px;
}

.winner-text-you {
  font-size: 20px;
  font-weight: bold;
  color: white;
}

.winner-card-display {
  margin: 12px auto;
  max-width: 260px;
  background: white;
  border-radius: 8px;
  padding: 8px;
  transform: scale(0.75);
  transform-origin: center;
}

.prize {
  font-size: 18px;
  font-weight: bold;
  margin-top: 10px;
  padding: 8px;
  background: rgba(255,255,255,0.2);
  border-radius: 6px;
}

.timer-section {
  margin-top: 12px;
  padding: 8px;
  background: rgba(255,255,255,0.2);
  border-radius: 6px;
}

.timer-label {
  font-size: 12px;
  margin-bottom: 4px;
}

.timer-value {
  font-size: 24px;
  font-weight: bold;
  color: white;
}

/* Multiple Winners Styles */
.multiple-winners {
  width: 100%;
}

.winners-header {
  margin: 10px 0;
}

.winner-count-text {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 4px;
}

.split-prize-text {
  font-size: 14px;
  opacity: 0.9;
}

.winners-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin: 12px 0;
  max-height: 420px;
  overflow-y: auto;
}

.winner-item {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 12px;
  text-align: center;
}

.winner-item-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 6px;
}

.winner-badge {
  background: #2ecc71;
  color: white;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 13px;
}

.winner-name-multiple {
  font-size: 15px;
  font-weight: bold;
}

.winner-text-you-small {
  background: linear-gradient(135deg, var(--success-green) 0%, var(--success-green-dark) 100%);
  color: white;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 700;
  font-size: 13px;
  box-shadow: 0 2px 4px rgba(16, 185, 129, 0.3);
}

.winner-card-display-small {
  margin: 8px auto;
  max-width: 220px;
  background: white;
  border-radius: 8px;
  padding: 6px;
  transform: scale(0.88);
  transform-origin: center;
}

.winner-prize {
  font-size: 14px;
  font-weight: bold;
  margin-top: 8px;
  padding: 6px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 5px;
}

.total-prize-section {
  margin-top: 12px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 8px;
  border: 2px solid rgba(255, 255, 255, 0.3);
}

.total-prize-label {
  font-size: 13px;
  margin-bottom: 4px;
  opacity: 0.9;
}

.total-prize-value {
  font-size: 20px;
  font-weight: bold;
}

.single-winner {
  width: 100%;
}
</style>

