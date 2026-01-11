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
  padding: 8px 12px;
  background: var(--primary-light);
  border-radius: 10px;
  margin: 5px;
  box-shadow: var(--card-shadow);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.bingo-letters {
  display: flex;
  gap: 3px;
}

.letter {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
  color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s ease;
}

.letter:hover {
  transform: scale(1.1);
}

.letter.b { background: linear-gradient(135deg, #ff6b6b 0%, #ff5252 100%); }
.letter.i { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
.letter.n { background: linear-gradient(135deg, #00b4d8 0%, #0077b6 100%); }
.letter.g { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); }
.letter.o { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); }

.status-text {
  font-weight: 600;
  font-size: 13px;
  color: var(--primary-dark);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-active {
  color: var(--success-green);
  font-weight: 700;
}
</style>

