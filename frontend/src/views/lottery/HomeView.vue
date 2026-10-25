<template>
  <div :key="store.homeRefreshKey" class="space-y-4 pt-1">
    <HeroCard
      :raffle="store.raffle"
      @open="startBuy"
      @buy="startBuy"
    />
  </div>
</template>

<script setup>
import HeroCard from '../../components/lottery/HeroCard.vue'
import { store, openPicker } from '../../stores/lottery'

defineProps({ embedded: { type: Boolean, default: false } })

function startBuy() {
  store.selectedNumbers = []
  store.quantity = 1
  openPicker()
}
</script>
