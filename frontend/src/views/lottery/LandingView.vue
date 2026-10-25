<template>
  <div class="space-y-4 pt-1 pb-4">
    <HomeView v-if="store.items.length === 1" embedded />
    <template v-else-if="store.items.length > 1">
      <div class="flex items-end justify-between gap-3">
        <div>
          <p class="text-gold text-xs font-semibold tracking-[0.18em] uppercase">{{ store.brandName }}</p>
          <h1 class="text-2xl font-extrabold text-white mt-1">{{ landingText('lotteries', t.lotteries) }}</h1>
        </div>
        <span class="text-xs text-white/45">{{ store.items.length }} {{ landingText('available', t.available) }}</span>
      </div>

      <article
        v-for="item in store.items"
        :key="item.id"
        class="rounded-card overflow-hidden bg-ink-200 border border-white/10"
      >
        <div
          role="button"
          tabindex="0"
          class="block w-full text-left cursor-pointer"
          @click="openItem(item)"
          @keydown.enter="openItem(item)"
        >
          <img
            v-if="item.image_url"
            :src="item.image_url"
            :alt="item.name"
            class="w-full h-[22rem] object-cover cursor-zoom-in"
            @click.stop="openItemImage(item)"
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
                <p class="text-[10px] text-white/40">{{ landingText('ticketPrice', t.ticketPrice) }}</p>
                <p class="text-gold font-bold">{{ formatBirr(item.ticket_price, t.birr) }}</p>
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
                {{ landingText('viewLottery', t.viewLottery) }} <ChevronRight :size="14" />
              </span>
            </div>
          </div>
        </div>
      </article>
    </template>

    <div v-else-if="store.landingLoaded" class="rounded-card bg-ink-200 border border-white/10 p-8 text-center">
      <p class="text-white font-semibold">{{ landingText('noActiveLottery', t.noActiveLottery) }}</p>
      <p class="text-sm text-white/45 mt-1">{{ landingText('noActiveLotteryHint', t.noActiveLotteryHint) }}</p>
    </div>

    <ImageViewer :src="viewerSrc" :alt="viewerAlt" @close="viewerSrc = ''" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronRight } from 'lucide-vue-next'
import HomeView from './HomeView.vue'
import PrizeList from '../../components/lottery/PrizeList.vue'
import ImageViewer from '../../components/lottery/ImageViewer.vue'
import TicketProgress from '../../components/lottery/TicketProgress.vue'
import { useI18n } from '../../composables/useI18n'
import { formatBirr } from '../../data/mock'
import { store, loadLanding, landingText } from '../../stores/lottery'

const { t } = useI18n()
const router = useRouter()
const viewerSrc = ref('')
const viewerAlt = ref('')

onMounted(() => {
  loadLanding()
})

function openItem(item) {
  router.push('/raffle/' + item.id)
}

function openItemImage(item) {
  viewerSrc.value = item.image_url
  viewerAlt.value = item.name || ''
}
</script>
