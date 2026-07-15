<template>
  <div class="admin-root">
    <header class="admin-header">
      <div>
        <h1>Lottery Admin</h1>
        <p class="sub">Getachew Fikadu Jirata — configurables</p>
      </div>
      <div class="header-actions">
        <button v-if="!loggedIn" type="button" class="btn" @click="showLogin = true">Login</button>
        <button v-else type="button" class="btn ghost" @click="logout">Logged in</button>
      </div>
    </header>

    <div v-if="unauthorized" class="banner error">
      Please log in with a staff account to edit settings.
      <button type="button" class="linkish" @click="showLogin = true">Login</button>
    </div>
    <div v-if="message" class="banner ok">{{ message }}</div>
    <div v-if="error" class="banner error">{{ error }}</div>

    <form v-if="loggedIn" class="panel" @submit.prevent="save">
      <section>
        <h2>1. Branding</h2>
        <label>
          App name (after trophy / header)
          <input v-model="form.brand_name" type="text" required />
        </label>
        <label>
          Checkout / ticket display name
          <input v-model="form.display_name" type="text" />
        </label>
      </section>

      <section>
        <h2>2. Car</h2>
        <label>
          Car name
          <input v-model="form.car_name" type="text" required />
        </label>
        <label>
          Color / trim label
          <input v-model="form.car_color" type="text" required />
        </label>
        <label>
          Image URL (used if no upload)
          <input v-model="form.car_image_url_raw" type="url" />
        </label>
        <label>
          Or upload car photo
          <input type="file" accept="image/*" @change="onFile" />
        </label>
        <div v-if="previewUrl" class="preview">
          <img :src="previewUrl" alt="Car preview" />
        </div>
      </section>

      <section>
        <h2>3. Countdown timer</h2>
        <p class="hint">
          Saving with these values restarts the live countdown from now + the duration below.
        </p>
        <div class="timer-grid">
          <label>Days <input v-model.number="form.countdown_days" type="number" min="0" /></label>
          <label>Hours <input v-model.number="form.countdown_hours" type="number" min="0" max="23" /></label>
          <label>Minutes <input v-model.number="form.countdown_minutes" type="number" min="0" max="59" /></label>
          <label>Seconds <input v-model.number="form.countdown_seconds" type="number" min="0" max="59" /></label>
        </div>
        <p v-if="form.ends_at" class="hint">Current end: {{ form.ends_at }}</p>
        <label class="check">
          <input v-model="resetTimer" type="checkbox" />
          Force restart timer on this save (even if duration unchanged)
        </label>
      </section>

      <section>
        <h2>4. Tickets</h2>
        <div class="timer-grid">
          <label>Ticket price (Birr) <input v-model.number="form.ticket_price" type="number" min="1" /></label>
          <label>Total tickets <input v-model.number="form.total_tickets" type="number" min="1" /></label>
          <label>Sold count <input v-model.number="form.sold_count" type="number" min="0" /></label>
        </div>
      </section>

      <section>
        <h2>5. Payment accounts</h2>
        <p class="hint">Shown in checkout step 2.</p>
        <div v-for="(acc, idx) in form.payment_accounts" :key="idx" class="account-card">
          <label>Bank / method <input v-model="acc.name" type="text" /></label>
          <label>Account holder <input v-model="acc.holder" type="text" /></label>
          <label>Account number <input v-model="acc.account" type="text" /></label>
          <button type="button" class="btn ghost danger" @click="removeAccount(idx)">Remove</button>
        </div>
        <button type="button" class="btn ghost" @click="addAccount">+ Add account</button>
      </section>

      <div class="actions">
        <button type="submit" class="btn primary" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save settings' }}
        </button>
        <button type="button" class="btn ghost" :disabled="loading" @click="load">Reload</button>
      </div>
    </form>

    <div v-else class="panel empty">
      <p>Log in to configure the lottery mini-app.</p>
      <button type="button" class="btn primary" @click="showLogin = true">Admin login</button>
    </div>

    <div v-if="showLogin" class="modal" @click.self="showLogin = false">
      <form class="modal-card" @submit.prevent="doLogin">
        <h3>Staff login</h3>
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
import { adminDashboardLogin, getLotterySettingsAdmin, updateLotterySettingsAdmin } from '../services/api'

