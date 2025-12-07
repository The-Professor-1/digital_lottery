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
}

.card-option {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #95a5a6;
  color: white;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  font-size: 12px;
  min-height: 25px;
  min-width: 25px;
}

.card-option:disabled,
.card-option.disabled {
  cursor: pointer; /* Allow clicking to change card */
  opacity: 0.8;
}

.card-option:hover:not(.taken):not(.selected) {
  transform: scale(1.1);
  box-shadow: 0 4px 8px rgba(0,0,0,0.2);
  background: #7f8c8d;
}

.card-option.taken {
  background: var(--orange);
  cursor: not-allowed;
  opacity: 1;
}

.card-option.selected {
  background: var(--green);
  transform: scale(1.1);
  box-shadow: 0 0 15px rgba(46, 204, 113, 0.5);
  cursor: pointer; /* Allow clicking selected card to unselect */
}

.card-option.taken.selected {
  cursor: pointer; /* Allow clicking selected card to unselect even if in takenCards */
  background: var(--green);
}
</style>

