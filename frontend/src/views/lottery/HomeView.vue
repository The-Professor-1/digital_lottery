<template>
  <div :key="store.homeRefreshKey" class="space-y-4 pt-1">
    <HeroCard
      :raffle="store.raffle"
      @open="goDetail"
      @buy="goDetail"
    />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import HeroCard from '../../components/lottery/HeroCard.vue'
import { store } from '../../stores/lottery'

const router = useRouter()

function goDetail() {
  router.push(`/raffle/${store.raffle.id}`)
}
</script>
