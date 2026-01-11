<template>
  <div class="header">
    <div class="header-content">
      <button class="close-btn" @click="closeApp">Close</button>
      <div class="title">
        <h1>ጉድ ቢንጎ</h1>
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
  background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary-medium) 100%);
  color: white;
  padding: 12px 16px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--card-shadow);
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.close-btn {
  background: var(--accent-coral);
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 20px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.close-btn:hover {
  background: var(--accent-coral-dark);
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
}

.title h1 {
  font-size: 20px;
  margin: 0;
  text-align: center;
  font-weight: 700;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.title p {
  font-size: 12px;
  margin: 0;
  text-align: center;
  opacity: 0.8;
}

.menu-btn {
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  color: white;
  border: 2px solid rgba(255, 255, 255, 0.3);
  width: 38px;
  height: 38px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.menu-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}
</style>

