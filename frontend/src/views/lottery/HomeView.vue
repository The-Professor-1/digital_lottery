<template>
  <div class="space-y-4 pt-1">
    <HeroCard
      :raffle="store.raffle"
      @open="goDetail"
      @buy="goDetail"
    />

    <div class="flex gap-2 overflow-x-auto no-scrollbar pb-1">
      <button
        v-for="f in filters"
        :key="f.id"
        type="button"
        class="shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-medium border transition-colors"
        :class="
          store.filter === f.id
            ? 'bg-gold text-black border-gold shadow-glow-sm'
            : 'bg-ink-200 text-white/75 border-white/10'
        "
        @click="store.filter = f.id"
      >
        <span>{{ f.emoji }}</span>
        <span>{{ f.label }}</span>
      </button>
    </div>

    <div class="flex items-center justify-between pt-1">
      <h3 class="text-sm font-semibold text-white/90">{{ t.ongoingRaffles }}</h3>
      <span class="text-xs text-white/45">0 {{ t.available }}</span>
    </div>

    <div class="flex flex-col items-center text-center py-10 px-4">
      <div
        class="w-14 h-14 rounded-2xl bg-ink-200 border border-white/10 flex items-center justify-center mb-3"
      >
        <Ticket :size="26" class="text-white/35" />
      </div>
      <p class="text-white/80 font-medium">{{ t.noOtherLotteries }}</p>
      <p class="text-xs text-white/40 mt-1.5 max-w-[260px]">{{ t.noOtherLotteriesHint }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Ticket } from 'lucide-vue-next'
import HeroCard from '../../components/lottery/HeroCard.vue'
import { useI18n } from '../../composables/useI18n'
import { store } from '../../stores/lottery'

const router = useRouter()
const { t } = useI18n()

const filters = computed(() => [
  { id: 'all', emoji: '✨', label: t.value.all },
  { id: 'popular', emoji: '🔥', label: t.value.popular },
  { id: 'new', emoji: '📈', label: t.value.newest },
])

function goDetail() {
  router.push(`/raffle/${store.raffle.id}`)
}
</script>
