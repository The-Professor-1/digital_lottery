<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-3"
      @click.self="$emit('close')"
    >
      <div
        class="w-full max-w-md rounded-2xl bg-ink-200 border border-white/10 shadow-xl overflow-hidden max-h-[85dvh] flex flex-col"
        role="dialog"
        aria-labelledby="notifications-title"
      >
        <div class="flex items-center justify-between gap-3 px-4 pt-4 pb-2 shrink-0">
          <h2 id="notifications-title" class="text-white font-bold text-[15px] truncate">
            {{ t.notifications }}
          </h2>
          <button
            type="button"
            class="w-8 h-8 rounded-full bg-ink border border-white/10 flex items-center justify-center text-white/70 hover:text-white"
            aria-label="Close"
            @click="$emit('close')"
          >
            <X :size="16" />
          </button>
        </div>

        <div class="flex items-center gap-2 px-4 pb-3 shrink-0">
          <div
            class="w-8 h-8 rounded-xl bg-gradient-to-br from-gold to-gold-light flex items-center justify-center"
          >
            <Trophy :size="16" class="text-black" />
          </div>
          <span class="text-sm font-semibold text-gold">{{ t.latestWinners }}</span>
        </div>

        <div v-if="roundGroups.length" class="overflow-y-auto px-4 pb-4 space-y-2">
          <article
            v-for="group in roundGroups"
            :key="group.key"
            class="rounded-2xl bg-ink-300/60 border border-white/5 p-3.5"
          >
            <div class="flex items-start gap-3">
              <div class="w-9 h-9 rounded-full bg-gold/15 border border-gold/30 flex items-center justify-center shrink-0">
                <Trophy :size="16" class="text-gold" />
              </div>
              <div class="min-w-0 flex-1">
                <p class="text-white font-bold text-[15px] truncate">
                  {{ group.label }}
                </p>
                <p class="text-xs text-white/45 mt-0.5">
                  {{ group.winners.length }} {{ group.winners.length === 1 ? t.winner : t.winnersLabel }}
                </p>
              </div>
              <span class="text-[10px] text-white/35 whitespace-nowrap mt-0.5">
                {{ formatDate(group.announcedAt) }}
              </span>
            </div>

            <div class="mt-3 space-y-2">
              <div
                v-for="winner in group.winners"
                :key="winner.id"
                class="rounded-xl bg-ink/60 border border-white/5 p-3"
              >
                <div class="flex items-start gap-2.5">
                  <div class="w-7 h-7 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
                    <User :size="13" class="text-gold" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <p class="text-white font-bold text-sm truncate">{{ winner.name || t.winner }}</p>
                    <p v-if="winner.phone" class="text-xs text-white/50 mt-0.5">{{ winner.phone }}</p>
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-2 mt-2">
                  <div class="rounded-lg bg-ink/70 border border-white/5 px-2.5 py-2">
                    <p class="text-[10px] uppercase tracking-wide text-white/40">{{ t.winningTicket }}</p>
                    <span class="inline-block bg-gold text-black text-[11px] font-bold px-2 py-0.5 rounded-md mt-1">
                      #{{ winner.ticket_number || winner.winner_number }}
                    </span>
                  </div>
                  <div class="rounded-lg bg-ink/70 border border-white/5 px-2.5 py-2">
                    <p class="text-[10px] uppercase tracking-wide text-white/40">{{ t.prize }}</p>
                    <p class="text-sm text-white/90 mt-1 break-words">
                      {{ winner.prize_name || winner.car_name || winner.lottery_item_name || '—' }}
                    </p>
                  </div>
                </div>

                <p v-if="winner.message" class="text-xs text-white/45 mt-2 leading-relaxed break-words">
                  {{ winner.message }}
                </p>
              </div>
            </div>
          </article>
        </div>

        <div v-else class="flex flex-col items-center text-center px-4 pb-6">
          <div class="w-14 h-14 rounded-2xl bg-ink border border-white/10 flex items-center justify-center mb-3">
            <Trophy :size="24" class="text-white/35" />
          </div>
          <p class="text-sm text-white/60">{{ t.winnerEmpty }}</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { Trophy, User, X } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { store } from '../../stores/lottery'

defineEmits(['close'])

const { t } = useI18n()

const roundGroups = computed(() => {
  const groups = new Map()
  for (const winner of store.winners || []) {
    const bucket = String(winner.announced_at || '').slice(0, 16)
    const key = winner.round_id
      ? `round:${winner.round_id}`
      : `${winner.lottery_item_id || 'global'}:${winner.lottery_label || ''}:${bucket}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: winner.lottery_label || winner.lottery_item_name || t.value.lotteryLabel,
        announcedAt: winner.announced_at || '',
        winners: [],
      })
    }
    groups.get(key).winners.push(winner)
  }
  const out = Array.from(groups.values())
  for (const group of out) {
    group.winners.sort((a, b) => String(b.announced_at || '').localeCompare(String(a.announced_at || '')))
  }
  out.sort((a, b) => String(b.announcedAt || '').localeCompare(String(a.announcedAt || '')))
  return out
})

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  } catch (e) {
    return ''
  }
}
</script>