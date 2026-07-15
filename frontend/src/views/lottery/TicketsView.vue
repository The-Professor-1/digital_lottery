<template>
  <div class="space-y-4 pt-2">
    <div>
      <h1 class="text-2xl font-bold text-white">{{ t.myTickets }}</h1>
      <p class="text-sm text-white/45 mt-0.5">{{ t.trackPurchases }}</p>
    </div>

    <div class="flex gap-2">
      <input
        v-model="query"
        type="tel"
        class="flex-1 rounded-xl bg-white text-black px-3 py-3 text-sm outline-none"
        placeholder="251..."
      />
      <button
        type="button"
        class="btn-gold px-4 py-3 text-sm inline-flex items-center gap-1.5 shrink-0"
        @click="searched = true"
      >
        <Search :size="16" />
        {{ t.search }}
      </button>
    </div>

    <div class="grid grid-cols-3 gap-2">
      <div class="rounded-2xl bg-forest-deep/80 border border-forest/30 p-3 text-center">
        <p class="text-2xl font-bold text-emerald-400">{{ stats.active }}</p>
        <p class="text-xs text-white/60 mt-0.5">{{ t.active }}</p>
      </div>
      <div class="rounded-2xl bg-amber-950/50 border border-gold/20 p-3 text-center">
        <p class="text-2xl font-bold text-gold">{{ stats.pending }}</p>
        <p class="text-xs text-white/60 mt-0.5">{{ t.pending }}</p>
      </div>
      <div class="rounded-2xl bg-amber-950/50 border border-gold/20 p-3 text-center">
        <p class="text-2xl font-bold text-gold">{{ stats.total }}</p>
        <p class="text-xs text-white/60 mt-0.5">{{ t.total }}</p>
      </div>
    </div>

    <div v-if="results.length" class="space-y-2">
      <article
        v-for="ticket in results"
        :key="ticket.id"
        class="rounded-2xl bg-ink-200 border border-white/5 p-4"
      >
        <div class="flex items-start justify-between gap-2">
          <div>
            <p class="font-semibold text-white">{{ ticket.raffleName }}</p>
            <p class="text-xs text-white/45 mt-0.5">{{ ticket.createdAt }}</p>
          </div>
          <span
            class="text-[11px] font-bold uppercase px-2 py-1 rounded-md"
            :class="
              ticket.status === 'active'
                ? 'bg-forest/30 text-emerald-300'
                : 'bg-gold/20 text-gold'
            "
          >
            {{ ticket.status }}
          </span>
        </div>
        <div class="flex flex-wrap gap-1.5 mt-3">
          <span
            v-for="n in ticket.numbers"
            :key="n"
            class="bg-gold text-black text-xs font-bold px-2 py-1 rounded-md"
          >
            #{{ n }}
          </span>
        </div>
        <p class="text-gold font-semibold mt-2 text-sm">{{ formatBirr(ticket.amount) }}</p>
      </article>
    </div>

    <div v-else class="flex flex-col items-center text-center py-12 px-4">
      <div
        class="w-16 h-16 rounded-2xl bg-ink-200 border border-gold/20 shadow-glow-sm flex items-center justify-center mb-4"
      >
        <Ticket :size="28" class="text-gold" />
      </div>
      <p class="text-white font-medium">{{ t.noTicketsYet }}</p>
      <p class="text-xs text-white/40 mt-1.5">{{ t.enterPhoneHint }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Search, Ticket } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { formatBirr } from '../../data/mock'
import { store } from '../../stores/lottery'

const { t } = useI18n()
const query = ref(store.phone)
const searched = ref(true)

const results = computed(() => {
  if (!searched.value && !query.value) return []
  const q = (searched.value ? query.value : store.phone).replace(/\D/g, '')
  if (!q) return []
  return store.tickets.filter((tk) => tk.phone.replace(/\D/g, '').includes(q))
})

const stats = computed(() => {
  const list = results.value
  return {
    active: list.filter((t) => t.status === 'active').length,
    pending: list.filter((t) => t.status === 'pending').length,
    total: list.length,
  }
})
</script>
