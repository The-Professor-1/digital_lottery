<template>
  <div class="user-card">
    <div class="card-header">
      <div class="card-number">ካርድ #{{ cardNumber }}</div>
    </div>
    <div class="card-grid">
      <!-- Header row with letters -->
      <div class="card-row header-row">
        <div class="empty-cell"></div>
        <div class="letter-cell letter-b">B</div>
        <div class="letter-cell letter-i">I</div>
        <div class="letter-cell letter-n">N</div>
        <div class="letter-cell letter-g">G</div>
        <div class="letter-cell letter-o">O</div>
      </div>
      <!-- Number rows -->
      <div
        v-for="(row, rowIdx) in cardLayout"
        :key="rowIdx"
        class="card-row"
      >
        <div class="row-number">{{ rowIdx + 1 }}</div>
        <div
          v-for="(cell, colIdx) in row"
          :key="`${rowIdx}-${colIdx}`"
          class="card-cell"
          :class="{ 
            'marked': cell.marked, 
            'free': cell.letter === 'FREE',
            'winning-cell': isWinningCell(rowIdx, colIdx)
          }"
          @click="handleCellClick(cell)"
        >
          <span v-if="cell.letter === 'FREE'">FREE</span>
          <span v-else>{{ cell.number }}</span>
        </div>
      </div>
    </div>
    <button
      v-if="!hideBingoButton"
      class="bingo-btn"
      :class="{ 'enabled': canClaimBingo }"
      :disabled="!canClaimBingo"
      @click="claimBingo"
    >
      ቢንጎ!
    </button>
  </div>
</template>

<script>
export default {
  name: 'UserCard',
  props: {
    cardLayout: {
      type: Array,
      default: () => []
    },
    cardNumber: {
      type: [Number, String],
      default: 0
    },
    canClaimBingo: {
      type: Boolean,
      default: false
    },
    winningPattern: {
      type: String,
      default: null
    },
    hideBingoButton: {
      type: Boolean,
      default: false
    }
  },
  methods: {
    handleCellClick(cell) {
      if (cell.letter === 'FREE' || cell.marked) {
        return
      }
      this.$emit('mark-number', cell.number)
    },
    claimBingo() {
      if (this.canClaimBingo) {
        this.$emit('claim-bingo')
      }
    },
    isWinningCell(rowIdx, colIdx) {
      if (!this.winningPattern) return false
      
      if (this.winningPattern.startsWith('row_')) {
        const winRow = parseInt(this.winningPattern.split('_')[1])
        return rowIdx === winRow
      } else if (this.winningPattern.startsWith('col_')) {
        const winCol = parseInt(this.winningPattern.split('_')[1])
        return colIdx === winCol
      } else if (this.winningPattern === 'diagonal_1') {
        return rowIdx === colIdx
      } else if (this.winningPattern === 'diagonal_2') {
        return rowIdx === 4 - colIdx
      } else if (this.winningPattern === 'full_card') {
        return true
      }
      return false
    }
  }
}
</script>

<style scoped>
.user-card {
  background: white;
  border-radius: 8px;
  padding: 8px;
}

.user-card.compact {
  transform: scale(0.5);
  transform-origin: top center;
  margin-top: -50%;
  margin-bottom: -50%;
}

.card-header {
  text-align: center;
  margin-bottom: 5px;
}

.card-number {
  color: var(--purple-dark);
  font-size: 12px;
  font-weight: bold;
}

.card-grid {
  margin-bottom: 8px;
  width: 100%;
  box-sizing: border-box;
}

.card-row {
  display: grid;
  grid-template-columns: 20px repeat(5, minmax(0, 1fr));
  gap: 2px;
  margin-bottom: 2px;
  width: 100%;
  box-sizing: border-box;
}

.header-row {
  margin-bottom: 3px;
}

.empty-cell {
  /* Empty space for row numbers */
}

.row-number {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  color: var(--gray);
  font-weight: bold;
}

.letter-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 20px;
  color: white;
  border-radius: 3px;
  min-height: 20px;
}

.letter-cell.letter-b { background: #ff6b35; }
.letter-cell.letter-i { background: #2ecc71; }
.letter-cell.letter-n { background: #3498db; }
.letter-cell.letter-g { background: #e74c3c; }
.letter-cell.letter-o { background: #9b59b6; }

.card-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
  border: 1px solid var(--purple-medium);
  border-radius: 3px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.1s ease-out; /* Faster transition for immediate feedback */
  font-size: 20px;
  min-height: 20px;
  min-width: 0;
  width: 100%;
  padding: 2px;
  box-sizing: border-box;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.1;
}

.card-cell:hover:not(.marked):not(.free) {
  background: #e8d5ff;
  transform: scale(1.05);
}

.card-cell.marked {
  background: var(--green);
  color: white;
  border-color: var(--green);
}

.card-cell.free {
  background: var(--orange);
  color: white;
  border-color: var(--orange);
  cursor: default;
  font-size: 8px;
  padding: 1px;
  word-break: break-word;
  line-height: 1;
}

.card-cell.winning-cell {
  background: #f1c40f !important;
  border: 2px solid #f39c12 !important;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.8);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

.bingo-btn {
  width: 100%;
  padding: 8px;
  background: var(--gray); /* Initial/unclickable state: grey */
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 25px;
  font-weight: bold;
  cursor: not-allowed;
  transition: all 0.1s ease-out; /* Faster transition for immediate feedback */
  margin-top: 5px;
  position: relative;
  opacity: 0.6;
}

.bingo-btn:active {
  transform: scale(0.95); /* Immediate visual feedback on click */
}

.bingo-btn:hover:not(:disabled) {
  background: var(--orange-dark);
  transform: scale(1.05);
}

.bingo-btn:disabled {
  background: var(--gray);
  cursor: not-allowed;
  opacity: 0.6;
}

.bingo-btn.enabled:not(:disabled) {
  background: var(--orange); /* Clickable state: orange */
  cursor: pointer;
  opacity: 1;
  animation: pulse-orange 1.5s infinite;
}

@keyframes pulse-orange {
  0%, 100% {
    box-shadow: 0 0 8px rgba(255, 107, 53, 0.6);
  }
  50% {
    box-shadow: 0 0 20px rgba(255, 107, 53, 1);
  }
}
</style>

