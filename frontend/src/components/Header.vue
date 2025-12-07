<template>
  <div class="header">
    <div class="header-content">
      <button class="close-btn" @click="closeApp">Close</button>
      <div class="title">
        <h1>ማርቆስ ቢንጎ</h1>
        <p>mini app</p>
      </div>
      <button class="menu-btn">⋮</button>
    </div>
  </div>
</template>

<script>
import { getTelegramWebApp } from '../services/telegram'

export default {
  name: 'Header',
  methods: {
    closeApp() {
      const tg = getTelegramWebApp()
      if (tg && tg.close) {
        tg.close()
      } else {
        window.close()
      }
    }
  }
}
</script>

<style scoped>
.header {
  background: #2c3e50;
  color: white;
  padding: 10px 15px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.close-btn {
  background: #2ecc71;
  color: white;
  border: none;
  padding: 8px 15px;
  border-radius: 5px;
  cursor: pointer;
  font-weight: bold;
}

.title h1 {
  font-size: 18px;
  margin: 0;
  text-align: center;
}

.title p {
  font-size: 12px;
  margin: 0;
  text-align: center;
  opacity: 0.8;
}

.menu-btn {
  background: #2ecc71;
  color: white;
  border: none;
  width: 35px;
  height: 35px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>

