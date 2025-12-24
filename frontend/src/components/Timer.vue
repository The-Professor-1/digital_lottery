<template>
  <div :class="['timer', { 'large': large }]">
    <div class="timer-display">{{ formattedTime }}</div>
  </div>
</template>

<script>
export default {
  name: 'Timer',
  props: {
    seconds: {
      type: Number,
      default: 0
    },
    large: {
      type: Boolean,
      default: false
    }
  },
  computed: {
    formattedTime() {
      // For large timer with less than 60 seconds, show just the number
      if (this.large && this.seconds < 60) {
        return String(this.seconds)
      }
      // Otherwise show MM:SS format
      const mins = Math.floor(this.seconds / 60)
      const secs = this.seconds % 60
      return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    }
  }
}
</script>

<style scoped>
.timer {
  display: inline-block;
  padding: 0;
  margin: 0;
  line-height: 1;
}

.timer-display {
  font-size: 14px;
  font-weight: bold;
  color: var(--purple-dark);
  background: white;
  padding: 3px 8px;
  border-radius: 4px;
  display: inline-block;
  white-space: nowrap;
}

/* Large timer style for next game countdown */
.timer.large {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
}

.timer.large .timer-display {
  font-size: 120px;
  font-weight: bold;
  color: var(--purple-dark);
  background: white;
  padding: 30px 60px;
  border-radius: 20px;
  display: inline-block;
  white-space: nowrap;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  min-width: 200px;
  text-align: center;
}
</style>

