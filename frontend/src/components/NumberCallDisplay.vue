<template>
  <div class="number-call-display">
    <div class="current-call" v-if="currentCall">
      <div class="call-number">
        <span class="letter" :class="`letter-${currentCall.letter.toLowerCase()}`">
          {{ currentCall.letter }}
        </span>
        <span class="number">-{{ currentCall.number }}</span>
      </div>
    </div>
    <div class="recent-calls" v-if="recentCalls.length > 0">
      <div
        v-for="(call, idx) in getUniqueRecentCalls"
        :key="`${call.letter}-${call.number}-${idx}`"
        class="recent-call"
        :class="`call-${call.letter.toLowerCase()}`"
      >
        {{ call.letter }}{{ call.number }}
      </div>
    </div>
    <div v-else class="no-calls">
      <p>...</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NumberCallDisplay',
  props: {
    currentCall: {
      type: Object,
      default: null
    },
    recentCalls: {
      type: Array,
      default: () => []
    }
  },
  computed: {
    getUniqueRecentCalls() {
      // Get unique recent calls (last 3, no duplicates)
      const unique = []
      const seen = new Set()
      for (let i = this.recentCalls.length - 1; i >= 0 && unique.length < 3; i--) {
        const call = this.recentCalls[i]
        const key = `${call.letter}-${call.number}`
        if (!seen.has(key)) {
          seen.add(key)
          unique.unshift(call) // Add to beginning to maintain order
        }
      }
      return unique
    }
  }
}
</script>

<style scoped>
.number-call-display {
  background: var(--purple-medium);
  padding: 8px;
  border-radius: 10px;
  margin: 5px;
  text-align: center;
  width: 100%;
  box-sizing: border-box;
}

.number-call-display.compact-call-display {
  width: 100%;
  max-width: 100%;
  padding: 5px;
  margin: 0 0 5px 0;
}

.current-call {
  margin-bottom: 8px;
}

.call-number {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: white;
  padding: 8px 12px;
  border-radius: 8px;
}

.letter {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: white;
  font-weight: bold;
  font-size: 25px;
}

.letter-b { background: #ff6b35; }
.letter-i { background: #2ecc71; }
.letter-n { background: #3498db; }
.letter-g { background: #e74c3c; }
.letter-o { background: #9b59b6; }

.number {
  font-size: 25px;
  font-weight: bold;
  color: var(--purple-dark);
}

.no-calls {
  color: white;
  font-size: 14px;
  padding: 10px;
}

.recent-calls {
  display: flex;
  gap: 6px;
  justify-content: center;
}

.recent-call {
  width: 25px;
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: white;
  font-weight: bold;
  font-size:12px;
}

.call-b { background: #ff6b35; }
.call-i { background: #2ecc71; }
.call-n { background: #3498db; }
.call-g { background: #e74c3c; }
.call-o { background: #9b59b6; }
</style>

