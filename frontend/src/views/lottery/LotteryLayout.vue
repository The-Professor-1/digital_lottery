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
import { onMounted } from 'vue'
import AppHeader from '../../components/lottery/AppHeader.vue'
import BottomNav from '../../components/lottery/BottomNav.vue'
import NumberPickerModal from '../../components/lottery/NumberPickerModal.vue'
import CheckoutModal from '../../components/lottery/CheckoutModal.vue'
import { store, loadPublicSettings } from '../../stores/lottery'

onMounted(() => {
  loadPublicSettings()
})
</script>

<style scoped>
.theme-light {
  background: #f3f4f6;
  color: #111;
}
</style>
