<template>
  <div class="card-selector">
    <div class="cards-grid">
      <div
        v-for="num in cardNumbers"
        :key="num"
        class="card-option"
        :class="{ 
          'taken': isTaken(num), 
          'selected': selectedCard === num
        }"
        @click="selectCard(num)"
      >
        {{ num }}
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CardSelector',
  props: {
    availableCards: {
      type: Array,
      default: () => []
    },
    takenCards: {
      type: Array,
      default: () => []
    },
    selectedCard: {
      type: Number,
      default: null
    },
    totalCards: {
      type: Number,
      default: 200
    }
  },
  computed: {
    cardNumbers() {
      return Array.from({ length: this.totalCards }, (_, i) => i + 1)
    }
  },
  methods: {
    isTaken(num) {
      return this.takenCards.includes(num)
    },
    selectCard(num) {
      // Allow clicking if:
      // 1. Card is not taken (available)
      // 2. Card is the currently selected card (for unselection)
      // Only prevent clicking if card is taken by someone else
      if (!this.isTaken(num) || this.selectedCard === num) {
        this.$emit('select-card', num)
      }
    }
  }
}
</script>

<style scoped>
.card-selector {
  padding: 0;
  background: transparent;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 4px;
  margin-top: 5px;
}

.card-option {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background:#5e6269;
  color: white;
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  margin-top: 2px;
  font-size: 15px;
  min-height: 28px;
  min-width: 28px;
  border: 2px solid transparent;
}

.card-option:disabled,
.card-option.disabled {
  cursor: pointer; /* Allow clicking to change card */
  opacity: 0.8;
}

.card-option:hover:not(.taken):not(.selected) {
  transform: scale(1.1) translateY(-2px);
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.25);
  border-color: var(--primary-medium);
  background: linear-gradient(135deg, var(--primary-medium) 0%, var(--primary-dark) 100%);
}

.card-option.taken {
  background: linear-gradient(135deg, var(--accent-coral) 0%, var(--accent-coral-dark) 100%);
  cursor: not-allowed;
  opacity: 0.85;
  border-color: var(--accent-coral-dark);
}

.card-option.selected {
  background: linear-gradient(135deg, var(--success-green) 0%, var(--success-green-dark) 100%);
  transform: scale(1.15);
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.5);
  cursor: pointer;
  border-color: var(--success-green-dark);
  animation: selectedPulse 2s infinite;
}

@keyframes selectedPulse {
  0%, 100% { box-shadow: 0 0 20px rgba(16, 185, 129, 0.5); }
  50% { box-shadow: 0 0 25px rgba(16, 185, 129, 0.7); }
}

.card-option.taken.selected {
  cursor: pointer;
  background: linear-gradient(135deg, var(--success-green) 0%, var(--success-green-dark) 100%);
  border-color: var(--success-green-dark);
  opacity: 1;
}
</style>

