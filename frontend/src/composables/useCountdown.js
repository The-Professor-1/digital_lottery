import { onMounted, onUnmounted, ref, watch, computed } from 'vue'

export function useCountdown(endsAtRef) {
  const days = ref('00')
  const hours = ref('00')
  const minutes = ref('00')
  const seconds = ref('00')
  const remainingMs = ref(0)
  let timer = null

  function tick() {
    const end = typeof endsAtRef === 'function' ? endsAtRef() : endsAtRef.value ?? endsAtRef
    const diff = Math.max(0, Number(end) - Date.now())
    remainingMs.value = diff
    const d = Math.floor(diff / 86400000)
    const h = Math.floor((diff % 86400000) / 3600000)
    const m = Math.floor((diff % 3600000) / 60000)
    const s = Math.floor((diff % 60000) / 1000)
    days.value = String(d).padStart(2, '0')
    hours.value = String(h).padStart(2, '0')
    minutes.value = String(m).padStart(2, '0')
    seconds.value = String(s).padStart(2, '0')
  }

  onMounted(() => {
    tick()
    timer = setInterval(tick, 250)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  if (endsAtRef && typeof endsAtRef === 'object' && 'value' in endsAtRef) {
    watch(endsAtRef, tick)
  }

  const remainingSeconds = computed(() => Math.ceil(remainingMs.value / 1000))
  const inFinalMinute = computed(
    () => remainingMs.value > 0 && remainingMs.value <= 60000
  )
  const isFinished = computed(() => remainingMs.value <= 0)

  return {
    days,
    hours,
    minutes,
    seconds,
    remainingMs,
    remainingSeconds,
    inFinalMinute,
    isFinished,
  }
}
