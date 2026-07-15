<template>
  <div class="rounded-2xl bg-gradient-to-b from-forest-dim to-forest-deep border border-forest/30 p-3">
    <div v-if="showLabel" class="flex items-center gap-1.5 text-sm text-white/90 mb-2">
      <Flame :size="14" class="text-gold" />
      <span>{{ t.remainingTime }}</span>
    </div>
    <div class="flex items-center justify-between gap-1">
      <div v-for="(unit, i) in units" :key="unit.key" class="contents">
        <div class="flex-1 text-center">
          <div
            class="bg-black/50 rounded-xl py-2.5 border border-white/5 shadow-inner"
          >
            <div class="text-gold text-xl font-bold tabular-nums leading-none">{{ unit.value }}</div>
          </div>
          <div class="text-[10px] text-gold/80 mt-1.5">{{ unit.label }}</div>
        </div>
        <div v-if="i < units.length - 1" class="text-gold font-bold text-lg pb-5 px-0.5">:</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Flame } from 'lucide-vue-next'
import { useCountdown } from '../../composables/useCountdown'
import { useI18n } from '../../composables/useI18n'

const props = defineProps({
  endsAt: { type: Number, required: true },
  showLabel: { type: Boolean, default: false },
})

const { t } = useI18n()
const { days, hours, minutes, seconds } = useCountdown(() => props.endsAt)

const units = computed(() => [
  { key: 'd', value: days.value, label: t.value.days },
  { key: 'h', value: hours.value, label: t.value.hours },
  { key: 'm', value: minutes.value, label: t.value.minutes },
  { key: 's', value: seconds.value, label: t.value.seconds },
])
</script>
