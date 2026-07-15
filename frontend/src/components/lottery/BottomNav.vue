<template>
  <nav
    class="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-phone z-40 px-3 pb-3 pt-1 pointer-events-none"
  >
    <div
      class="pointer-events-auto flex items-stretch justify-around bg-ink-100/95 border border-white/10 rounded-2xl backdrop-blur-md px-2 py-1.5 shadow-lg"
    >
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="flex-1 flex flex-col items-center gap-0.5 py-2 rounded-xl transition-all"
        :class="
          isActive(item.to)
            ? 'text-gold bg-gold/10 shadow-glow-sm border border-gold/40'
            : 'text-white/45 border border-transparent'
        "
      >
        <component :is="item.icon" :size="20" :stroke-width="isActive(item.to) ? 2.4 : 2" />
        <span class="text-[11px] font-medium leading-none">{{ item.label }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Home, Ticket, User } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'

const route = useRoute()
const { t } = useI18n()

const items = computed(() => [
  { to: '/', icon: Home, label: t.value.home },
  { to: '/tickets', icon: Ticket, label: t.value.tickets },
  { to: '/profile', icon: User, label: t.value.profile },
])

function isActive(path) {
  if (path === '/') return route.path === '/' || route.path.startsWith('/raffle')
  return route.path.startsWith(path)
}
</script>
