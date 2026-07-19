<template>
  <div class="rounded-card overflow-hidden border border-gold/30 bg-gradient-to-b from-ink-200 via-forest-deep to-ink-100">
    <!-- Manual announcement (auto toggle off) -->
    <div v-if="phase === 'manual'" class="px-4 py-8 text-center space-y-3">
      <p class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">{{ t.manualAnnounceTitle }}</p>
      <p class="text-white text-base font-semibold leading-snug">{{ t.manualAnnounceBody }}</p>
      <p class="text-white/55 text-sm leading-relaxed">{{ t.manualAnnounceHint }}</p>
    </div>

    <!-- Stuck: timer ended with no verified tickets -->
    <div v-else-if="phase === 'stuck'" class="px-4 py-8 text-center space-y-3">
      <p class="text-gold text-sm font-semibold tracking-wide uppercase">{{ t.drawStarting }}</p>
      <p class="text-white text-base font-semibold">{{ t.noTicketsToDraw }}</p>
      <p class="text-white/50 text-xs leading-relaxed">{{ t.waitingAdminRestart }}</p>
    </div>

    <!-- Final minute: timer on top + shuffle on bottom -->
    <template v-else-if="phase === 'final' || phase === 'drawing'">
      <div class="px-4 pt-8 pb-4 text-center space-y-2 border-b border-white/5">
        <p class="text-gold text-xs font-semibold tracking-[0.2em] uppercase">{{ t.drawStarting }}</p>
        <div
          class="text-gold font-extrabold tabular-nums leading-none transition-transform"
          :class="pulse ? 'scale-110' : 'scale-100'"
          style="font-size: clamp(3.5rem, 18vw, 6rem)"
        >
          {{ displaySeconds }}
        </div>
        <p class="text-white/60 text-sm">{{ t.secondsLeft }}</p>
      </div>
      <div class="px-3 py-5 space-y-3">
        <p class="text-center text-gold text-sm font-semibold">{{ t.shufflingBalls }}</p>
        <div class="flex flex-wrap justify-center gap-1.5 max-h-40 overflow-hidden min-h-[5rem]">
          <span
            v-for="(ball, i) in visibleBalls"
            :key="i + '-' + ball"
            class="ball"
            :style="{ background: ballColor(ball) }"
          >
            {{ padNumber(ball) }}
          </span>
        </div>
        <p v-if="!takenPool.length" class="text-center text-xs text-white/40">
          {{ t.waitingTickets }}
        </p>
      </div>
    </template>

    <!-- Ordered reveal: show current big ball + already revealed list growing -->
    <div v-else-if="phase === 'reveal'" class="px-4 py-6 space-y-5">
      <p class="text-center text-gold text-xs font-semibold tracking-[0.18em] uppercase">
        {{ revealLabel }}
      </p>
      <div
        class="mx-auto w-28 h-28 rounded-full flex items-center justify-center text-3xl font-extrabold text-white shadow-lg border-4 border-white/20"
        :style="{ background: ballColor(revealNumber) }"
      >
        {{ padNumber(revealNumber) }}
      </div>
      <p class="text-center text-white/80 text-lg font-semibold">{{ revealPrizeText }}</p>

      <div v-if="revealedRows.length" class="space-y-2 pt-2 border-t border-white/10">
        <div
          v-for="row in revealedRows"
          :key="'r' + row.place"
          class="flex items-center gap-3 rounded-xl bg-black/25 border border-white/10 px-3 py-2 opacity-80"
        >
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-extrabold text-white"
            :style="{ background: ballColor(row.number) }"
          >
            {{ padNumber(row.number) }}
          </div>
          <div>
            <p class="text-white text-sm font-bold">{{ row.label }}</p>
            <p class="text-lime-300/80 text-xs">{{ formatAmount(row.prize) }} ብር</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Winners + next round timer -->
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

      <div class="mt-2 rounded-2xl border border-gold/40 bg-black/35 px-4 py-4 text-center space-y-2">
        <template v-if="adminControlsRound">
          <p class="text-white/70 text-xs uppercase tracking-wide">{{ t.waitingAdminNextRound }}</p>
          <p class="text-white/55 text-sm leading-relaxed">{{ t.waitingAdminNextRoundHint }}</p>
        </template>
        <template v-else>
          <p class="text-white/70 text-xs uppercase tracking-wide">{{ t.nextRoundIn }}</p>
          <div class="text-gold text-3xl font-extrabold tabular-nums">
            {{ nextRoundLabel }}
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useCountdown } from '../../composables/useCountdown'
import { useI18n } from '../../composables/useI18n'
import { padNumber } from '../../data/mock'
import { runLotteryDraw, notifyLotteryWinners, startLotteryNextRound } from '../../services/api'
import { store, applyPublicSettings, loadPublicSettings } from '../../stores/lottery'

