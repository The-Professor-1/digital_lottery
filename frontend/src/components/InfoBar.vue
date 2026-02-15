<template>
  <div class="info-bar">
    <div class="info-item">
      <div class="label">ደራሽ</div>
      <div class="value">{{ derash }}</div>
    </div>
    <div class="info-item">
      <div class="label">ተጫዋች</div>
      <div class="value">{{ players }}</div>
    </div>
    <div class="info-item">
      <div class="label">መደብ</div>
      <div class="value">{{ bet }}</div>
    </div>
    <div class="info-item">
      <div class="label">የተጠሩ</div>
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
  background: var(--primary-light);
  padding: 8px;
  gap: 8px;
  border-radius: 10px;
  margin: 5px;
  box-shadow: var(--card-shadow);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.info-item {
  flex: 1;
  text-align: center;
  background: white;
  padding: 8px 6px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s ease;
}

.info-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}

.label {
  color: var(--primary-dark);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.value {
  color: var(--gray-dark);
  font-size: 18px;
  font-weight: 700;
}
</style>

