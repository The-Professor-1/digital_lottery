<template>
  <article
    class="rounded-card overflow-hidden bg-gradient-to-b from-forest-dim via-forest-deep to-ink-100 border border-forest/20"
  >
    <!-- Draw / final minute takeover -->
    <WinnerReveal v-if="showDrawUi" :ends-at="raffle.endsAt || 0" />

    <template v-else>
      <button type="button" class="block w-full text-left" @click="$emit('open')">
        <div
          class="relative min-h-[200px] px-5 py-8 flex flex-col items-center justify-center text-center bg-gradient-to-br from-ink-200 via-forest-deep to-ink-100"
        >
          <div
            class="absolute inset-0 opacity-30 pointer-events-none"
            style="background: radial-gradient(ellipse at 50% 0%, rgba(212,175,55,0.35), transparent 55%)"
          />
          <p class="relative text-gold text-xs font-semibold tracking-[0.18em] uppercase">
            {{ raffle.heroTitle || 'markos digital lottery' }}
          </p>
          <h1 class="relative mt-4 text-white text-3xl sm:text-4xl font-extrabold leading-tight tracking-tight">
            1ኛ እጣ {{ formatAmount(raffle.prize1st) }} ብር
          </h1>
          <h2 class="relative mt-3 text-lime-300/95 text-xl sm:text-2xl font-bold leading-snug">
            2ኛ እጣ {{ formatAmount(raffle.prize2nd) }} ብር
          </h2>
          <h3 class="relative mt-2 text-white/80 text-base sm:text-lg font-semibold leading-snug">
            3ኛ እጣ {{ formatAmount(raffle.prize3rd) }} ብር
          </h3>
        </div>
      </button>

      <div class="px-4 pb-4 space-y-3 pt-3">
        <!-- Date mode: countdown. Other modes: display name only until admin starts draw -->
        <CountdownTimer v-if="showCountdown" :ends-at="raffle.endsAt" />
        <div
          v-else
          class="rounded-2xl border border-white/10 bg-black/25 px-4 py-5 text-center"
        >
          <h2 class="text-white text-xl font-bold leading-tight">
            {{ raffle.displayName || raffle.name }}
          </h2>
          <p v-if="raffle.color" class="text-lime-400/90 text-sm mt-1">{{ raffle.color }}</p>
        </div>

        <TicketProgress :sold-count="raffle.soldCount" :total-tickets="raffle.totalTickets" />

        <div class="flex items-center gap-3 pt-1">
          <div class="flex items-center gap-1.5 text-white/70 text-sm">
            <Users :size="16" />
            <span>{{ raffle.participants }}</span>
          </div>
          <button type="button" class="btn-gold flex-1 py-3 text-sm" @click="$emit('buy')">
            {{ t.buyTicket }}
          </button>
        </div>
      </div>
    </template>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { Users } from 'lucide-vue-next'
import CountdownTimer from './CountdownTimer.vue'
import TicketProgress from './TicketProgress.vue'
import WinnerReveal from './WinnerReveal.vue'
import { useCountdown } from '../../composables/useCountdown'
import { useI18n } from '../../composables/useI18n'

const props = defineProps({
  raffle: { type: Object, required: true },
})
defineEmits(['open', 'buy'])

const { t } = useI18n()
const { remainingMs, inFinalMinute, isFinished } = useCountdown(() => props.raffle.endsAt)

const autoAnnounce = computed(() => props.raffle.automaticAnnouncement !== false)
const drawMode = computed(() => props.raffle.drawMode || 'date')
const isDateMode = computed(() => drawMode.value === 'date')

const showCountdown = computed(
  () => isDateMode.value && !!props.raffle.endsAt && !props.raffle.drawCompleted
)

/** Admin-started draw (sold_out / manual): show big timer for the whole ends_at window */
const adminDrawLive = computed(() => {
  if (isDateMode.value) return false
  if (!props.raffle.endsAt) return false
  return remainingMs.value > 0 || isFinished.value
})

const showDrawUi = computed(() => {
  if (props.raffle.drawCompleted) return true
  // Sold-out / admin mode: show big timer for the whole Start Draw window
  if (!isDateMode.value) {
    return adminDrawLive.value
  }
  if (!autoAnnounce.value) {
    return isFinished.value
  }
  return inFinalMinute.value || isFinished.value
})

function formatAmount(n) {
  return Number(n || 0).toLocaleString('en-US')
}
</script>
