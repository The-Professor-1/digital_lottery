<template>
  <div class="timer">
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
    }
  },
  computed: {
    formattedTime() {
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
</style>

