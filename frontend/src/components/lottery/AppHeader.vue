<template>
  <header class="sticky top-0 z-30 bg-ink/95 backdrop-blur-md px-3 pt-3 pb-2">
    <div class="flex items-center gap-2">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <div
          class="w-10 h-10 rounded-xl bg-gradient-to-br from-gold to-gold-light flex items-center justify-center shadow-glow-sm shrink-0"
        >
          <Trophy :size="20" class="text-black" />
        </div>
        <div class="min-w-0">
          <h1 class="text-gold font-bold text-[15px] leading-tight truncate">{{ store.brandName }}</h1>
        </div>
      </div>

      <div class="relative">
        <button
          type="button"
          class="flex items-center gap-1.5 bg-ink-200 border border-white/10 rounded-full px-2.5 py-1.5 text-xs text-white/90"
          @click="langOpen = !langOpen"
        >
          <Globe :size="14" class="text-gold" />
          <span>{{ t.langName }}</span>
          <ChevronDown :size="12" class="opacity-60" />
        </button>
        <div
          v-if="langOpen"
          class="absolute right-0 mt-1 w-36 rounded-xl bg-ink-200 border border-white/10 shadow-lg overflow-hidden z-40"
        >
          <button
            v-for="opt in langOptions"
            :key="opt.code"
            type="button"
            class="w-full text-left px-3 py-2 text-sm hover:bg-white/5"
            :class="locale === opt.code ? 'text-gold' : 'text-white/80'"
            @click="pickLang(opt.code)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <button
        type="button"
        class="relative w-9 h-9 rounded-full bg-ink-200 border border-white/10 flex items-center justify-center"
        aria-label="Notifications"
      >
        <Bell :size="16" class="text-gold" />
        <span class="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500" />
      </button>

      <button
        type="button"
        class="w-9 h-9 rounded-full bg-ink-200 border border-white/10 flex items-center justify-center"
        aria-label="Toggle theme"
        @click="toggleTheme"
      >
        <Sun v-if="store.theme === 'dark'" :size="16" class="text-white/80" />
        <Moon v-else :size="16" class="text-gold" />
      </button>
    </div>
  </header>
</template>

<script setup>
import { ref } from 'vue'
import { Trophy, Globe, Bell, Sun, Moon, ChevronDown } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { store, toggleTheme } from '../../stores/lottery'

const { locale, t, setLocale } = useI18n()
const langOpen = ref(false)

const langOptions = [
  { code: 'am', label: 'Amharic' },
  { code: 'en', label: 'English' },
  { code: 'om', label: 'Afan Oromo' },
]

function pickLang(code) {
  setLocale(code)
  langOpen.value = false
}
</script>
