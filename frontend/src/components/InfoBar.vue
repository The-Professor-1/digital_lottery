<template>
  <div class="info-bar">
    <div class="info-item">
      <div class="label">ደራሽ</div>
      <div class="value">{{ derash }}</div>
    </div>
    <div class="info-item">
      <div class="label">የተጫዋች ብዛት</div>
      <div class="value">{{ players }}</div>
    </div>
    <div class="info-item">
      <div class="label">መደብ</div>
      <div class="value">{{ bet }}</div>
    </div>
    <div class="info-item">
      <div class="label">የተጠሩ ቁጥሮች</div>
      <div class="value">{{ call }}</div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'InfoBar',
  props: {
    derash: {
      type: [Number, String],
      default: 0
    },
    players: {
      type: [Number, String],
      default: 0
    },
    bet: {
      type: [Number, String],
      default: 0
    },
    call: {
      type: [Number, String],
      default: 0
    }
  }
}
</script>

<style scoped>
.info-bar {
  display: flex;
  background: var(--purple-light);
  padding: 5px;
  gap: 5px;
  border-bottom: 1px solid white;
}

.info-item {
  flex: 1;
  text-align: center;
  background: white;
  padding: 5px;
  border-radius: 4px;
}

.label {
  color: var(--purple-dark);
  font-size: 10px;
  font-weight: bold;
  margin-bottom: 2px;
}

.value {
  color: #333;
  font-size: 14px;
  font-weight: bold;
}
</style>

