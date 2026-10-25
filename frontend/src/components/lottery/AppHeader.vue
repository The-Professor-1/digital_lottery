<template>
  <header class="sticky top-0 z-30 bg-app/90 backdrop-blur-xl border-b border-line/60 px-3 pt-3 pb-2">
    <div class="flex items-center gap-2">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <div
          class="w-10 h-10 rounded-2xl bg-gradient-to-br from-gold to-gold-light border border-gold/20 flex items-center justify-center shadow-glow-sm shrink-0"
        >
          <Trophy :size="20" class="text-black" />
        </div>
        <div class="min-w-0 h-10 overflow-hidden flex flex-col justify-center">
          <h1 class="text-gold font-display font-semibold text-[16px] leading-[1.08] break-words">{{ brandLines[0] }}</h1>
          <h1 v-if="brandLines[1]" class="text-gold font-display font-semibold text-[16px] leading-[1.08] break-words">
            {{ brandLines[1] }}
          </h1>
        </div>
      </div>

      <div class="relative">
        <button
          type="button"
          class="flex items-center gap-1.5 bg-surface-2 border border-line rounded-full px-2.5 py-1.5 text-xs text-content/90"
          @click="langOpen = !langOpen"
        >
          <Globe :size="14" class="text-gold" />
          <span>{{ t.langName }}</span>
          <ChevronDown :size="12" class="opacity-60" />
        </button>
        <div
          v-if="langOpen"
          class="absolute right-0 mt-1 w-36 rounded-xl bg-surface-2 border border-line shadow-lg overflow-hidden z-40"
        >
          <button
            v-for="opt in langOptions"
            :key="opt.code"
            type="button"
            class="w-full text-left px-3 py-2 text-sm hover:bg-content/5"
            :class="locale === opt.code ? 'text-gold' : 'text-content/80'"
            @click="pickLang(opt.code)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <button
        type="button"
        class="relative w-9 h-9 rounded-full bg-surface-2 border border-line flex items-center justify-center"
        aria-label="Notifications"
        @click="openNotice"
      >
        <Bell :size="16" class="text-gold" />
        <span v-if="store.winners.length" class="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-danger" />
      </button>

      <button
        type="button"
        class="w-9 h-9 rounded-full bg-surface-2 border border-line flex items-center justify-center"
        aria-label="Toggle theme"
        @click="toggleTheme"
      >
        <Sun v-if="store.theme === 'dark'" :size="16" class="text-content/80" />
        <Moon v-else :size="16" class="text-gold" />
      </button>
    </div>
    <NotificationsModal v-if="noticeOpen" @close="noticeOpen = false" />
  </header>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Trophy, Globe, Bell, Sun, Moon, ChevronDown } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import NotificationsModal from './NotificationsModal.vue'
import { store, toggleTheme, loadWinners } from '../../stores/lottery'

const { locale, t, setLocale } = useI18n()
const langOpen = ref(false)
const noticeOpen = ref(false)

const brandLines = computed(() => {
  const parts = String(store.brandName || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return ['Digital Lottery']
  if (parts.length === 1) return [parts[0]]
  return [parts[0], parts.slice(1).join(' ')]
})

const langOptions = [
  { code: 'am', label: 'አማርኛ' },
  { code: 'en', label: 'English' },
]

async function openNotice() {
  langOpen.value = false
  noticeOpen.value = true
  await loadWinners()
}

function pickLang(code) {
  setLocale(code)
  langOpen.value = false
  import('../../services/api')
    .then(({ setLotteryLanguage }) => setLotteryLanguage(code))
    .catch(() => {})
}
</script>
