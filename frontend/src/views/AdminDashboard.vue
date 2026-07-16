<template>
  <div class="admin-root">
    <header class="admin-header">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p class="sub">{{ pageSubtitle }}</p>
      </div>
      <div class="header-actions">
        <button v-if="!loggedIn" type="button" class="btn" @click="showLogin = true">Login</button>
        <template v-else>
          <div class="rev-block">
            <select v-model="revenuePeriod" class="period-select" @change="loadPurchases" title="Revenue period">
              <option value="today">Today</option>
              <option value="yesterday">Yesterday</option>
              <option value="this_week">This week</option>
              <option value="last_week">Last week</option>
              <option value="this_month">This month</option>
              <option value="last_month">Last month</option>
            </select>
            <span class="rev">{{ revenuePeriodLabel }}: <strong>{{ formatMoney(revenueAmount) }} Birr</strong>
              <span class="rev-count">· {{ revenueCount }} verified</span>
            </span>
          </div>
          <button type="button" class="btn ghost" @click="logout">Logout</button>
        </template>
      </div>
    </header>

    <div v-if="unauthorized" class="banner error">
      Please log in to continue.
      <button type="button" class="linkish" @click="showLogin = true">Login</button>
    </div>
    <div v-if="message" class="banner ok">{{ message }}</div>
    <div v-if="error" class="banner error">{{ error }}</div>

    <nav v-if="loggedIn" class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :class="{ active: activeTab === tab.id }"
        @click="switchTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- SETTINGS -->
    <form v-if="loggedIn && activeTab === 'settings'" class="panel" @submit.prevent="save">
      <section>
        <h2>Branding & car</h2>
        <label>Brand name <input v-model="form.brand_name" type="text" required /></label>
        <label>Display name <input v-model="form.display_name" type="text" /></label>
        <label>Car name <input v-model="form.car_name" type="text" required /></label>
        <label>Color label <input v-model="form.car_color" type="text" required /></label>
        <label>Image URL <input v-model="form.car_image_url_raw" type="text" /></label>
        <label>Upload photo <input ref="fileInput" type="file" accept="image/*" @change="onFile" /></label>
        <div v-if="previewUrl" class="preview"><img :src="previewUrl" alt="preview" /></div>
        <p v-if="form.car_image_url" class="hint">Live image URL: {{ form.car_image_url }}</p>
      </section>

      <section>
        <h2>Countdown</h2>
        <div class="timer-grid">
          <label>Days <input v-model.number="form.countdown_days" type="number" min="0" /></label>
          <label>Hours <input v-model.number="form.countdown_hours" type="number" min="0" /></label>
          <label>Minutes <input v-model.number="form.countdown_minutes" type="number" min="0" /></label>
          <label>Seconds <input v-model.number="form.countdown_seconds" type="number" min="0" /></label>
        </div>
        <label class="check"><input v-model="resetTimer" type="checkbox" /> Force restart timer</label>
      </section>

      <section>
        <h2>Tickets</h2>
        <div class="timer-grid">
          <label>Price <input v-model.number="form.ticket_price" type="number" min="1" /></label>
          <label>Total tickets <input v-model.number="form.total_tickets" type="number" min="1" /></label>
        </div>
      </section>

      <section>
        <h2>Payment accounts</h2>
        <div v-for="(acc, idx) in form.payment_accounts" :key="idx" class="account-card">
          <label>Bank <input v-model="acc.name" type="text" /></label>
          <label>Holder <input v-model="acc.holder" type="text" /></label>
          <label>Account # <input v-model="acc.account" type="text" /></label>
          <button type="button" class="btn ghost danger" @click="removeAccount(idx)">Remove</button>
        </div>
        <button type="button" class="btn ghost" @click="addAccount">+ Add account</button>
      </section>

      <div class="actions">
        <button type="submit" class="btn primary" :disabled="saving">{{ saving ? 'Saving…' : 'Save settings' }}</button>
        <button type="button" class="btn ghost" @click="load">Reload</button>
      </div>
    </form>

    <!-- NUMBERS -->
    <div v-if="loggedIn && activeTab === 'numbers'" class="panel">
      <h2>Admin taken / free numbers</h2>
      <p class="hint">All numbers are free by default. Paste taken numbers (comma/space separated). Verified user tickets stay taken automatically.</p>
      <textarea v-model="blockedText" rows="4" class="area" placeholder="e.g. 1, 2, 15, 61" />
      <p class="hint">Currently taken (admin + purchases): {{ form.taken_numbers?.length || 0 }}</p>
      <button type="button" class="btn primary" :disabled="saving" @click="saveBlocked">Save blocked numbers</button>
    </div>

    <!-- RECEIPTS -->
    <div v-if="loggedIn && activeTab === 'receipts'" class="panel">
      <div class="row-between">
        <h2>Receipts</h2>
        <span class="rev">{{ revenuePeriodLabel }}: {{ formatMoney(revenueAmount) }} Birr · {{ revenueCount }} verified</span>
      </div>
      <div class="filters">
        <select v-model="receiptStatus" @change="loadPurchases">
          <option value="pending">Pending</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
        </select>
        <select v-model="receiptPeriod" @change="loadPurchases" title="Receipt timeline">
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="this_week">This week</option>
          <option value="last_week">Last week</option>
          <option value="this_month">This month</option>
          <option value="last_month">Last month</option>
          <option value="all">All time</option>
        </select>
        <button type="button" class="btn ghost" @click="loadPurchases">Refresh</button>
      </div>
      <p class="hint">Pending: {{ pendingCount }} · Verified: {{ verifiedCount }}</p>

      <article v-for="p in purchases" :key="p.id" class="receipt-card">
        <div class="row-between">
          <div>
            <strong>{{ p.full_name }}</strong>
            <div class="muted">{{ p.phone }} · {{ p.created_at }}</div>
            <div>Numbers: <b>{{ (p.numbers || []).map(n => String(n).padStart(3,'0')).join(', ') }}</b></div>
            <div>{{ formatMoney(p.amount) }} Birr · {{ p.bank_name }} {{ p.bank_account }}</div>
          </div>
          <span class="badge" :class="p.status">{{ p.status }}</span>
        </div>
        <a v-if="p.receipt_image_url" :href="p.receipt_image_url" target="_blank" class="receipt-link">Open receipt image</a>
        <div v-if="p.status === 'pending'" class="actions">
          <button type="button" class="btn primary" @click="act(p.id, 'verify')">Verify</button>
          <button type="button" class="btn ghost danger" @click="act(p.id, 'reject')">Reject</button>
          <button type="button" class="btn ghost danger" @click="act(p.id, 'delete')">Delete</button>
        </div>
        <div v-else-if="p.status === 'verified' || p.status === 'rejected'" class="actions">
          <button type="button" class="btn ghost danger" @click="act(p.id, 'delete')">
            Delete (free numbers)
          </button>
        </div>
      </article>
      <p v-if="!purchases.length" class="hint">No receipts in this filter.</p>
    </div>

    <!-- USERS -->
    <div v-if="loggedIn && activeTab === 'users'" class="panel">
      <div class="row-between">
        <h2>Users</h2>
        <span class="hint">Showing {{ visibleUsers.length }} of {{ users.length }}</span>
      </div>
      <div class="filters">
        <input v-model="usersQuery" type="text" placeholder="Search phone / name / telegram id" @keyup.enter="loadUsers" />
        <button type="button" class="btn ghost" @click="loadUsers">{{ usersLoading ? '…' : 'Search' }}</button>
      </div>
      <article v-for="(u, idx) in visibleUsers" :key="u.id || ('g-' + idx)" class="receipt-card">
        <div class="row-between">
          <div>
            <strong>{{ u.first_name || u.username || 'User' }}</strong>
            <span v-if="u.is_guest" class="badge pending" style="margin-left:6px">guest</span>
            <div class="muted">{{ u.phone || '—' }} · tg: {{ u.telegram_id || '—' }} · {{ u.preferred_language || '—' }}</div>
            <div class="muted">Joined: {{ u.date_joined || '—' }}</div>
          </div>
          <div style="text-align:right">
            <div class="rev">{{ formatMoney(u.total_spent_verified) }} Birr</div>
            <div class="muted">{{ u.verified_purchases }} verified · {{ u.pending_purchases }} pending</div>
          </div>
        </div>
        <div v-if="u.verified_numbers?.length" class="nums-row">
          <span class="muted">Verified #:</span>
          <span v-for="n in u.verified_numbers" :key="'v'+n" class="num-chip">{{ String(n).padStart(3,'0') }}</span>
        </div>
        <div v-if="u.pending_numbers?.length" class="nums-row">
          <span class="muted">Pending #:</span>
          <span v-for="n in u.pending_numbers" :key="'p'+n" class="num-chip pending-chip">{{ String(n).padStart(3,'0') }}</span>
        </div>
        <p v-if="!u.verified_numbers?.length && !u.pending_numbers?.length" class="hint">No ticket numbers this round.</p>
        <div class="actions">
          <button type="button" class="btn ghost danger" @click="deleteUser(u)">Delete user</button>
        </div>
      </article>
      <p v-if="!users.length && !usersLoading" class="hint">No users found.</p>
      <div v-if="usersVisibleCount < users.length" class="actions">
        <button type="button" class="btn primary" @click="showMoreUsers">
          Show more ({{ Math.min(10, users.length - usersVisibleCount) }} more)
        </button>
      </div>
    </div>

    <!-- WINNER -->
    <div v-if="loggedIn && activeTab === 'winner'" class="panel">
      <h2>Announce winner</h2>
      <p class="hint">Use after the ticket deadline. Notifies verified ticket holders on Telegram.</p>
      <label>Winning number <input v-model="winnerNumber" type="text" placeholder="061" /></label>
      <label>Message <textarea v-model="winnerMessage" rows="3" class="area" placeholder="Congratulations to the winner!" /></label>
      <p v-if="form.winner_announced_at" class="hint">Last announced: #{{ form.winner_number }} at {{ form.winner_announced_at }}</p>
      <button type="button" class="btn primary" @click="announce">Announce winner</button>
    </div>

    <!-- ACCESS (main admin only) — create credentials for /admin-view -->
    <div v-if="loggedIn && isMain && activeTab === 'access'" class="panel">
      <h2>Admin View login</h2>
      <p class="hint">
        Credentials for
        <a class="receipt-link" :href="adminViewLoginUrl" target="_blank">{{ adminViewLoginUrl }}</a>
      </p>

      <div v-if="accessUser" class="account-card">
        <h2 style="margin-top:0">Stored credentials</h2>
        <p><span class="muted">Username:</span> <strong>{{ accessUser }}</strong></p>
        <p>
          <span class="muted">Password:</span>
          <strong>{{ accessStoredPassword || (accessHasPassword ? '(set — enter a new password below to replace)' : 'not set') }}</strong>
        </p>
        <p class="hint">Open: <a class="receipt-link" :href="adminViewUrl" target="_blank">{{ adminViewUrl }}</a></p>
      </div>

      <label>Username <input v-model="accessUser" type="text" autocomplete="off" /></label>
      <label>
        Password
        <input
          v-model="accessPass"
          type="text"
          autocomplete="off"
          :placeholder="accessHasPassword ? 'Leave blank to keep current password' : 'Set a password'"
        />
      </label>
      <div class="actions">
        <button type="button" class="btn primary" :disabled="accessSaving || !accessUser.trim()" @click="saveAccess">
          {{ accessSaving ? 'Saving…' : 'Save credentials' }}
        </button>
        <button type="button" class="btn ghost" @click="loadAccess">Reload</button>
      </div>
    </div>

    <div v-if="!loggedIn" class="panel empty">
      <p>Log in to manage the lottery.</p>
      <button type="button" class="btn primary" @click="showLogin = true">Admin login</button>
    </div>

    <div v-if="showLogin" class="modal" @click.self="showLogin = false">
      <form class="modal-card" @submit.prevent="doLogin">
        <h3>{{ isMain ? 'Staff login' : 'Admin login' }}</h3>
        <label>Username <input v-model="loginUser" type="text" autocomplete="username" /></label>
        <label>Password <input v-model="loginPass" type="password" autocomplete="current-password" /></label>
        <div class="actions">
          <button type="button" class="btn ghost" @click="showLogin = false">Cancel</button>
          <button type="submit" class="btn primary">Login</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script>
