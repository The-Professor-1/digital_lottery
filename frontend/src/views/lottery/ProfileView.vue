<template>
  <div class="pt-2 flex flex-col min-h-[calc(100dvh-10rem)]">
    <div
      class="rounded-card bg-gradient-to-r from-forest-dim to-forest-deep border border-forest/25 p-4 flex items-center gap-4"
    >
      <div
        class="w-14 h-14 rounded-2xl bg-gold flex items-center justify-center shrink-0 shadow-glow-sm"
      >
        <Phone :size="26" class="text-black" />
      </div>
      <div class="min-w-0">
        <p class="text-sm text-white/70">{{ t.userPhone }}</p>
        <p class="text-xl font-bold text-white tracking-wide truncate">{{ store.phone }}</p>
      </div>
    </div>

    <div class="mt-auto pt-10 pb-4 text-center text-[11px] text-white/35 leading-relaxed px-2">
      <p>© 2026 {{ store.brandName }}. All Rights Reserved.</p>
      <p class="mt-1">
        {{ t.designedBy }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { Phone } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { store } from '../../stores/lottery'

const { t } = useI18n()
</script>
