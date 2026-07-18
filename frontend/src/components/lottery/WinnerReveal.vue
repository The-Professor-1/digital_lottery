<template>
  <div class="rounded-card overflow-hidden border border-gold/30 bg-gradient-to-b from-ink-200 via-forest-deep to-ink-100">
    <!-- Final 60s big countdown -->
    <div v-if="phase === 'countdown'" class="px-4 py-10 text-center space-y-3">
      <p class="text-gold text-xs font-semibold tracking-[0.2em] uppercase">{{ t.drawStarting }}</p>
      <div
        class="text-gold font-extrabold tabular-nums leading-none transition-transform"
        :class="pulse ? 'scale-110' : 'scale-100'"
        style="font-size: clamp(4.5rem, 22vw, 7rem)"
      >
        {{ displaySeconds }}
      </div>
      <p class="text-white/60 text-sm">{{ t.secondsLeft }}</p>
    </div>

    <!-- Ball shuffle -->
    <div v-else-if="phase === 'shuffle'" class="px-3 py-6 space-y-4">
      <p class="text-center text-gold text-sm font-semibold">{{ t.shufflingBalls }}</p>
      <div class="flex flex-wrap justify-center gap-1.5 max-h-48 overflow-hidden">
        <span
          v-for="(ball, i) in visibleBalls"
          :key="i + '-' + ball"
          class="ball"
          :style="{ background: ballColor(ball) }"
        >
          {{ padNumber(ball) }}
        </span>
      </div>
    </div>

    <!-- Reveal prizes one by one -->
    <div v-else-if="phase === 'reveal'" class="px-4 py-8 text-center space-y-5">
      <p class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">{{ revealLabel }}</p>
      <div
        class="mx-auto w-28 h-28 rounded-full flex items-center justify-center text-3xl font-extrabold text-white shadow-lg border-4 border-white/20"
        :style="{ background: ballColor(revealNumber) }"
      >
        {{ padNumber(revealNumber) }}
      </div>
      <p class="text-white/80 text-lg font-semibold">{{ revealPrizeText }}</p>
    </div>

    <!-- Final board -->
    <div v-else-if="phase === 'done'" class="px-4 py-6 space-y-4">
      <p class="text-center text-gold text-sm font-bold tracking-wide uppercase">{{ t.winnersAnnounced }}</p>
      <div
        v-for="row in finalRows"
        :key="row.place"
        class="flex items-center gap-3 rounded-2xl bg-black/30 border border-white/10 p-3"
      >
        <div
          class="w-14 h-14 rounded-full flex items-center justify-center text-lg font-extrabold text-white shrink-0"
          :style="{ background: ballColor(row.number) }"
        >
          {{ padNumber(row.number) }}
        </div>
        <div class="min-w-0 text-left">
          <p class="text-white font-bold">{{ row.label }}</p>
          <p class="text-lime-300/90 text-sm">{{ formatAmount(row.prize) }} ብር</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useCountdown } from '../../composables/useCountdown'
import { useI18n } from '../../composables/useI18n'
import { padNumber } from '../../data/mock'
import { runLotteryDraw } from '../../services/api'
import { store, loadPublicSettings } from '../../stores/lottery'

const props = defineProps({
  endsAt: { type: Number, required: true },
})

const { t } = useI18n()
const { remainingSeconds, inFinalMinute, isFinished } = useCountdown(() => props.endsAt)

const phase = ref('idle') // idle | countdown | shuffle | reveal | done
const pulse = ref(false)
const visibleBalls = ref([])
const revealLabel = ref('')
const revealNumber = ref(0)
const revealPrizeText = ref('')
const drawResult = ref(null)
let shuffleTimer = null
let revealTimers = []
let started = false

const displaySeconds = computed(() => Math.max(0, remainingSeconds.value))

const finalRows = computed(() => {
  const r = drawResult.value || {}
  return [
    { place: 1, label: '1ኛ እጣ', number: r.winner_1st, prize: r.prize_1st },
    { place: 2, label: '2ኛ እጣ', number: r.winner_2nd, prize: r.prize_2nd },
    { place: 3, label: '3ኛ እጣ', number: r.winner_3rd, prize: r.prize_3rd },
  ].filter((x) => x.number)
})

function formatAmount(n) {
  return Number(n || 0).toLocaleString('en-US')
}

function ballColor(n) {
  const colors = [
    '#e11d48', '#2563eb', '#16a34a', '#ca8a04', '#9333ea',
    '#ea580c', '#0891b2', '#4f46e5', '#be123c', '#0f766e',
  ]
  return colors[Number(n) % colors.length]
}

