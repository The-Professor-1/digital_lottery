<template>
  <div class="space-y-4 pt-1 pb-4">
    <button
      type="button"
      class="inline-flex items-center gap-1 text-sm text-white/60 -mt-1"
      @click="router.back()"
    >
      <ChevronLeft :size="18" /> Back
    </button>

    <div class="relative rounded-card overflow-hidden aspect-[16/11] bg-zinc-300">
      <img
        :src="raffle.image"
        :alt="raffle.name"
        class="w-full h-full object-cover"
      />
      <span
        class="absolute bottom-3 left-3 inline-flex rounded-full bg-forest text-white text-[11px] font-bold px-2.5 py-1"
      >
        {{ t.newBadge }}
      </span>
      <div
        class="absolute bottom-3 right-3 flex items-center gap-1 bg-black/50 rounded-full px-2 py-1"
      >
        <Star v-for="n in 5" :key="n" :size="12" class="text-gold fill-gold" />
        <span class="text-xs text-white ml-0.5">{{ raffle.rating.toFixed(1) }}</span>
      </div>
    </div>

    <div>
      <h1 class="text-2xl font-bold text-white">{{ raffle.name }}</h1>
      <p class="text-lime-400 mt-0.5">{{ raffle.color }}</p>
    </div>

    <CountdownTimer :ends-at="raffle.endsAt" show-label />
    <TicketProgress
      :sold-count="raffle.soldCount"
      :total-tickets="raffle.totalTickets"
      :show-remaining="false"
    />

    <div class="flex items-center justify-between gap-3 py-1">
      <div>
        <p class="text-sm text-white/50">{{ t.ticketPrice }}</p>
        <p class="text-gold text-xl font-bold">{{ formatBirr(raffle.ticketPrice) }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="w-10 h-10 rounded-xl bg-ink-300 text-white text-xl font-bold"
          @click="setQuantity(store.quantity - 1)"
        >
          −
        </button>
        <span class="w-8 text-center font-bold text-lg tabular-nums">{{ store.quantity }}</span>
        <button
          type="button"
          class="w-10 h-10 rounded-xl bg-gold text-black text-xl font-bold shadow-glow-sm"
          @click="setQuantity(store.quantity + 1)"
        >
          +
        </button>
      </div>
    </div>

    <button
      type="button"
      class="btn-gold-outline w-full py-3.5 text-sm inline-flex items-center justify-center gap-2"
      @click="openPicker"
    >
      <Target :size="18" />
      {{ t.chooseNumbers }}
    </button>

    <div class="flex gap-2 sticky bottom-24 pt-2">
      <button
        type="button"
        class="btn-gold flex-1 py-3.5 text-sm inline-flex items-center justify-center gap-1.5"
        @click="onQuickPick"
      >
        <Zap :size="16" />
        {{ t.quickPick }}
      </button>
      <button
        type="button"
        class="flex-1 py-3.5 rounded-2xl border border-white/20 text-white/50 text-sm font-semibold inline-flex items-center justify-center gap-1.5 disabled:opacity-40"
        :disabled="!canSelect"
        :class="canSelect ? 'btn-green !border-transparent' : ''"
        @click="openCheckoutFromSelect"
      >
        <Shield :size="16" />
        {{ t.select }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, Star, Target, Zap, Shield } from 'lucide-vue-next'
import CountdownTimer from '../../components/lottery/CountdownTimer.vue'
import TicketProgress from '../../components/lottery/TicketProgress.vue'
import { useI18n } from '../../composables/useI18n'
import { formatBirr } from '../../data/mock'
import {
  store,
  setQuantity,
  openPicker,
  quickPick,
  openCheckoutFromSelect,
  loadPublicSettings,
} from '../../stores/lottery'

const router = useRouter()
const { t } = useI18n()
const raffle = computed(() => store.raffle)
const canSelect = computed(() => store.selectedNumbers.length === store.quantity)

onMounted(() => {
  loadPublicSettings()
})

function onQuickPick() {
  quickPick()
  openCheckoutFromSelect()
}
</script>
