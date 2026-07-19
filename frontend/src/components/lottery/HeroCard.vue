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
            {{ raffle.heroTitle || store.brandName }}
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
        <!-- Same slot: date countdown OR display name from admin -->
        <CountdownTimer
          v-if="showCountdown"
          :ends-at="raffle.endsAt"
        />
        <div
          v-else
          class="rounded-2xl bg-gradient-to-b from-forest-dim to-forest-deep border border-forest/30 p-4 text-center"
        >
          <h2 class="text-gold text-xl sm:text-2xl font-extrabold leading-snug tracking-tight">
            {{ raffle.displayName || raffle.name || store.brandName }}
          </h2>
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
import { store } from '../../stores/lottery'

const props = defineProps({
  raffle: { type: Object, required: true },
})
defineEmits(['open', 'buy'])

const { t } = useI18n()
const { remainingMs, inFinalMinute, isFinished } = useCountdown(() => props.raffle.endsAt)

const autoAnnounce = computed(() => props.raffle.automaticAnnouncement !== false)
const drawMode = computed(() => props.raffle.drawMode || 'date')
const isDateMode = computed(() => drawMode.value === 'date')

/** Only date-deadline mode shows D:H:M:S. Other modes show display name. */
const showCountdown = computed(
  () => isDateMode.value && !!props.raffle.endsAt && !props.raffle.drawCompleted
)

const adminDrawLive = computed(() => {
  if (isDateMode.value) return false
  const ends = props.raffle.endsAt || 0
  if (!ends) return false
  // Counting down after Start Draw
  if (remainingMs.value > 0) return true
  // Just finished — keep announce UI briefly (ignore stale old deadlines)
  if (isFinished.value && ends > Date.now() - 10 * 60 * 1000) return true
  return false
})

const showDrawUi = computed(() => {
  if (props.raffle.drawCompleted) return true
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
