import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { initTelegramWebApp, getInitData } from './services/telegram'
import { registerTelegram } from './services/api'
import './style.css'

// Import views
import WaitingView from './views/WaitingView.vue'
import GameCompletedView from './views/GameCompletedView.vue'
import CardSelectionView from './views/CardSelectionView.vue'
import ActiveGameView from './views/ActiveGameView.vue'

const routes = [
  { path: '/', redirect: '/game' }, // Start at game view, it will route appropriately based on game status
  { path: '/waiting', name: 'waiting', component: WaitingView },
  { path: '/completed', name: 'completed', component: GameCompletedView },
  { path: '/select-card', name: 'select-card', component: CardSelectionView },
  { path: '/game', name: 'game', component: ActiveGameView },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Add navigation guard to route appropriately on initial load
router.beforeEach(async (to, from, next) => {
  // Only check on initial load (from root)
  if (from.name === null && to.path === '/game') {
    try {
      const { getCurrentGame } = await import('./services/api')
      const game = await getCurrentGame()
      if (game.status === 'waiting') {
        next('/select-card')
      } else if (game.status === 'completed') {
        next('/completed')
      } else {
        next() // Game is active, continue to game view
      }
    } catch (error) {
      // No game or error, continue to game view (it will handle routing)
      next()
    }
  } else {
    next()
  }
})

// Initialize Telegram Web App
const isTelegramApp = initTelegramWebApp()

// Authenticate with Telegram if running in Telegram Web App
if (isTelegramApp) {
  const initData = getInitData()
  if (initData && typeof initData === 'string' && initData.length > 0) {
    // Register/authenticate user with Telegram
    registerTelegram(initData)
      .then(async (data) => {
        console.log('✅ Telegram authentication successful:', data.user_id)
        
        // Check if user has phone number, if not try to get it from initData
        if (data.user && !data.user.phone_number) {
          try {
            const { getInitDataRaw } = await import('./services/telegram')
            const initDataRaw = getInitDataRaw()
            
            // Check if phone number is in initDataUnsafe
            if (initDataRaw && initDataRaw.user && initDataRaw.user.phone_number) {
              const { updateUserPhone } = await import('./services/api')
              await updateUserPhone(initDataRaw.user.phone_number)
              console.log('✅ Phone number saved from initData:', initDataRaw.user.phone_number)
            } else {
              // Phone number not available - user needs to share it through bot
              console.warn('⚠️ Phone number not available. User needs to share phone number through Telegram bot.')
            }
          } catch (error) {
            console.warn('⚠️ Phone number retrieval failed:', error)
            // Continue without phone number
          }
        }
      })
      .catch((error) => {
        console.error('❌ Telegram authentication failed:', error)
        // Continue anyway - user might already be authenticated via token
      })
  } else {
    console.warn('⚠️ Telegram Web App detected but no initData available')
  }
}

const app = createApp(App)
app.use(router)
app.mount('#app')

