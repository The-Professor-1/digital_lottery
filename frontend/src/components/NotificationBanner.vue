<template>
  <transition name="banner-fade">
    <div v-if="message" class="notification-banner" :class="type">
      <div class="banner-content">
        <span class="banner-message">{{ message }}</span>
      </div>
    </div>
  </transition>
</template>

<script>
export default {
  name: 'NotificationBanner',
  props: {
    message: {
      type: String,
      default: null
    },
    type: {
      type: String,
      default: 'info', // 'info', 'success', 'error', 'warning'
      validator: (value) => ['info', 'success', 'error', 'warning'].includes(value)
    },
    duration: {
      type: Number,
      default: 3000 // 3 seconds
    }
  },
  watch: {
    message(newMessage) {
      if (newMessage) {
        // Auto-dismiss after duration
        setTimeout(() => {
          this.$emit('dismiss')
        }, this.duration)
      }
    }
  },
  mounted() {
    if (this.message) {
      setTimeout(() => {
        this.$emit('dismiss')
      }, this.duration)
    }
  }
}
</script>

<style scoped>
.notification-banner {
  position: fixed;
  top: 50px; /* Below top section (timer, wallet, bid) - adjust this value to change position */
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  min-width: 300px;
  max-width: 90%;
  background: white;
  border-radius: 12px;
  box-shadow: var(--card-shadow-lg);
  padding: 14px 24px;
  text-align: center;
  border: 2px solid transparent;
}

.notification-banner.error {
  border-left: 5px solid var(--accent-coral);
  background: linear-gradient(135deg, #fff5f5 0%, #ffe5e5 100%);
  border-color: rgba(255, 107, 107, 0.2);
}

.notification-banner.success {
  border-left: 5px solid var(--success-green);
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border-color: rgba(16, 185, 129, 0.2);
}

.notification-banner.warning {
  border-left: 5px solid #f59e0b;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: rgba(245, 158, 11, 0.2);
}

.notification-banner.info {
  border-left: 5px solid var(--primary-medium);
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: rgba(0, 180, 216, 0.2);
}

.banner-content {
  display: flex;
  align-items: center;
  justify-content: center;
}

.banner-message {
  font-size: 14px;
  font-weight: 500;
  color: #2c3e50;
  line-height: 1.4;
}

.banner-fade-enter-active,
.banner-fade-leave-active {
  transition: all 0.3s ease;
}

.banner-fade-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}

.banner-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}
</style>