const props = defineProps({
  endsAt: { type: Number, required: true },
})

const { t } = useI18n()
const { remainingSeconds, inFinalMinute, isFinished } = useCountdown(() => props.endsAt)

const phase = ref('idle') // idle | final | drawing | reveal | done | stuck | manual

const autoAnnounce = computed(() => store.raffle.automaticAnnouncement !== false)
const adminControlsRound = computed(() => (store.raffle.drawMode || 'date') !== 'date')
const pulse = ref(false)
const visibleBalls = ref([])
const revealLabel = ref('')
const revealNumber = ref(0)
const revealPrizeText = ref('')
const revealedRows = ref([])
const drawResult = ref(null)
const nextRoundEndsAt = ref(0)
const nextRoundLeft = ref(0)
let shuffleTimer = null
let revealTimers = []
let nextRoundTimer = null
let recoverTimer = null
let drawStarted = false
let resetStarted = false
let notifyStarted = false

const displaySeconds = computed(() => Math.max(0, remainingSeconds.value))

const takenPool = computed(() => {
  const fromStore = [...(store.verifiedTakenNumbers || [])].map(Number).filter((n) => n > 0)
  const fromDraw = (drawResult.value?.taken_numbers || []).map(Number)
  const pool = fromDraw.length ? fromDraw : fromStore
  return [...new Set(pool)].sort((a, b) => a - b)
})

const finalRows = computed(() => {
  const r = drawResult.value || {}
  return [
    { place: 1, label: '1ኛ እጣ', number: r.winner_1st, prize: r.prize_1st },
    { place: 2, label: '2ኛ እጣ', number: r.winner_2nd, prize: r.prize_2nd },
    { place: 3, label: '3ኛ እጣ', number: r.winner_3rd, prize: r.prize_3rd },
  ].filter((x) => x.number)
})

