import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { initTelegramWebApp, getInitData } from './services/telegram'
import { registerTelegram } from './services/api'
import './style.css'

import LotteryLayout from './views/lottery/LotteryLayout.vue'
import HomeView from './views/lottery/HomeView.vue'
import RaffleDetailView from './views/lottery/RaffleDetailView.vue'
import TicketsView from './views/lottery/TicketsView.vue'
import ProfileView from './views/lottery/ProfileView.vue'
import AdminDashboard from './views/AdminDashboard.vue'
import SecondAdminDashboard from './views/SecondAdminDashboard.vue'
import SecondAdminLogin from './views/SecondAdminLogin.vue'

const routes = [
  {
    path: '/',
    component: LotteryLayout,
    children: [
      { path: '', name: 'home', component: HomeView },
      { path: 'raffle/:id', name: 'raffle-detail', component: RaffleDetailView },
      { path: 'tickets', name: 'tickets', component: TicketsView },
      { path: 'profile', name: 'profile', component: ProfileView },
    ],
  },
  { path: '/admin-dashboard', name: 'admin-dashboard', component: AdminDashboard },
  { path: '/secondadmin', name: 'second-admin-dashboard', component: SecondAdminDashboard },
  { path: '/secondadmin/login', name: 'second-admin-login', component: SecondAdminLogin },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

const isTelegramApp = initTelegramWebApp()

if (isTelegramApp) {
  const initData = getInitData()
  if (initData && typeof initData === 'string' && initData.length > 0) {
    registerTelegram(initData)
      .then(async (data) => {
        console.log('Telegram authentication successful:', data.user_id)
        const { store, loadUserProfile } = await import('./stores/lottery')
        if (data.user?.phone_number) {
          store.phone = String(data.user.phone_number).replace(/\D/g, '')
        }
        if (data.user && !data.user.phone_number) {
          try {
            const { getInitDataRaw } = await import('./services/telegram')
            const initDataRaw = getInitDataRaw()
            if (initDataRaw?.user?.phone_number) {
              const { updateUserPhone } = await import('./services/api')
              await updateUserPhone(initDataRaw.user.phone_number)
              store.phone = String(initDataRaw.user.phone_number).replace(/\D/g, '')
            }
          } catch (error) {
            console.warn('Phone number retrieval failed:', error)
          }
        }
        await loadUserProfile()
      })
      .catch((error) => {
        console.error('Telegram authentication failed:', error)
      })
  }
}

const app = createApp(App)
app.use(router)
app.mount('#app')