function startCountdownUi() {
  if (phase.value === 'idle' || phase.value === 'countdown') {
    phase.value = 'countdown'
  }
}

async function runDrawSequence() {
  if (started) return
  started = true
  phase.value = 'shuffle'

  const total = store.raffle.totalTickets || 100
  const balls = Array.from({ length: Math.min(total, 80) }, (_, i) => i + 1)
  let ticks = 0
  shuffleTimer = setInterval(() => {
    ticks += 1
    for (let i = balls.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[balls[i], balls[j]] = [balls[j], balls[i]]
    }
    visibleBalls.value = balls.slice(0, 24)
    if (ticks > 18) {
      clearInterval(shuffleTimer)
      shuffleTimer = null
      fetchAndReveal()
    }
  }, 120)
}

async function fetchAndReveal() {
  try {
    const res = await runLotteryDraw()
    drawResult.value = res
    store.raffle = {
      ...store.raffle,
      winner1st: res.winner_1st,
      winner2nd: res.winner_2nd,
      winner3rd: res.winner_3rd,
      drawCompleted: true,
    }
  } catch (e) {
    // If too early, retry shortly; if already drawn, use settings
    const data = e.response?.data
    if (data?.winner_1st) {
      drawResult.value = data
    } else {
      await loadPublicSettings()
      if (store.raffle.drawCompleted || store.raffle.winner1st) {
        drawResult.value = {
          winner_1st: store.raffle.winner1st,
          winner_2nd: store.raffle.winner2nd,
          winner_3rd: store.raffle.winner3rd,
          prize_1st: store.raffle.prize1st,
          prize_2nd: store.raffle.prize2nd,
          prize_3rd: store.raffle.prize3rd,
        }
      } else {
        setTimeout(() => {
          started = false
          runDrawSequence()
        }, 2000)
        return
      }
    }
  }

  const rows = [
    { label: '1ኛ እጣ', number: drawResult.value.winner_1st, prize: drawResult.value.prize_1st },
    { label: '2ኛ እጣ', number: drawResult.value.winner_2nd, prize: drawResult.value.prize_2nd },
    { label: '3ኛ እጣ', number: drawResult.value.winner_3rd, prize: drawResult.value.prize_3rd },
  ]

  phase.value = 'reveal'
  let i = 0
  const showNext = () => {
    if (i >= rows.length) {
      phase.value = 'done'
      loadPublicSettings()
      return
    }
    const row = rows[i]
    revealLabel.value = row.label
    revealNumber.value = row.number
    revealPrizeText.value = `${formatAmount(row.prize)} ብር`
    i += 1
    revealTimers.push(setTimeout(showNext, 2800))
  }
  showNext()
}

watch(
  [inFinalMinute, isFinished, remainingSeconds],
  ([finalMin, finished, secs]) => {
    pulse.value = secs % 2 === 0
    if (store.raffle.drawCompleted && store.raffle.winner1st) {
      drawResult.value = {
        winner_1st: store.raffle.winner1st,
        winner_2nd: store.raffle.winner2nd,
        winner_3rd: store.raffle.winner3rd,
        prize_1st: store.raffle.prize1st,
        prize_2nd: store.raffle.prize2nd,
        prize_3rd: store.raffle.prize3rd,
      }
      phase.value = 'done'
      return
    }
    if (finished && !started) {
      runDrawSequence()
    } else if (finalMin) {
      startCountdownUi()
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (store.raffle.drawCompleted && store.raffle.winner1st) {
    drawResult.value = {
      winner_1st: store.raffle.winner1st,
      winner_2nd: store.raffle.winner2nd,
      winner_3rd: store.raffle.winner3rd,
      prize_1st: store.raffle.prize1st,
      prize_2nd: store.raffle.prize2nd,
      prize_3rd: store.raffle.prize3rd,
    }
    phase.value = 'done'
  }
})

onUnmounted(() => {
  if (shuffleTimer) clearInterval(shuffleTimer)
  revealTimers.forEach(clearTimeout)
})

defineExpose({ phase })
</script>

<style scoped>
.ball {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 9999px;
  color: #fff;
  font-size: 0.65rem;
  font-weight: 800;
  box-shadow: inset 0 -2px 4px rgba(0, 0, 0, 0.35), 0 2px 4px rgba(0, 0, 0, 0.25);
  animation: bounce 0.35s ease-in-out infinite alternate;
}
@keyframes bounce {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(-4px);
  }
}
</style>
