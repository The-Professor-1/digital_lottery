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
      <p v-if="raffle.heroTitle" class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">
        {{ raffle.heroTitle }}
      </p>
      <div class="mt-4 w-full max-w-sm">
        <PrizeList
          :prizes="raffle.prizes || []"
          :prize1st="raffle.prize1st"
          :prize2nd="raffle.prize2nd"
          :prize3rd="raffle.prize3rd"
        />
      </div>
    </div>

    <div>
      <h1 class="text-2xl font-bold text-white">{{ raffle.name || raffle.displayName }}</h1>
      <p v-if="raffle.color" class="text-lime-400 mt-0.5">{{ raffle.color }}</p>
    </div>

    <CountdownTimer
      v-if="(raffle.drawMode || 'date') === 'date' && raffle.endsAt"
      :ends-at="raffle.endsAt"
      show-label
    />
    <div
      v-else
      class="rounded-2xl bg-gradient-to-b from-forest-dim to-forest-deep border border-forest/30 p-4 text-center"
    >
      <p class="text-gold text-xl font-extrabold">
        {{ raffle.displayName || raffle.name || store.brandName }}
      </p>
    </div>
    <TicketProgress
      :sold-count="raffle.soldCount"
      :total-tickets="raffle.totalTickets"
      :show-remaining="false"
    />

    <div class="flex items-center justify-between gap-3 py-1">
      <div>
        <p class="text-sm text-white/50">{{ landingText('ticketPrice', t.ticketPrice) }}</p>
        <p class="text-gold text-xl font-bold">{{ formatBirr(raffle.ticketPrice, t.birr) }}</p>
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
        {{ landingText('buyTicket', t.buyTicket) }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, Target, Shield } from 'lucide-vue-next'
import CountdownTimer from '../../components/lottery/CountdownTimer.vue'
import TicketProgress from '../../components/lottery/TicketProgress.vue'
import PrizeList from '../../components/lottery/PrizeList.vue'
import { useI18n } from '../../composables/useI18n'
import { formatBirr, padNumber } from '../../data/mock'
import {
  store,
  setQuantity,
  openPicker,
  openCheckoutFromSelect,
  loadPublicSettings,
  activateItemById,
  landingText,
} from '../../stores/lottery'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const raffle = computed(() => store.raffle)
const canBuy = computed(
  () =>
    store.selectedNumbers.length > 0 &&
    store.selectedNumbers.length === store.quantity
)

onMounted(async () => {
  const id = route.params?.id
  if (id) {
    await activateItemById(id)
  } else {
    await loadPublicSettings()
  }
})

</script>