import {
  adminDashboardLogin,
  lotteryAdminBootstrap,
  getLotterySettingsAdmin,
  updateLotterySettingsAdmin,
  getLotteryPurchasesAdmin,
  lotteryPurchaseAction,
  announceLotteryWinner,
  getSecondAdminCredentials,
  saveSecondAdminCredentials,
  secondAdminLogin,
  secondAdminLogout,
  getLotteryUsersAdmin,
  deleteLotteryUser,
} from '../services/api'

export default {
  name: 'AdminDashboard',
  props: {
    /** 'main' = /admin-dashboard ; 'view' = /admin-view */
    variant: {
      type: String,
      default: 'main',
      validator: (v) => ['main', 'view'].includes(v),
    },
  },
  data() {
    return {
      loggedIn: false,
      unauthorized: false,
      showLogin: false,
      loginUser: '',
      loginPass: '',
      loading: false,
      saving: false,
      message: '',
      error: '',
      resetTimer: false,
      file: null,
      activeTab: 'settings',
      form: {
        brand_name: 'Getachew Fikadu',
        display_name: '',
        car_name: '',
        car_color: '',
        car_image_url: '',
        car_image_url_raw: '',
        ticket_price: 3000,
        total_tickets: 3500,
        countdown_days: 12,
        countdown_hours: 10,
        countdown_minutes: 24,
        countdown_seconds: 45,
        payment_accounts: [],
        admin_blocked_numbers: [],
        taken_numbers: [],
        winner_number: '',
        winner_announced_at: '',
      },
      blockedText: '',
      purchases: [],
      receiptStatus: 'pending',
      receiptPeriod: 'today',
      revenuePeriod: 'today',
      revenueAmount: 0,
      revenueCount: 0,
      pendingCount: 0,
      verifiedCount: 0,
      winnerNumber: '',
      winnerMessage: '',
      accessUser: '',
      accessPass: '',
      accessStoredPassword: '',
      accessHasPassword: false,
      accessSaving: false,
      users: [],
      usersQuery: '',
      usersLoading: false,
      usersVisibleCount: 10,
    }
  },
  computed: {
    isMain() {
      return this.variant !== 'view'
    },
    pageTitle() {
      return this.isMain ? 'Lottery Admin' : 'Admin View'
    },
    pageSubtitle() {
      return this.isMain
        ? 'Settings · receipts · numbers · users · winner · access'
        : 'Settings · receipts · numbers · users · winner'
    },
    revenuePeriodLabel() {
      const labels = {
        today: 'Today',
        yesterday: 'Yesterday',
        this_week: 'This week',
        last_week: 'Last week',
        this_month: 'This month',
        last_month: 'Last month',
      }
      return labels[this.revenuePeriod] || 'Revenue'
    },
    tabs() {
      const base = [
        { id: 'settings', label: 'Settings' },
        { id: 'numbers', label: 'Numbers' },
        { id: 'receipts', label: 'Receipts' },
        { id: 'users', label: 'Users' },
        { id: 'winner', label: 'Winner' },
      ]
      if (this.isMain) base.push({ id: 'access', label: 'Access' })
      return base
    },
    visibleUsers() {
      return (this.users || []).slice(0, this.usersVisibleCount)
    },
    previewUrl() {
      if (this.file) return URL.createObjectURL(this.file)
      return this.form.car_image_url || this.form.car_image_url_raw || ''
    },
    adminViewUrl() {
      if (typeof window === 'undefined') return '/admin-view'
      return `${window.location.origin}/admin-view`
    },
    adminViewLoginUrl() {
      return `${this.adminViewUrl}/login`
    },
  },
  mounted() {
    document.title = this.isMain ? 'Lottery Admin' : 'Admin View'
    this.init()
  },
  methods: {
    async init() {
      try {
        await lotteryAdminBootstrap()
      } catch (e) {
        console.warn('CSRF bootstrap failed', e)
      }
      await this.load()
    },
    formatMoney(n) {
      return Number(n || 0).toLocaleString('en-US')
    },
    switchTab(id) {
      this.activeTab = id
      if (id === 'receipts') this.loadPurchases()
      if (id === 'access') this.loadAccess()
      if (id === 'users') this.loadUsers()
    },
    async doLogin() {
      this.error = ''
      try {
        if (this.isMain) {
          await adminDashboardLogin(this.loginUser, this.loginPass)
        } else {
          await secondAdminLogin(this.loginUser, this.loginPass)
        }
        this.loggedIn = true
        this.unauthorized = false
        this.showLogin = false
        await this.load()
      } catch (e) {
        this.error = e.response?.data?.error || 'Login failed'
      }
    },
    async logout() {
      if (!this.isMain) {
        try {
          await secondAdminLogout()
        } catch (e) {
          /* still clear UI */
        }
      }
      this.loggedIn = false
      this.unauthorized = true
    },
    onFile(e) {
      this.file = e.target.files?.[0] || null
    },
    addAccount() {
      this.form.payment_accounts.push({ id: `acc-${Date.now()}`, name: '', holder: '', account: '' })
    },
    removeAccount(idx) {
      this.form.payment_accounts.splice(idx, 1)
    },
    applyData(data) {
      this.form = {
        ...this.form,
        brand_name: data.brand_name || '',
        display_name: data.display_name || '',
        car_name: data.car_name || '',
        car_color: data.car_color || '',
        car_image_url: data.car_image_url || '',
        car_image_url_raw: data.car_image_url_raw || '',
        ticket_price: data.ticket_price ?? 3000,
        total_tickets: data.total_tickets ?? 3500,
        countdown_days: data.countdown_days ?? 0,
        countdown_hours: data.countdown_hours ?? 0,
        countdown_minutes: data.countdown_minutes ?? 0,
        countdown_seconds: data.countdown_seconds ?? 0,
        payment_accounts: Array.isArray(data.payment_accounts)
          ? data.payment_accounts.map((a) => ({ ...a }))
          : [],
        admin_blocked_numbers: data.admin_blocked_numbers || [],
        taken_numbers: data.taken_numbers || [],
        winner_number: data.winner_number || '',
        winner_announced_at: data.winner_announced_at || '',
      }
      this.blockedText = (this.form.admin_blocked_numbers || []).join(', ')
      if (!this.form.payment_accounts.length) this.addAccount()
    },
    async load() {
      this.loading = true
      this.error = ''
      try {
        const data = await getLotterySettingsAdmin()
        this.applyData(data)
        this.loggedIn = true
        this.unauthorized = false
        await this.loadPurchases()
      } catch (e) {
        if (e.response?.status === 401) {
          this.unauthorized = true
          this.loggedIn = false
        } else {
          const msg = e.response?.data?.error || e.response?.data?.message || 'Could not load settings'
          this.error = msg.includes('Not found')
            ? `${msg} Run on EC2: git pull && bash scripts/rebuild_frontend.sh`
            : msg
        }
      } finally {
        this.loading = false
      }
    },
    async save() {
      this.saving = true
      this.message = ''
      this.error = ''
      try {
        const payload = {
          brand_name: this.form.brand_name,
          display_name: this.form.display_name,
          car_name: this.form.car_name,
          car_color: this.form.car_color,
          car_image_url: this.form.car_image_url_raw || '',
          ticket_price: this.form.ticket_price,
          total_tickets: this.form.total_tickets,
          countdown_days: this.form.countdown_days,
          countdown_hours: this.form.countdown_hours,
          countdown_minutes: this.form.countdown_minutes,
          countdown_seconds: this.form.countdown_seconds,
          payment_accounts: this.form.payment_accounts,
          admin_blocked_numbers: this.form.admin_blocked_numbers,
          reset_timer: this.resetTimer,
        }
        const res = await updateLotterySettingsAdmin(payload, this.file)
        this.applyData(res.settings || res)
        this.file = null
        this.resetTimer = false
        this.message = 'Settings saved. Open or refresh the mini-app Home tab to see updates.'
        if (this.$refs.fileInput) this.$refs.fileInput.value = ''
      } catch (e) {
        if (e.response?.status === 401) {
          this.unauthorized = true
          this.loggedIn = false
        }
        this.error = e.response?.data?.error || 'Save failed'
      } finally {
        this.saving = false
      }
    },
    async saveBlocked() {
      const nums = this.blockedText
        .split(/[\s,;]+/)
        .map((x) => parseInt(x, 10))
        .filter((n) => !Number.isNaN(n) && n > 0)
      this.form.admin_blocked_numbers = [...new Set(nums)]
      await this.save()
    },
    async loadPurchases() {
      try {
        const data = await getLotteryPurchasesAdmin({
          status: this.receiptStatus,
          period: this.receiptPeriod,
          revenue_period: this.revenuePeriod,
        })
        this.purchases = data.purchases || []
        this.revenueAmount = data.revenue_amount ?? data.revenue_today ?? 0
        this.revenueCount = data.revenue_count ?? data.verified_today_count ?? 0
        this.pendingCount = data.pending_count || 0
        this.verifiedCount = data.verified_count || 0
      } catch (e) {
        if (e.response?.status === 401) {
          this.unauthorized = true
          this.loggedIn = false
        } else if (e.response?.status === 404) {
          this.error = (e.response?.data?.error || 'Receipts API not found') + ' — deploy backend on EC2 first.'
        }
      }
    },
    async act(id, action) {
      this.error = ''
      if (action === 'delete') {
        if (!confirm('Delete this receipt request? Numbers will become free again.')) return
      }
      try {
        await lotteryPurchaseAction(id, action)
        this.message =
          action === 'verify'
            ? 'Verified — user notified.'
            : action === 'reject'
              ? 'Rejected.'
              : 'Deleted — numbers freed.'
        await this.loadPurchases()
        await this.load()
      } catch (e) {
        this.error = e.response?.data?.error || 'Action failed'
      }
    },
    async announce() {
      this.error = ''
      try {
        await announceLotteryWinner(this.winnerNumber, this.winnerMessage)
        this.message = 'Winner announced and users notified.'
        await this.load()
      } catch (e) {
        this.error = e.response?.data?.error || 'Announce failed'
      }
    },
    async loadUsers() {
      this.usersLoading = true
      this.usersVisibleCount = 10
      try {
        const data = await getLotteryUsersAdmin({ q: this.usersQuery || undefined })
        this.users = data.users || []
      } catch (e) {
        if (e.response?.status === 401) {
          this.unauthorized = true
          this.loggedIn = false
        } else {
          this.error = e.response?.data?.error || 'Could not load users'
        }
      } finally {
        this.usersLoading = false
      }
    },
    showMoreUsers() {
      this.usersVisibleCount = Math.min(this.users.length, this.usersVisibleCount + 10)
    },
    async deleteUser(u) {
      const label = u.first_name || u.username || u.phone || 'this user'
      if (!confirm(`Delete ${label}? Their lottery purchases will be removed and numbers freed.`)) return
      this.error = ''
      try {
        const payload = u.id ? { user_id: u.id } : { phone: u.phone }
        const res = await deleteLotteryUser(payload)
        this.message = `Deleted. Purchases removed: ${res.deleted_purchases || 0}`
        await this.loadUsers()
        await this.load()
      } catch (e) {
        this.error = e.response?.data?.error || 'Could not delete user'
      }
    },
    async loadAccess() {
      if (!this.isMain) return
      try {
        const data = await getSecondAdminCredentials()
        this.accessUser = data.username || ''
        this.accessStoredPassword = data.password || ''
        this.accessHasPassword = !!data.has_password
        this.accessPass = ''
      } catch (e) {
        this.error = e.response?.data?.error || 'Could not load Admin View credentials'
      }
    },
    async saveAccess() {
      if (!this.isMain) return
      this.accessSaving = true
      this.message = ''
      this.error = ''
      try {
        const res = await saveSecondAdminCredentials(this.accessUser.trim(), this.accessPass)
        this.message = 'Admin View credentials saved. Login at /admin-view'
        this.accessUser = res.username || this.accessUser
        this.accessStoredPassword = res.password || this.accessPass || this.accessStoredPassword
        this.accessHasPassword = !!res.has_password || !!this.accessStoredPassword
        this.accessPass = ''
        await this.loadAccess()
      } catch (e) {
        this.error = e.response?.data?.error || 'Could not save credentials'
      } finally {
        this.accessSaving = false
      }
    },
  },
}
</script>

