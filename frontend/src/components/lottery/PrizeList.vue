<template>
  <div :class="compact ? 'space-y-1.5' : 'space-y-2.5'">
    <template v-if="compact">
      <article
        v-for="(prize, index) in rows"
        :key="prize.key || index"
        class="rounded-xl border border-line/70 bg-surface/70 px-3 py-2 flex items-center gap-2.5"
      >
        <img
          v-if="prize.image_url"
          :src="prize.image_url"
          :alt="prize.title || prize.place"
          class="w-10 h-10 rounded-lg object-cover shrink-0"
        />
        <div class="min-w-0 flex-1">
          <p class="text-gold font-bold uppercase tracking-wide text-[10px]">{{ prize.place || 'Prize' }}</p>
          <p class="text-content font-semibold text-sm truncate">{{ prize.title || prize.description || 'Prize' }}</p>
          <p v-if="prize.description && prize.description !== prize.title && !prize.amount" class="text-[11px] text-content/50 truncate">
            {{ prize.description }}
          </p>
        </div>
        <p v-if="prize.amount" class="text-gold font-bold text-sm whitespace-nowrap">
          {{ formatAmount(prize.amount) }} <span class="text-[10px] font-semibold">Birr</span>
        </p>
      </article>
    </template>
    <template v-else>
      <article
        v-for="(prize, index) in rows"
        :key="prize.key || index"
        class="rounded-xl border border-line bg-surface-2/65 overflow-hidden p-3"
      >
        <div class="flex items-start gap-3">
          <img
            v-if="prize.image_url"
            :src="prize.image_url"
            :alt="prize.title || prize.place"
            class="w-20 h-20 rounded-lg object-cover shrink-0"
          />
          <div class="min-w-0 flex-1">
            <p class="text-gold font-bold uppercase tracking-wide text-xs">{{ prize.place || 'Prize' }}</p>
            <p class="text-content font-semibold text-base break-words">{{ prize.title || prize.description || 'Prize' }}</p>
            <p v-if="prize.description && prize.description !== prize.title" class="text-xs text-content/55 mt-0.5 break-words">
              {{ prize.description }}
            </p>
            <p v-if="prize.amount" class="text-gold font-bold mt-1 text-lg">
              {{ formatAmount(prize.amount) }} Birr
            </p>
          </div>
        </div>
      </article>
    </template>
    <p v-if="!rows.length" class="text-xs text-content/45">No prizes configured yet.</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

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
    { key: '1st', place: '1st', title: '1st Prize', amount: props.prize1st },
    { key: '2nd', place: '2nd', title: '2nd Prize', amount: props.prize2nd },
    { key: '3rd', place: '3rd', title: '3rd Prize', amount: props.prize3rd },
  ].filter((p) => Number(p.amount || 0) > 0)
})

function formatAmount(n) {
  return Number(n || 0).toLocaleString('en-US')
}
</script>
