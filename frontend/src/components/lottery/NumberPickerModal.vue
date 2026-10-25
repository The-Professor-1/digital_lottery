<template>
  <Transition name="sheet">
    <div
      v-if="store.showPicker"
      class="sheet-panel fixed inset-0 z-50 flex flex-col bg-ink-100 max-w-phone mx-auto"
    >
      <div class="px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-2 flex items-start justify-between gap-3 border-b border-white/10">
        <div>
          <h2 class="text-lg font-bold text-white">{{ t.pickNumbers }}</h2>
          <p class="text-sm text-white/55 mt-0.5">
            {{ t.pickFreeSubtitle(store.selectedNumbers.length) }}
          </p>
        </div>
        <button
          type="button"
          class="w-10 h-10 rounded-xl bg-red-900/80 flex items-center justify-center shrink-0"
          @click="closePicker"
        >
          <X :size="18" class="text-white" />
        </button>
      </div>

      <div class="px-4 py-2 flex items-center gap-4 text-[11px] text-white/70">
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3.5 h-3.5 rounded bg-sold" /> {{ t.taken }}
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3.5 h-3.5 rounded bg-ink-300" /> {{ t.open }}
        </span>
        <span class="ml-auto text-gold font-semibold tabular-nums">
          {{ formatBirr(totalAmount) }}
        </span>
      </div>

      <div class="flex-1 overflow-y-auto no-scrollbar px-3 pb-3">
        <div class="grid grid-cols-8 gap-1.5">
          <button
            v-for="n in total"
            :key="n"
            type="button"
            class="aspect-square rounded-lg text-[11px] font-semibold tabular-nums transition-colors"
            :class="tileClass(n)"
            :disabled="isTaken(n)"
            @click="toggleNumber(n)"
          >
            {{ padNumber(n) }}
          </button>
        </div>
      </div>

      <div class="p-4 border-t border-white/5 bg-ink-100 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <button
          type="button"
          class="w-full py-3.5 rounded-2xl font-bold text-sm transition-all"
          :class="
            complete
              ? 'btn-green'
              : 'bg-forest/45 text-white/85 border border-forest/50 cursor-not-allowed shadow-none'
          "
          :disabled="!complete"
          @click="confirmPicker"
        >
          {{
            complete
              ? t.continueWithAmount(store.selectedNumbers.length, formatBirr(totalAmount))
              : t.selectAtLeastOne
          }}
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { padNumber, formatBirr } from '../../data/mock'
import {
  store,
  closePicker,
  toggleNumber,
  confirmPicker,
  isTaken,
} from '../../stores/lottery'

const { t } = useI18n()
const total = computed(() => store.raffle.totalTickets)
const complete = computed(() => store.selectedNumbers.length >= 1)
const totalAmount = computed(
  () => store.selectedNumbers.length * (store.raffle.ticketPrice || 0)
)

function tileClass(n) {
  if (isTaken(n)) return 'bg-sold text-red-200/80 cursor-not-allowed'
  if (store.selectedNumbers.includes(n)) return 'bg-gold text-black shadow-glow-sm'
  return 'bg-ink-300 text-white/90 hover:bg-ink-200'
}
</script>
