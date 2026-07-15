import { computed, ref } from 'vue'
import { messages } from '../locales/messages'

const LOCALE_KEY = 'gfj_locale'
const USER_SET_KEY = 'gfj_locale_user_set'

const saved = localStorage.getItem(LOCALE_KEY)
const locale = ref(saved && messages[saved] ? saved : 'am')

export function useI18n() {
  const t = computed(() => messages[locale.value] || messages.am)

  function setLocale(code, { userChosen = true } = {}) {
    if (!messages[code]) return
    locale.value = code
    localStorage.setItem(LOCALE_KEY, code)
    if (userChosen) {
      localStorage.setItem(USER_SET_KEY, '1')
    }
  }

  /** Apply bot/API language only if user has not overridden it in the app. */
  function applyPreferredLocale(code) {
    if (!code || !messages[code]) return
    if (localStorage.getItem(USER_SET_KEY) === '1') return
    setLocale(code, { userChosen: false })
  }

  return { locale, t, setLocale, applyPreferredLocale, messages }
}