<style scoped>
.admin-root {
  min-height: 100vh;
  background: #0f1115;
  color: #f3f4f6;
  font-family: 'Segoe UI', system-ui, sans-serif;
  padding: 1.25rem;
  max-width: 920px;
  margin: 0 auto;
}
.admin-header { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
h1 { margin: 0; font-size: 1.45rem; color: #f5a623; }
.sub { margin: 0.25rem 0 0; color: #9ca3af; font-size: 0.875rem; }
.rev { color: #86efac; font-size: 0.9rem; }
.rev-block { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.rev-count { opacity: 0.85; font-weight: 400; }
.period-select {
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 0.35rem 0.5rem;
  font-size: 0.85rem;
}
.tabs { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.tabs button {
  background: #1a1f2a; border: 1px solid #2a3140; color: #d1d5db;
  padding: 0.5rem 0.9rem; border-radius: 999px; cursor: pointer;
}
.tabs button.active { background: #f5a623; color: #111; border-color: #f5a623; font-weight: 700; }
.panel {
  background: #161a22; border: 1px solid #2a3140; border-radius: 16px;
  padding: 1.25rem; display: flex; flex-direction: column; gap: 1.25rem;
}
.panel.empty { text-align: center; padding: 3rem 1rem; }
section h2, .panel > h2 { margin: 0 0 0.5rem; font-size: 1.05rem; color: #f5a623; }
label { display: block; margin-bottom: 0.65rem; font-size: 0.85rem; color: #d1d5db; }
input[type='text'], input[type='url'], input[type='number'], input[type='password'], select, .area {
  display: block; width: 100%; margin-top: 0.35rem; padding: 0.65rem 0.75rem;
  border-radius: 10px; border: 1px solid #334155; background: #0d0d0d; color: #fff; box-sizing: border-box;
}
.area { resize: vertical; }
.timer-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
@media (min-width: 640px) { .timer-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.hint { font-size: 0.8rem; color: #9ca3af; margin: 0; }
.check { display: flex; align-items: center; gap: 0.5rem; }
.account-card, .receipt-card {
  border: 1px solid #2a3140; border-radius: 12px; padding: 0.85rem; background: #0d0d0d;
}
.preview img { width: 100%; max-height: 220px; object-fit: cover; border-radius: 12px; }
.actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.btn {
  border: none; border-radius: 10px; padding: 0.7rem 1rem; font-weight: 600; cursor: pointer;
  background: #374151; color: #fff;
}
.btn.primary { background: linear-gradient(90deg, #f5a623, #ffb84d); color: #111; }
.btn.ghost { background: transparent; border: 1px solid #4b5563; }
.btn.danger { color: #fca5a5; border-color: #7f1d1d; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.banner { padding: 0.75rem 1rem; border-radius: 10px; margin-bottom: 1rem; font-size: 0.9rem; }
.banner.ok { background: #052e1a; border: 1px solid #1e8e5a; color: #86efac; }
.banner.error { background: #3f1515; border: 1px solid #7f1d1d; color: #fecaca; }
.linkish { background: none; border: none; color: #f5a623; text-decoration: underline; cursor: pointer; }
.modal {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex;
  align-items: center; justify-content: center; padding: 1rem; z-index: 50;
}
.modal-card {
  width: 100%; max-width: 380px; background: #161a22; border: 1px solid #2a3140;
  border-radius: 16px; padding: 1.25rem;
}
.row-between { display: flex; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
.filters { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.muted { color: #9ca3af; font-size: 0.8rem; }
.badge { text-transform: uppercase; font-size: 0.7rem; font-weight: 700; padding: 0.25rem 0.5rem; border-radius: 6px; }
.badge.pending { background: #78350f; color: #fcd34d; }
.badge.verified { background: #064e3b; color: #6ee7b7; }
.badge.rejected { background: #7f1d1d; color: #fecaca; }
.receipt-link { color: #f5a623; font-size: 0.85rem; }
.nums-row { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; margin-top: 0.5rem; }
.num-chip {
  background: #064e3b; color: #6ee7b7; font-size: 0.75rem; font-weight: 700;
  padding: 0.2rem 0.45rem; border-radius: 6px;
}
.num-chip.pending-chip { background: #78350f; color: #fcd34d; }
</style>
