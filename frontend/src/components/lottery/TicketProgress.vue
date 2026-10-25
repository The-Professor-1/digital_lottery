<template>
  <div>
    <div class="flex items-center justify-between text-xs mb-1.5">
      <span class="text-white/70">{{ soldCount.toLocaleString() }} {{ t.sold }}</span>
      <span class="text-forest font-semibold">{{ percent }}% {{ t.filled }}</span>
    </div>
    <div class="h-1.5 rounded-full bg-white/10 overflow-hidden">
      <div
        class="h-full rounded-full bg-gradient-to-r from-forest to-emerald-400 transition-all duration-500"
        :style="{ width: `${percent}%` }"
      />
    </div>
    <p v-if="showRemaining" class="text-[11px] text-white/45 mt-1.5">
      {{ remaining.toLocaleString() }} {{ t.remainingTickets }}
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../composables/useI18n'

const props = defineProps({
  soldCount: { type: Number, required: true },
  totalTickets: { type: Number, required: true },
  showRemaining: { type: Boolean, default: true },
})

const { t } = useI18n()
const percent = computed(() => Math.round((props.soldCount / props.totalTickets) * 100))
const remaining = computed(() => props.totalTickets - props.soldCount)
</script>
