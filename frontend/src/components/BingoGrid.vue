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
  background: var(--purple-light);
  padding: 5px;
  border-radius: 6px;
  margin: 5px;
  width: 100%;
  height: 50px;
  box-sizing: border-box;
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
  font-weight: bold;
  font-size: 30px;
  color: white;
  border-radius: 2px;
  min-height: 10px;
  padding: 0;
}

.letter-cell.letter-b { background: #ff6b35; }
.letter-cell.letter-i { background: #2ecc71; }
.letter-cell.letter-n { background: #3498db; }
.letter-cell.letter-g { background: #e74c3c; }
.letter-cell.letter-o { background: #9b59b6; }

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
  background: #ecf0f1;
  color: #2c3e50;
  font-weight: bold;
  border: 1px solid var(--purple-medium);
  border-radius: 2px;
  font-size: 12px;
  cursor: default;
  min-height: 12px;
  padding: 0;
  line-height: 1;
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
  background: var(--green);
  color: white;
  border-color: var(--green);
}

.number-cell.current {
  background: var(--orange);
  color: white;
  border-color: var(--orange);
  transform: scale(1.1);
  box-shadow: 0 0 10px rgba(255, 107, 53, 0.5);
  z-index: 10;
  position: relative;
}
</style>

