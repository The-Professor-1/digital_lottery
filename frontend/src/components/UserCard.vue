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
        v-for="(row, rowIdx) in processedCardLayout"
        :key="rowIdx"
        class="card-row"
      >
        <div class="row-number">{{ rowIdx + 1 }}</div>
        <div
          v-for="(cell, colIdx) in row"
          :key="`${rowIdx}-${colIdx}`"
          class="card-cell"
          :class="{ 
            'free': cell.letter === 'FREE',
            'last-called': lastCalledNumber && Number(cell.number) === Number(lastCalledNumber),
            'winning-cell': isWinningCell(rowIdx, colIdx),
            'marked': cell.marked && !isWinningCell(rowIdx, colIdx) && !(lastCalledNumber && Number(cell.number) === Number(lastCalledNumber))
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
    },
    selectedNumbers: {
      type: Array,
      default: () => []
    },
    calledNumbers: {
      type: Array,
      default: () => []
    },
    lastCalledNumber: {
      type: Number,
      default: null
    }
  },
  computed: {
    processedCardLayout() {
      // Process card layout to mark cells based on called numbers
      if (!this.cardLayout) {
        return this.cardLayout
      }
      
      // Create a deep copy to avoid mutating the original
      const layout = JSON.parse(JSON.stringify(this.cardLayout))
      
      // Use calledNumbers if available, otherwise fall back to selectedNumbers
      const numbersToMark = this.calledNumbers && this.calledNumbers.length > 0 
        ? this.calledNumbers 
        : (this.selectedNumbers || [])
      
      // Mark cells that are in called numbers (or selected numbers as fallback)
      for (let row of layout) {
        for (let cell of row) {
          if (cell.number && numbersToMark.includes(cell.number)) {
            cell.marked = true
          }
        }
      }
      
      return layout
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
      } else if (this.winningPattern === 'corner') {
        // Corner bingo: 4 corners + FREE cell (center)
        return (rowIdx === 0 && colIdx === 0) ||  // Top-left
               (rowIdx === 0 && colIdx === 4) ||  // Top-right
               (rowIdx === 4 && colIdx === 0) ||  // Bottom-left
               (rowIdx === 4 && colIdx === 4) ||  // Bottom-right
               (rowIdx === 2 && colIdx === 2)     // FREE cell (center) - included for visual appeal
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
  border-radius: 16px;
  padding: 12px;
  box-shadow: var(--card-shadow-lg);
  border: 2px solid rgba(0, 180, 216, 0.1);
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
  color: var(--primary-dark);
  font-size: 23px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
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
  color: var(--gray-medium);
  font-weight: 700;
}

.letter-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 20px;
  color: white;
  border-radius: 8px;
  min-height: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s ease;
}

.letter-cell:hover {
  transform: scale(1.05);
}

.letter-cell.letter-b { background: linear-gradient(135deg, #ff6b6b 0%, #ff5252 100%); }
.letter-cell.letter-i { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
.letter-cell.letter-n { background: linear-gradient(135deg, #00b4d8 0%, #0077b6 100%); }
.letter-cell.letter-g { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); }
.letter-cell.letter-o { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); }

.card-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-light);
  border: 2px solid var(--primary-medium);
  border-radius: 8px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 20px;
  min-height: 20px;
  min-width: 0;
  width: 100%;
  padding: 2px;
  box-sizing: border-box;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.1;
  color: var(--gray-dark);
}

.card-cell:hover:not(.marked):not(.free):not(.winning-cell) {
  background: var(--primary-light);
  transform: scale(1.05);
  border-color: var(--primary-dark);
}

.card-cell.marked {
  background: linear-gradient(135deg, var(--success-green) 0%, var(--success-green-dark) 100%);
  color: white;
  border-color: var(--success-green-dark);
  box-shadow: 0 2px 4px rgba(16, 185, 129, 0.3);
}

/* Last called number must override marked class - higher specificity */
.card-cell.last-called.marked {
  /* This will be handled by .card-cell.last-called rule below */
}

.card-cell.free {
  background: linear-gradient(135deg, var(--accent-coral) 0%, var(--accent-coral-dark) 100%);
  color: white;
  border-color: var(--accent-coral-dark);
  cursor: default;
  font-size: 8px;
  padding: 1px;
  word-break: break-word;
  line-height: 1;
  font-weight: 700;
}

.card-cell.winning-cell {
  background: #f1c40f !important;
  border: 2px solid #f39c12 !important;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.8);
  animation: pulse 1s infinite;
}

/* FREE cell that is part of winning pattern (e.g., corner bingo) should also be yellow */
.card-cell.free.winning-cell {
  background: #f1c40f !important;
  border: 2px solid #f39c12 !important;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.8);
  animation: pulse 1s infinite;
  color: white !important;
}

/* Last called number - Use darker yellow with pulse animation like winning line */
/* CRITICAL: Must come after .marked to override it */
.card-cell.last-called,
.card-cell.last-called.marked,
.card-cell.last-called.winning-cell,
.card-cell.last-called.marked.winning-cell {
  color: white !important;
  font-weight: bold !important;
  animation: pulse-last-called 1s infinite !important;
  z-index: 10 !important;
  position: relative !important;
  background: #d4a017 !important; /* Darker yellow */
  border: 3px solid #b8860b !important;
  box-shadow: 0 0 15px rgba(212, 160, 23, 0.8) !important;
  will-change: transform, box-shadow;
}

/* Last called number that is also in winning line - stronger shadow */
.card-cell.last-called.winning-cell,
.card-cell.last-called.marked.winning-cell {
  box-shadow: 0 0 20px rgba(212, 160, 23, 1) !important;
}

@keyframes pulse-last-called {
  0%, 100% {
    background: #d4a017 !important; /* Darker yellow */
    border-color: #b8860b !important;
    box-shadow: 0 0 15px rgba(212, 160, 23, 0.8) !important;
    transform: scale(1.1);
  }
  50% {
    background: #f4d03f !important; /* Lighter yellow for pulse effect */
    border-color: #d4a017 !important;
    box-shadow: 0 0 20px rgba(244, 208, 63, 1) !important;
    transform: scale(1.15);
  }
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
  padding: 12px;
  background: linear-gradient(135deg, var(--gray-medium) 0%, var(--gray-dark) 100%);
  color: white;
  border: none;
  border-radius: 16px;
  font-size: 26px;
  font-weight: 700;
  cursor: not-allowed;
  transition: all 0.3s ease;
  margin-top: 8px;
  position: relative;
  opacity: 0.6;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.bingo-btn:active {
  transform: scale(0.97);
}

.bingo-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, var(--accent-coral-dark) 0%, var(--accent-coral) 70%);
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(255, 107, 107, 0.4);
}

.bingo-btn:disabled {
  background: linear-gradient(135deg, var(--gray-medium) 0%, var(--gray-dark) 100%);
  cursor: not-allowed;
  opacity: 0.6;
}

.bingo-btn.enabled:not(:disabled) {
  background: linear-gradient(135deg, var(--accent-coral) 0%, var(--accent-coral-dark) 100%);
  cursor: pointer;
  opacity: 1;
  box-shadow: 0 4px 12px rgba(255, 107, 107, 0.5);
  animation: pulse-coral 2s infinite;
}

@keyframes pulse-coral {
  0%, 100% {
    box-shadow: 0 4px 12px rgba(255, 107, 107, 0.5);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 6px 20px rgba(255, 107, 107, 0.8);
    transform: scale(1.02);
  }
}
</style>

