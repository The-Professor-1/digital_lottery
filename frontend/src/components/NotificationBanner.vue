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
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 12px 20px;
  text-align: center;
}

.notification-banner.error {
  border-left: 4px solid #e74c3c;
  background: #fee;
}

.notification-banner.success {
  border-left: 4px solid #2ecc71;
  background: #efe;
}

.notification-banner.warning {
  border-left: 4px solid #f39c12;
  background: #fff9e6;
}

.notification-banner.info {
  border-left: 4px solid #3498db;
  background: #eef;
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

