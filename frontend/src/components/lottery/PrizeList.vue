<template>
  <div :class="compact ? 'space-y-1.5' : 'space-y-2.5'">
    <article
      v-for="(prize, index) in rows"
      :key="prize.key || index"
      class="rounded-xl border border-white/10 bg-ink-200/65 overflow-hidden"
      :class="compact ? 'p-2.5' : 'p-3'"
    >
      <div class="flex items-start gap-3">
        <img
          v-if="prize.image_url"
          :src="prize.image_url"
          :alt="prize.title || prize.place"
          class="rounded-lg object-cover shrink-0"
          :class="compact ? 'w-12 h-12' : 'w-20 h-20'"
        />
        <div class="min-w-0 flex-1">
          <p class="text-gold font-bold uppercase tracking-wide" :class="compact ? 'text-[10px]' : 'text-xs'">
            {{ placeLabel(prize.place) }}
          </p>
          <p class="text-white font-semibold break-words" :class="compact ? 'text-sm' : 'text-base'">
            {{ prize.title || prize.description || t.prize }}
          </p>
          <p v-if="prize.description && prize.description !== prize.title" class="text-xs text-white/55 mt-0.5 break-words">
            {{ prize.description }}
          </p>
          <p v-if="prize.amount" class="text-gold font-bold mt-1" :class="compact ? 'text-sm' : 'text-lg'">
            {{ formatAmount(prize.amount) }} {{ t.birr }}
          </p>
        </div>
      </div>
    </article>
    <p v-if="!rows.length" class="text-xs text-white/45">{{ t.noPrizes }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../composables/useI18n'

const { t } = useI18n()

const props = defineProps({
  prizes: { type: Array, default: () => [] },
  prize1st: { type: Number, default: 0 },
  prize2nd: { type: Number, default: 0 },
  prize3rd: { type: Number, default: 0 },
  compact: { type: Boolean, default: false },
})

const rows = computed(() => {
  if (Array.isArray(props.prizes) && props.prizes.length) {
    return props.prizes.map((p, i) => ({ ...p, key: p.place || i }))
  }
  return [
    { key: '1st', place: '1st', title: t.value.firstPrize, amount: props.prize1st },
    { key: '2nd', place: '2nd', title: t.value.secondPrize, amount: props.prize2nd },
    { key: '3rd', place: '3rd', title: t.value.thirdPrize, amount: props.prize3rd },
  ].filter((p) => Number(p.amount || 0) > 0)
})

function placeLabel(place) {
  const raw = String(place || '').trim()
  const normalized = raw.toLowerCase()
  if (/^(1|1st|first)(\b|$)/.test(normalized)) return t.value.first
  if (/^(2|2nd|second)(\b|$)/.test(normalized)) return t.value.second
  if (/^(3|3rd|third)(\b|$)/.test(normalized)) return t.value.third
  return raw || t.value.prize
}

function formatAmount(n) {
  return Number(n || 0).toLocaleString('en-US')
}
</script>
