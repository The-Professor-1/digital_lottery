<template>
  <div class="space-y-4 pt-1 pb-4">
    <HomeView v-if="store.items.length <= 1" embedded />
    <template v-else>
      <div class="flex items-end justify-between gap-3">
        <div>
          <p class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">{{ store.brandName }}</p>
          <h1 class="text-2xl font-extrabold text-white mt-1">{{ t.lotteries }}</h1>
        </div>
        <span class="text-xs text-white/45">{{ store.items.length }} {{ t.available }}</span>
      </div>

      <article
        v-for="item in store.items"
        :key="item.id"
        class="rounded-card overflow-hidden bg-ink-200 border border-white/10"
      >
        <button type="button" class="block w-full text-left" @click="openItem(item)">
          <img
            v-if="item.image_url"
            :src="item.image_url"
            :alt="item.name"
            class="w-full h-44 object-cover"
          />
          <div class="p-4 space-y-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-gold text-[11px] font-semibold uppercase tracking-wide">
                  {{ item.hero_title || item.name }}
                </p>
                <h2 class="text-white text-lg font-bold truncate">{{ item.name }}</h2>
                <p v-if="item.description" class="text-xs text-white/50 mt-1 line-clamp-2">
                  {{ item.description }}
                </p>
              </div>
              <div class="text-right shrink-0">
                <p class="text-[10px] text-white/40">{{ t.ticketPrice }}</p>
                <p class="text-gold font-bold">{{ formatBirr(item.ticket_price) }}</p>
              </div>
            </div>

            <PrizeList
              :prizes="item.prizes || []"
              :prize1st="0"
              :prize2nd="0"
              :prize3rd="0"
              compact
            />

            <div class="flex items-center justify-between gap-3 pt-1">
              <div class="min-w-0 flex-1">
                <TicketProgress
                  :sold-count="item.sold_count || 0"
                  :total-tickets="item.total_tickets || 1"
                  :show-remaining="false"
                />
              </div>
              <span class="text-xs text-gold font-semibold inline-flex items-center gap-1 shrink-0">
                {{ t.viewLottery }} <ChevronRight :size="14" />
              </span>
            </div>
          </div>
        </button>
      </article>
    </template>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronRight } from 'lucide-vue-next'
import HomeView from './HomeView.vue'
import PrizeList from '../../components/lottery/PrizeList.vue'
import TicketProgress from '../../components/lottery/TicketProgress.vue'
import { useI18n } from '../../composables/useI18n'
import { formatBirr } from '../../data/mock'
import { store, loadLanding } from '../../stores/lottery'

const { t } = useI18n()
const router = useRouter()

onMounted(() => {
  loadLanding()
})

function openItem(item) {
  router.push('/raffle/' + item.id)
}
</script>
