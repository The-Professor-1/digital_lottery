import { computed, ref } from 'vue'
import { messages } from '../locales/messages'

const locale = ref(localStorage.getItem('gfj_locale') || 'am')

export function useI18n() {
  const t = computed(() => messages[locale.value] || messages.am)

  function setLocale(code) {
    locale.value = code
    localStorage.setItem('gfj_locale', code)
  }

  return { locale, t, setLocale, messages }
}
