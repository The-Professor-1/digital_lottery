<template>
  <article
    class="rounded-card overflow-hidden bg-gradient-to-b from-forest-dim via-forest-deep to-ink-100 border border-forest/20"
  >
    <button type="button" class="block w-full text-left" @click="$emit('open')">
      <div class="relative aspect-[16/10] bg-gradient-to-b from-zinc-200 to-zinc-400">
        <img
          :key="raffle.image"
          :src="raffle.image"
          :alt="raffle.name"
          class="w-full h-full object-cover object-center"
          loading="lazy"
        />
        <span
          v-if="raffle.badge === 'trending'"
          class="absolute top-3 left-3 inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-900 text-[11px] font-semibold px-2.5 py-1"
        >
          <Flame :size="12" /> {{ t.trending }}
        </span>
        <span
          v-else
          class="absolute bottom-3 left-3 inline-flex items-center rounded-full bg-forest text-white text-[11px] font-bold px-2.5 py-1"
        >
          {{ t.newBadge }}
        </span>
        <div class="absolute top-3 right-3 flex items-center gap-0.5">
          <Star
            v-for="n in 5"
            :key="n"
            :size="14"
            class="text-gold fill-gold drop-shadow"
          />
        </div>
      </div>

      <div class="px-4 pt-3 pb-2">
        <h2 class="text-white text-xl font-bold leading-tight">{{ raffle.name }}</h2>
        <p class="text-lime-400/90 text-sm mt-0.5">{{ raffle.color }}</p>
      </div>
    </button>

    <div class="px-4 pb-4 space-y-3">
      <CountdownTimer :ends-at="raffle.endsAt" />
      <TicketProgress :sold-count="raffle.soldCount" :total-tickets="raffle.totalTickets" />

      <div class="flex items-center gap-3 pt-1">
        <div class="flex items-center gap-1.5 text-white/70 text-sm">
          <Users :size="16" />
          <span>{{ raffle.participants }}</span>
        </div>
        <button type="button" class="btn-gold flex-1 py-3 text-sm" @click="$emit('buy')">
          {{ t.buyTicket }}
        </button>
      </div>
    </div>
  </article>
</template>

<script setup>
import { Flame, Star, Users } from 'lucide-vue-next'
import CountdownTimer from './CountdownTimer.vue'
import TicketProgress from './TicketProgress.vue'
import { useI18n } from '../../composables/useI18n'

defineProps({
  raffle: { type: Object, required: true },
})
defineEmits(['open', 'buy'])

const { t } = useI18n()
</script>
