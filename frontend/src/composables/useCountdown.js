import { onMounted, onUnmounted, ref, watch } from 'vue'

export function useCountdown(endsAtRef) {
  const days = ref('00')
  const hours = ref('00')
  const minutes = ref('00')
  const seconds = ref('00')
  let timer = null

  function tick() {
    const end = typeof endsAtRef === 'function' ? endsAtRef() : endsAtRef.value ?? endsAtRef
    const diff = Math.max(0, Number(end) - Date.now())
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
    timer = setInterval(tick, 1000)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  if (endsAtRef && typeof endsAtRef === 'object' && 'value' in endsAtRef) {
    watch(endsAtRef, tick)
  }

  return { days, hours, minutes, seconds }
}
