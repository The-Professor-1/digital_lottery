<template>
  <Transition name="sheet">
    <div
      v-if="store.showPicker"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/70"
      @click.self="closePicker"
    >
      <div
        class="sheet-panel w-full max-w-phone bg-ink-100 rounded-t-3xl border-t border-white/10 flex flex-col max-h-[92dvh]"
      >
        <div class="px-4 pt-4 pb-2 flex items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-bold text-white">{{ t.pickNumbers }}</h2>
            <p class="text-sm text-white/55 mt-0.5">
              {{ t.pickSubtitle(store.quantity, store.selectedNumbers.length) }}
            </p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button
              type="button"
              class="w-10 h-10 rounded-xl bg-gold flex items-center justify-center"
              @click="quickPick"
            >
              <Shuffle :size="18" class="text-black" />
            </button>
            <button
              type="button"
              class="w-10 h-10 rounded-xl bg-red-900/80 flex items-center justify-center"
              @click="closePicker"
            >
              <X :size="18" class="text-white" />
            </button>
          </div>
        </div>

        <div class="px-4 py-2 flex items-center gap-4 text-[11px] text-white/70">
          <span class="inline-flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 rounded bg-gold" /> {{ t.selected }}
          </span>
          <span class="inline-flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 rounded bg-sold" /> {{ t.taken }}
          </span>
          <span class="inline-flex items-center gap-1.5">
            <span class="w-3.5 h-3.5 rounded bg-ink-300" /> {{ t.open }}
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
              :disabled="soldNumbers.has(n)"
              @click="toggleNumber(n)"
            >
              {{ padNumber(n) }}
            </button>
          </div>
        </div>

        <div class="p-4 border-t border-white/5 bg-ink-100">
          <button
            type="button"
            class="w-full py-3.5 rounded-2xl font-bold text-sm transition-all"
            :class="
              complete
                ? 'btn-gold'
                : 'bg-ink-300 text-white/40 cursor-not-allowed'
            "
            :disabled="!complete"
            @click="confirmPicker"
          >
            {{
              complete
                ? t.continueWith(store.selectedNumbers.length)
                : t.selectMore(store.quantity - store.selectedNumbers.length)
            }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { Shuffle, X } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { soldNumbers, padNumber } from '../../data/mock'
import {
  store,
  closePicker,
  toggleNumber,
  quickPick,
  confirmPicker,
} from '../../stores/lottery'

const { t } = useI18n()
const total = computed(() => store.raffle.totalTickets)
const complete = computed(() => store.selectedNumbers.length === store.quantity)

function tileClass(n) {
  if (soldNumbers.has(n)) return 'bg-sold text-red-200/80 cursor-not-allowed'
  if (store.selectedNumbers.includes(n)) return 'bg-gold text-black shadow-glow-sm'
  return 'bg-ink-300 text-white/90 hover:bg-ink-200'
}
</script>
