<template>
  <div class="game-status">
    <div class="bingo-letters">
      <span class="letter b">B</span>
      <span class="letter i">I</span>
      <span class="letter n">N</span>
      <span class="letter g">G</span>
      <span class="letter o">O</span>
    </div>
    <div class="status-text" :class="statusClass">{{ statusText }}</div>
  </div>
</template>

<script>
export default {
  name: 'GameStatus',
  props: {
    status: {
      type: String,
      default: 'waiting'
    }
  },
  computed: {
    statusText() {
      if (this.status === 'active') return 'የጀመረ'
      if (this.status === 'completed') return 'ተጠናቋል'
      return 'በመጠባበቅ ላይ'
    },
    statusClass() {
      return {
        'status-waiting': this.status === 'waiting',
        'status-active': this.status === 'active',
        'status-completed': this.status === 'completed'
      }
    }
  }
}
</script>

<style scoped>
.game-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 10px;
  background: var(--purple-light);
}

.bingo-letters {
  display: flex;
  gap: 3px;
}

.letter {
  width: 25px;
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 12px;
  color: white;
  border-radius: 3px;
}

.letter.b { background: #ff6b35; }
.letter.i { background: #2ecc71; }
.letter.n { background: #3498db; }
.letter.g { background: #e74c3c; }
.letter.o { background: #9b59b6; }

.status-text {
  font-weight: bold;
  font-size: 12px;
  color: var(--purple-dark);
}

.status-active {
  color: var(--green);
}
</style>

