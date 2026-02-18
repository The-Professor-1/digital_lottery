<template>
  <div class="timer card-selection-timer">
    <div class="timer-display">{{ formattedTime }}</div>
  </div>
</template>

<script>
export default {
  name: 'CardSelectionTimer',
  props: {
    seconds: {
      type: Number,
      default: 0
    },
    totalSeconds: {
      type: Number,
      default: 20
    },
    gameCreatedAt: {
      type: [String, Date],
      default: null
    }
  },
  data() {
    return {
      remainingSeconds: 0,
      centiseconds: 0,
      tickInterval: null
    }
  },
  computed: {
    formattedTime() {
      const secs = Math.max(0, Math.floor(this.remainingSeconds))
      const cs = Math.min(99, Math.floor((this.remainingSeconds % 1) * 100))
      return `${String(secs).padStart(2, '0')}:${String(cs).padStart(2, '0')}`
    }
  },
  watch: {
    seconds: {
      immediate: true,
      handler(val) {
        if (!this.gameCreatedAt && val >= 0) {
          this.remainingSeconds = val
        }
      }
    },
    gameCreatedAt: {
      handler(val) {
        if (val) {
          this.updateRemaining()
        }
      }
    }
  },
  mounted() {
    this.updateRemaining()
    this.tickInterval = setInterval(() => {
      this.updateRemaining()
    }, 50) // Update every 50ms for fast-moving centiseconds (urgency)
  },
  beforeUnmount() {
    if (this.tickInterval) {
      clearInterval(this.tickInterval)
    }
  },
  methods: {
    updateRemaining() {
      if (this.gameCreatedAt && this.totalSeconds) {
        const start = new Date(this.gameCreatedAt).getTime()
        const elapsed = (Date.now() - start) / 1000
        this.remainingSeconds = Math.max(0, this.totalSeconds - elapsed)
      } else if (this.seconds >= 0) {
        this.remainingSeconds = this.seconds
      }
    }
  }
}
</script>

<style scoped>
.card-selection-timer .timer-display {
  font-size: 14px;
  font-weight: 700;
  color: var(--primary-dark);
  background: white;
  padding: 4px 10px;
  border-radius: 10px;
  display: inline-block;
  white-space: nowrap;
  box-shadow: var(--card-shadow);
  border: 2px solid var(--primary-medium);
}
</style>
