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
  color: #000; /* Default black text for normal cells */
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

/* Last called number must override marked class - higher specificity */
.card-cell.last-called.marked {
  /* This will be handled by .card-cell.last-called rule below */
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