const nextRoundLabel = computed(() => {
  const s = Math.max(0, nextRoundLeft.value)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
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

function startShuffleLoop() {
  if (shuffleTimer) return
  shuffleTimer = setInterval(() => {
    // Only shuffle verified / taken ticket numbers (real owners)
    const pool = [...takenPool.value]
    if (!pool.length) {
      visibleBalls.value = []
      return
    }
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[pool[i], pool[j]] = [pool[j], pool[i]]
    }
    visibleBalls.value = pool.slice(0, Math.min(24, pool.length))
  }, 140)
}

function stopShuffleLoop() {
  if (shuffleTimer) {
    clearInterval(shuffleTimer)
    shuffleTimer = null
  }
}

function applyDrawResult(res) {
  drawResult.value = res
  store.raffle = {
    ...store.raffle,
    winner1st: res.winner_1st,
    winner2nd: res.winner_2nd,
    winner3rd: res.winner_3rd,
    drawCompleted: true,
    nextRoundAt: res.next_round_at_ms || store.raffle.nextRoundAt,
    winnerRevealSeconds: res.winner_reveal_seconds || store.raffle.winnerRevealSeconds || 6,
    winnersNotified: !!res.winners_notified,
  }
  if (res.next_round_at_ms) {
    nextRoundEndsAt.value = res.next_round_at_ms
  }
}

async function runDrawAndReveal() {
  if (drawStarted) return
  drawStarted = true
  phase.value = 'drawing'
  startShuffleLoop()

  // Keep shuffle visible briefly after 0
  await new Promise((r) => setTimeout(r, 1800))

  try {
    const res = await runLotteryDraw()
    applyDrawResult(res)
  } catch (e) {
    const data = e.response?.data
    if (data?.winner_1st) {
      applyDrawResult(data)
    } else if (data?.error_code === 'no_tickets') {
      enterStuckWaitingRestart()
      return
    } else {
      await loadPublicSettings()
      if (store.raffle.winner1st) {
        applyDrawResult({
          winner_1st: store.raffle.winner1st,
          winner_2nd: store.raffle.winner2nd,
          winner_3rd: store.raffle.winner3rd,
          prize_1st: store.raffle.prize1st,
          prize_2nd: store.raffle.prize2nd,
          prize_3rd: store.raffle.prize3rd,
          next_round_at_ms: store.raffle.nextRoundAt,
          taken_numbers: [...store.takenNumbers],
        })
      } else if (!takenPool.value.length) {
        enterStuckWaitingRestart()
        return
      } else {
        drawStarted = false
        setTimeout(runDrawAndReveal, 2000)
        return
      }
    }
  }

  stopShuffleLoop()
  const rows = [
    { place: 1, label: '1ኛ እጣ', number: drawResult.value.winner_1st, prize: drawResult.value.prize_1st },
    { place: 2, label: '2ኛ እጣ', number: drawResult.value.winner_2nd, prize: drawResult.value.prize_2nd },
    { place: 3, label: '3ኛ እጣ', number: drawResult.value.winner_3rd, prize: drawResult.value.prize_3rd },
  ].filter((r) => r.number)

  phase.value = 'reveal'
  revealedRows.value = []
  let i = 0

  const revealMs = Math.max(2000, (store.raffle.winnerRevealSeconds || drawResult.value?.winner_reveal_seconds || 6) * 1000)

  const showNext = () => {
    if (i >= rows.length) {
      phase.value = 'done'
      finishAnnounceAndNotify()
      return
    }
    const row = rows[i]
    revealLabel.value = row.label
    revealNumber.value = row.number
    revealPrizeText.value = `${formatAmount(row.prize)} ብር`
    // keep prior reveals in the list below (not including current until next)
    if (i > 0) {
      revealedRows.value = rows.slice(0, i)
    }
    i += 1
    revealTimers.push(
      setTimeout(() => {
        revealedRows.value = rows.slice(0, i)
        showNext()
      }, revealMs)
    )
  }
  showNext()
}

function resetLocalDrawState() {
  phase.value = 'idle'
  drawResult.value = null
  visibleBalls.value = []
  drawStarted = false
  resetStarted = false
  notifyStarted = false
  nextRoundEndsAt.value = 0
  nextRoundLeft.value = 0
  store.homeRefreshKey += 1
}

function startRecoverPoll() {
  if (recoverTimer) clearInterval(recoverTimer)
  recoverTimer = setInterval(async () => {
    await loadPublicSettings()
    if (store.raffle.drawCompleted) return

    const dateMode = (store.raffle.drawMode || 'date') === 'date'
    const ends = store.raffle.endsAt || 0

    // Date mode: admin restart sets a future endsAt
    if (dateMode) {
      if (ends <= Date.now() + 2000) return
      clearInterval(recoverTimer)
      recoverTimer = null
      resetLocalDrawState()
      return
    }

    // Non-date: restart clears endsAt; Start Draw sets a new future endsAt
    if (!ends || ends > Date.now() + 2000) {
      clearInterval(recoverTimer)
      recoverTimer = null
      resetLocalDrawState()
    }
  }, 3000)
}

function enterStuckWaitingRestart() {
  stopShuffleLoop()
  phase.value = 'stuck'
  drawStarted = false
  startRecoverPoll()
}

function enterManualAnnounce() {
  stopShuffleLoop()
  phase.value = 'manual'
  drawStarted = false
  startRecoverPoll()
}

async function finishAnnounceAndNotify() {
  if (notifyStarted) return
  notifyStarted = true
  try {
    const res = await notifyLotteryWinners()
    applyDrawResult(res)
    if (res.next_round_at_ms) {
      nextRoundEndsAt.value = res.next_round_at_ms
      store.raffle.nextRoundAt = res.next_round_at_ms
    }
    store.raffle.winnersNotified = true
    if (adminControlsRound.value) {
      startRecoverPoll()
    } else {
      startNextRoundClock()
    }
    loadPublicSettings()
  } catch (e) {
    const code = e.response?.data?.error_code
    const wait = Number(e.response?.data?.remaining_seconds) || 2
    notifyStarted = false
    if (code === 'announce_in_progress') {
      setTimeout(finishAnnounceAndNotify, Math.max(1000, wait * 1000))
      return
    }
    console.warn('notify winners failed', e)
    if (adminControlsRound.value) {
      startRecoverPoll()
    } else {
      startNextRoundClock()
    }
  }
}

function startNextRoundClock() {
  if (nextRoundTimer) clearInterval(nextRoundTimer)
  const end = nextRoundEndsAt.value || store.raffle.nextRoundAt || 0
  const tick = () => {
    nextRoundLeft.value = Math.max(0, Math.ceil((end - Date.now()) / 1000))
    if (nextRoundLeft.value <= 0) {
      clearInterval(nextRoundTimer)
      nextRoundTimer = null
      doStartNextRound()
    }
  }
  tick()
  nextRoundTimer = setInterval(tick, 500)
}

async function doStartNextRound() {
  if (resetStarted) return
  resetStarted = true
  try {
    const res = await startLotteryNextRound()
    if (res.settings) applyPublicSettings(res.settings)
    else await loadPublicSettings()
  } catch (e) {
    const code = e.response?.data?.error_code
    // Another client may have already started the round
    if (code === 'no_draw' || e.response?.status === 400) {
      await loadPublicSettings()
      if (!store.raffle.drawCompleted) {
        /* continue to local reset below */
      } else {
        resetStarted = false
        setTimeout(doStartNextRound, 2500)
        return
      }
    } else {
      resetStarted = false
      setTimeout(doStartNextRound, 2500)
      return
    }
  }
  store.selectedNumbers = []
  store.tickets = []
  store.ticketStats = { active: 0, pending: 0, total: 0 }
  store.verifiedTakenNumbers = new Set()
  store.takenNumbers = new Set()
  store.homeRefreshKey += 1
  phase.value = 'idle'
  drawStarted = false
  resetStarted = false
  notifyStarted = false
  drawResult.value = null
  nextRoundEndsAt.value = 0
  nextRoundLeft.value = 0
}

watch(
  [inFinalMinute, isFinished, remainingSeconds],
  ([finalMin, finished, secs]) => {
    pulse.value = secs % 2 === 0

    // Skip while this client is mid-shuffle/reveal; late joiners (idle) jump to winners
    if (
      store.raffle.drawCompleted &&
      store.raffle.winner1st &&
      phase.value !== 'reveal' &&
      phase.value !== 'drawing' &&
      phase.value !== 'final'
    ) {
      if (phase.value !== 'done') {
        drawResult.value = {
          winner_1st: store.raffle.winner1st,
          winner_2nd: store.raffle.winner2nd,
          winner_3rd: store.raffle.winner3rd,
          prize_1st: store.raffle.prize1st,
          prize_2nd: store.raffle.prize2nd,
          prize_3rd: store.raffle.prize3rd,
        }
        nextRoundEndsAt.value = store.raffle.nextRoundAt || 0
        phase.value = 'done'
        // Late joiners / refresh: DMs wait until announce window ends (server-gated)
        finishAnnounceAndNotify()
      }
      return
    }

    if (phase.value === 'stuck' || phase.value === 'manual') {
      return
    }

    // Date mode: last 60s. Admin-started draw: entire timer window.
    const inDrawWindow = adminControlsRound.value
      ? secs > 0 || finished
      : finalMin

    if (!autoAnnounce.value) {
      if (finished && !store.raffle.drawCompleted) {
        enterManualAnnounce()
      }
      return
    }

    if (finished && !drawStarted && !store.raffle.drawCompleted) {
      runDrawAndReveal()
    } else if (inDrawWindow && !finished && !drawStarted) {
      phase.value = 'final'
      startShuffleLoop()
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (store.raffle.drawCompleted && store.raffle.winner1st && phase.value !== 'reveal') {
    drawResult.value = {
      winner_1st: store.raffle.winner1st,
      winner_2nd: store.raffle.winner2nd,
      winner_3rd: store.raffle.winner3rd,
      prize_1st: store.raffle.prize1st,
      prize_2nd: store.raffle.prize2nd,
      prize_3rd: store.raffle.prize3rd,
    }
    nextRoundEndsAt.value = store.raffle.nextRoundAt || 0
    phase.value = 'done'
    finishAnnounceAndNotify()
  }
})

onUnmounted(() => {
  stopShuffleLoop()
  revealTimers.forEach(clearTimeout)
  if (nextRoundTimer) clearInterval(nextRoundTimer)
  if (recoverTimer) clearInterval(recoverTimer)
})
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
