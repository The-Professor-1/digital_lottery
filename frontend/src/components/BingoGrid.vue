<template>
  <div class="bingo-grid">
    <div class="bingo-header">
      <div class="letter-cell" :class="`letter-${letter.toLowerCase()}`" v-for="letter in ['B', 'I', 'N', 'G', 'O']" :key="letter">
        {{ letter }}
      </div>
    </div>
    <div class="grid-container">
      <div
        v-for="col in columns"
        :key="col.letter"
        class="column"
      >
        <div
          v-for="num in col.numbers"
          :key="num"
          class="number-cell"
          :class="{ 
            'called': isCalled(num), 
            'current': isCurrent(num),
            [`letter-${col.letter.toLowerCase()}`]: true
          }"
        >
          {{ num }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'BingoGrid',
  props: {
    calledNumbers: {
      type: Array,
      default: () => []
    },
    currentNumber: {
      type: Object,
      default: null
    }
  },
  computed: {
    columns() {
      return [
        { letter: 'B', numbers: Array.from({ length: 15 }, (_, i) => i + 1) },
        { letter: 'I', numbers: Array.from({ length: 15 }, (_, i) => i + 16) },
        { letter: 'N', numbers: Array.from({ length: 15 }, (_, i) => i + 31) },
        { letter: 'G', numbers: Array.from({ length: 15 }, (_, i) => i + 46) },
        { letter: 'O', numbers: Array.from({ length: 15 }, (_, i) => i + 61) },
      ]
    }
  },
  methods: {
    isCalled(num) {
      return this.calledNumbers.includes(num)
    },
    isCurrent(num) {
      return this.currentNumber && this.currentNumber.number === num
    }
  }
}
</script>

<style scoped>
.bingo-grid {
  background: var(--primary-light);
  padding: 6px;
  border-radius: 12px;
  margin: 5px;
  width: 100%;
  height: 50px;
  box-sizing: border-box;
  box-shadow: var(--card-shadow);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.bingo-header {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
  margin-bottom: 2px;
  width: 100%;
  box-sizing: border-box;
}

.letter-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 30px;
  color: white;
  border-radius: 8px;
  min-height: 10px;
  padding: 0;
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

.grid-container {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
  width: 100%;
  box-sizing: border-box;
}

.column {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.number-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--white);
  color: var(--gray-dark);
  font-weight: 600;
  border: 2px solid var(--primary-medium);
  border-radius: 6px;
  font-size: 12px;
  cursor: default;
  min-height: 12px;
  padding: 0;
  line-height: 1;
  transition: all 0.2s ease;
}

@media (max-width: 767px) {
  .number-cell {
    font-size: 10px;
    min-height: 10px;
  }
  
  .letter-cell {
    font-size: 16px;
    min-height: 18px;
  }
}

.number-cell.called {
  background: linear-gradient(135deg, var(--success-green) 0%, var(--success-green-dark) 100%);
  color: white;
  border-color: var(--success-green-dark);
  box-shadow: 0 2px 4px rgba(16, 185, 129, 0.3);
}

.number-cell.current {
  background: linear-gradient(135deg, var(--accent-coral) 0%, var(--accent-coral-dark) 100%);
  color: white;
  border-color: var(--accent-coral-dark);
  transform: scale(1.15);
  box-shadow: 0 0 15px rgba(255, 107, 107, 0.6);
  z-index: 10;
  position: relative;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1.15); }
  50% { transform: scale(1.2); }
}
</style>

