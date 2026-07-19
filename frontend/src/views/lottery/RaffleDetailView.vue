<template>
  <div class="space-y-4 pt-1 pb-4">
    <button
      type="button"
      class="inline-flex items-center gap-1 text-sm text-white/60 -mt-1"
      @click="router.back()"
    >
      <ChevronLeft :size="18" /> {{ t.back }}
    </button>

    <div
      class="relative rounded-card overflow-hidden min-h-[180px] px-5 py-7 flex flex-col items-center justify-center text-center bg-gradient-to-br from-ink-200 via-forest-deep to-ink-100 border border-forest/20"
    >
      <p class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">
        {{ raffle.heroTitle || 'markos digital lottery' }}
      </p>
      <h1 class="mt-3 text-white text-3xl font-extrabold leading-tight tracking-tight">
        1ኛ እጣ {{ formatAmount(raffle.prize1st) }} ብር
      </h1>
      <h2 class="mt-3 text-lime-300/95 text-xl font-bold leading-snug">
        2ኛ እጣ {{ formatAmount(raffle.prize2nd) }} ብር
      </h2>
      <h3 class="mt-2 text-white/80 text-base font-semibold leading-snug">
        3ኛ እጣ {{ formatAmount(raffle.prize3rd) }} ብር
      </h3>
    </div>

    <div>
      <h1 class="text-2xl font-bold text-white">{{ raffle.displayName || raffle.name }}</h1>
      <p v-if="raffle.color" class="text-lime-400 mt-0.5">{{ raffle.color }}</p>
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

    <div v-if="store.selectedNumbers.length" class="space-y-2">
      <p class="text-sm text-white/70">{{ t.selectedNumbersLabel }}</p>
      <div class="flex flex-wrap gap-1.5">
        <span
          v-for="n in store.selectedNumbers"
          :key="n"
          class="inline-block bg-gold text-black text-sm font-bold px-3 py-1.5 rounded-lg"
        >
          {{ padNumber(n) }}
        </span>
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

    <div class="pt-2">
      <button
        type="button"
        class="w-full py-3.5 rounded-2xl text-sm font-semibold inline-flex items-center justify-center gap-1.5 transition-colors"
        :disabled="!canBuy"
        :class="
          canBuy
            ? 'btn-green'
            : 'bg-forest/45 text-white/85 border border-forest/50 cursor-not-allowed shadow-none'
        "
        @click="openCheckoutFromSelect"
      >
        <Shield :size="16" />
        {{ t.buyTicket }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, Target, Shield } from 'lucide-vue-next'
import CountdownTimer from '../../components/lottery/CountdownTimer.vue'
import TicketProgress from '../../components/lottery/TicketProgress.vue'
import { useI18n } from '../../composables/useI18n'
import { formatBirr, padNumber } from '../../data/mock'
import {
  store,
  setQuantity,
  openPicker,
  openCheckoutFromSelect,
  loadPublicSettings,
} from '../../stores/lottery'

const router = useRouter()
const { t } = useI18n()
const raffle = computed(() => store.raffle)
const canBuy = computed(
  () =>
    store.selectedNumbers.length > 0 &&
    store.selectedNumbers.length === store.quantity
)

onMounted(() => {
  loadPublicSettings()
})

function formatAmount(n) {
  return Number(n || 0).toLocaleString('en-US')
}
</script>
