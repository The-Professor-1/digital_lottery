<template>
  <div class="app-shell" :class="store.theme === 'light' ? 'theme-light' : ''">
    <AppHeader />
    <main class="px-3 pb-28 min-h-[calc(100dvh-8rem)]">
      <RouterView />
    </main>
    <BottomNav />
    <NumberPickerModal />
    <CheckoutModal />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import AppHeader from '../../components/lottery/AppHeader.vue'
import BottomNav from '../../components/lottery/BottomNav.vue'
import NumberPickerModal from '../../components/lottery/NumberPickerModal.vue'
import CheckoutModal from '../../components/lottery/CheckoutModal.vue'
import { store, loadPublicSettings, loadUserProfile, loadTicketsForPhone } from '../../stores/lottery'

let pollTimer = null

onMounted(async () => {
  await loadPublicSettings()
  await loadUserProfile()
  if (store.phone) await loadTicketsForPhone(store.phone)

  // Poll so admin Start Draw / mode changes show up without a full refresh
  pollTimer = setInterval(() => {
    if (store.showPicker || store.showCheckout) return
    loadPublicSettings()
  }, 4000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.theme-light {
  background: #f3f4f6;
  color: #111;
}
</style>