export default {
  name: 'AdminDashboard',
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
      form: {
        brand_name: 'Getachew Fikadu',
        display_name: 'Gech EV Makina Ekub',
        car_name: 'BYD Yuan UP',
        car_color: 'Time Grey',
        car_image_url: '',
        car_image_url_raw: '',
        ticket_price: 3000,
        total_tickets: 3500,
        sold_count: 397,
        countdown_days: 12,
        countdown_hours: 10,
        countdown_minutes: 24,
        countdown_seconds: 45,
        ends_at: '',
        payment_accounts: [],
      },
    }
  },
  computed: {
    previewUrl() {
      if (this.file) return URL.createObjectURL(this.file)
      return this.form.car_image_url || this.form.car_image_url_raw || ''
    },
  },
  mounted() {
    this.load()
  },
  methods: {
    async doLogin() {
      this.error = ''
      try {
        await adminDashboardLogin(this.loginUser, this.loginPass)
        this.loggedIn = true
        this.unauthorized = false
        this.showLogin = false
        await this.load()
      } catch (e) {
        this.error = e.response?.data?.error || 'Login failed'
      }
    },
    logout() {
      this.loggedIn = false
    },
    onFile(e) {
      this.file = e.target.files?.[0] || null
    },
    addAccount() {
      this.form.payment_accounts.push({
        id: `acc-${Date.now()}`,
        name: '',
        holder: '',
        account: '',
      })
    },
    removeAccount(idx) {
      this.form.payment_accounts.splice(idx, 1)
    },
    applyData(data) {
      this.form = {
        brand_name: data.brand_name || '',
        display_name: data.display_name || '',
        car_name: data.car_name || '',
        car_color: data.car_color || '',
        car_image_url: data.car_image_url || '',
        car_image_url_raw: data.car_image_url_raw || data.car_image_url || '',
        ticket_price: data.ticket_price ?? 3000,
        total_tickets: data.total_tickets ?? 3500,
        sold_count: data.sold_count ?? 0,
        countdown_days: data.countdown_days ?? 0,
        countdown_hours: data.countdown_hours ?? 0,
        countdown_minutes: data.countdown_minutes ?? 0,
        countdown_seconds: data.countdown_seconds ?? 0,
        ends_at: data.ends_at || '',
        payment_accounts: Array.isArray(data.payment_accounts)
          ? data.payment_accounts.map((a) => ({ ...a }))
          : [],
      }
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
      } catch (e) {
        if (e.response?.status === 401) {
          this.unauthorized = true
          this.loggedIn = false
        } else {
          this.error = e.response?.data?.error || 'Could not load settings'
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
          car_image_url: this.form.car_image_url_raw,
          ticket_price: this.form.ticket_price,
          total_tickets: this.form.total_tickets,
          sold_count: this.form.sold_count,
          countdown_days: this.form.countdown_days,
          countdown_hours: this.form.countdown_hours,
          countdown_minutes: this.form.countdown_minutes,
          countdown_seconds: this.form.countdown_seconds,
          payment_accounts: this.form.payment_accounts,
          reset_timer: this.resetTimer,
        }
        const res = await updateLotterySettingsAdmin(payload, this.file)
        this.applyData(res.settings || res)
        this.file = null
        this.resetTimer = false
        this.message = 'Settings saved. Mini-app will use the new values.'
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
  max-width: 820px;
  margin: 0 auto;
}
.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #f5a623;
}
.sub {
  margin: 0.25rem 0 0;
  color: #9ca3af;
  font-size: 0.875rem;
}
.panel {
  background: #161a22;
  border: 1px solid #2a3140;
  border-radius: 16px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.panel.empty {
  text-align: center;
  padding: 3rem 1rem;
}
section h2 {
  margin: 0 0 0.75rem;
  font-size: 1.05rem;
  color: #f5a623;
}
label {
  display: block;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  color: #d1d5db;
}
input[type='text'],
input[type='url'],
input[type='number'],
input[type='password'] {
  display: block;
  width: 100%;
  margin-top: 0.35rem;
  padding: 0.65rem 0.75rem;
  border-radius: 10px;
  border: 1px solid #334155;
  background: #0d0d0d;
  color: #fff;
  box-sizing: border-box;
}
.timer-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}
@media (min-width: 640px) {
  .timer-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
.hint {
  font-size: 0.8rem;
  color: #9ca3af;
  margin: 0 0 0.75rem;
}
.check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.account-card {
  border: 1px solid #2a3140;
  border-radius: 12px;
  padding: 0.85rem;
  margin-bottom: 0.75rem;
  background: #0d0d0d;
}
.preview img {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border-radius: 12px;
  margin-top: 0.5rem;
}
.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.btn {
  border: none;
  border-radius: 10px;
  padding: 0.7rem 1rem;
  font-weight: 600;
  cursor: pointer;
  background: #374151;
  color: #fff;
}
.btn.primary {
  background: linear-gradient(90deg, #f5a623, #ffb84d);
  color: #111;
}
.btn.ghost {
  background: transparent;
  border: 1px solid #4b5563;
}
.btn.danger {
  color: #fca5a5;
  border-color: #7f1d1d;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.banner {
  padding: 0.75rem 1rem;
  border-radius: 10px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}
.banner.ok {
  background: #052e1a;
  border: 1px solid #1e8e5a;
  color: #86efac;
}
.banner.error {
  background: #3f1515;
  border: 1px solid #7f1d1d;
  color: #fecaca;
}
.linkish {
  background: none;
  border: none;
  color: #f5a623;
  text-decoration: underline;
  cursor: pointer;
  margin-left: 0.5rem;
}
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 50;
}
.modal-card {
  width: 100%;
  max-width: 380px;
  background: #161a22;
  border: 1px solid #2a3140;
  border-radius: 16px;
  padding: 1.25rem;
}
.modal-card h3 {
  margin: 0 0 1rem;
  color: #f5a623;
}
</style>
