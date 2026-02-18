<template>
  <div class="admin-dashboard">
    <div class="dashboard-header">
      <h1>Admin Dashboard</h1>
      <span v-if="data && lastUpdated" class="last-updated">Last updated: {{ lastUpdated }}</span>
      <button class="refresh-btn" @click="refreshData">🔄 Refresh</button>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="data">
      <!-- Statistics -->
      <section class="section">
        <h2>📊 Statistics</h2>
        <div class="stats-grid">
          <div class="stats-card games">
            <h3>Games Played</h3>
            <p class="stat-line"><strong>Today:</strong> {{ data.games_today || 0 }} <span class="muted">({{ data.date_today || '' }})</span></p>
            <p class="stat-line"><strong>Yesterday:</strong> {{ data.games_yesterday || 0 }}</p>
            <p class="stat-line"><strong>This Week:</strong> {{ data.games_week || 0 }}</p>
            <p class="stat-line"><strong>This Month:</strong> {{ data.games_month || 0 }}</p>
            <p class="stat-line"><strong>Total:</strong> {{ data.games_total || 0 }}</p>
          </div>
          <div class="stats-card revenue">
            <h3>Revenue</h3>
            <p class="stat-line"><strong>Today:</strong> {{ data.revenue_today_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>Yesterday:</strong> {{ data.revenue_yesterday_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>This Week:</strong> {{ data.revenue_week_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>This Month:</strong> {{ data.revenue_month_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>Total:</strong> {{ formatCurrency(data.revenue_total || 0) }}</p>
          </div>
        </div>
      </section>

      <!-- Game Mode Statistics -->
      <section class="section">
        <h2>🎮 Game Mode</h2>
        <div class="stats-grid three-cols">
          <div class="stats-card auto">
            <h3>🤖 Automatic</h3>
            <p class="stat-value">{{ data.total_automatic_games || 0 }}</p>
          </div>
          <div class="stats-card manual">
            <h3>✋ Manual</h3>
            <p class="stat-value">{{ data.total_manual_games || 0 }}</p>
          </div>
          <div class="stats-card total-cards">
            <h3>📊 Total Cards</h3>
            <p class="stat-value">{{ (data.total_automatic_games || 0) + (data.total_manual_games || 0) }}</p>
          </div>
        </div>
      </section>

      <!-- Financial -->
      <section class="section">
        <h2>💰 Financial</h2>
        <div class="stats-grid three-cols">
          <div class="stats-card deposits">
            <h3>💵 Total Deposits</h3>
            <p class="stat-value">{{ formatCurrency(data.total_deposits || 0) }}</p>
          </div>
          <div class="stats-card withdrawals">
            <h3>💸 Total Withdrawals</h3>
            <p class="stat-value">{{ formatCurrency(data.total_withdrawals || 0) }}</p>
          </div>
          <div class="stats-card balance">
            <h3>💳 Total Balance</h3>
            <p class="stat-value">{{ formatCurrency(data.total_balance || 0) }}</p>
          </div>
        </div>
      </section>

      <!-- Search User -->
      <section class="section">
        <h2>🔍 Search User</h2>
        <div class="search-row">
          <input v-model="searchQuery" type="text" placeholder="Enter phone number" class="search-input" @keyup.enter="doSearchUser" />
          <button class="btn btn-primary" @click="doSearchUser">Search</button>
        </div>
        <div v-if="searchResult" class="user-detail">
          <pre>{{ searchResult }}</pre>
        </div>
      </section>

      <!-- Deposits & Withdrawals -->
      <section class="section">
        <div class="section-header">
          <h2>💰💸 Deposits & Withdrawals</h2>
          <button class="btn btn-secondary" @click="refreshDeposits">🔄 Refresh</button>
        </div>

        <h3>💰 Pending Deposits</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Amount</th>
                <th>Platform</th>
                <th>Text</th>
                <th>Photo</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in (data.pending_deposits || [])" :key="'pd-' + d.id">
                <td>{{ d.id }}</td>
                <td>{{ d.username }}</td>
                <td>{{ formatCurrency(d.amount) }}</td>
                <td>{{ d.platform }}</td>
                <td class="text-cell">{{ (d.deposit_text || '').slice(0, 30) }}{{ (d.deposit_text && d.deposit_text.length > 30) ? '…' : '' }}</td>
                <td>
                  <a v-if="d.photo_file_id" :href="depositPhotoUrl(d.id)" target="_blank" rel="noopener" class="link">📷 Photo</a>
                  <span v-else class="muted">—</span>
                </td>
                <td>{{ d.created_at }}</td>
                <td>
                  <button class="btn btn-approve" @click="approveDeposit(d.id)">Approve</button>
                  <button class="btn btn-reject" @click="rejectDeposit(d.id)">Decline</button>
                </td>
              </tr>
              <tr v-if="!(data.pending_deposits && data.pending_deposits.length)">
                <td colspan="8">No pending deposits</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3>✅ Approved Deposits</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>User</th><th>Amount</th><th>Platform</th><th>Created</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in (data.approved_deposits || [])" :key="'ad-' + d.id">
                <td>{{ d.id }}</td>
                <td>{{ d.username }}</td>
                <td>{{ formatCurrency(d.amount) }}</td>
                <td>{{ d.platform }}</td>
                <td>{{ d.created_at }}</td>
              </tr>
              <tr v-if="!(data.approved_deposits && data.approved_deposits.length)">
                <td colspan="5">No approved deposits</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3>💸 Pending Withdraws</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th><th>User</th><th>Amount</th><th>Platform</th><th>Account Name</th><th>Account #</th><th>Created</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in (data.pending_withdraws || [])" :key="'pw-' + w.id">
                <td>{{ w.id }}</td>
                <td>{{ w.username }}</td>
                <td>{{ formatCurrency(w.amount) }}</td>
                <td>{{ w.platform }}</td>
                <td>{{ w.account_holder_name }}</td>
                <td>{{ w.account_number }}</td>
                <td>{{ w.created_at }}</td>
                <td>
                  <button class="btn btn-approve" @click="approveWithdraw(w.id)">Approve</button>
                  <button class="btn btn-reject" @click="rejectWithdraw(w.id)">Decline</button>
                </td>
              </tr>
              <tr v-if="!(data.pending_withdraws && data.pending_withdraws.length)">
                <td colspan="8">No pending withdraws</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3>✅ Approved Withdraws</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>User</th><th>Amount</th><th>Platform</th><th>Account Name</th><th>Created</th></tr>
            </thead>
            <tbody>
              <tr v-for="w in (data.approved_withdraws || [])" :key="'aw-' + w.id">
                <td>{{ w.id }}</td>
                <td>{{ w.username }}</td>
                <td>{{ formatCurrency(w.amount) }}</td>
                <td>{{ w.platform }}</td>
                <td>{{ w.account_holder_name }}</td>
                <td>{{ w.created_at }}</td>
              </tr>
              <tr v-if="!(data.approved_withdraws && data.approved_withdraws.length)">
                <td colspan="6">No approved withdraws</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Active Games -->
      <section class="section">
        <h2>🎯 Active Games</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>Status</th><th>Players</th><th>Derash</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in (data.active_games || [])" :key="'ag-' + g.id">
                <td>{{ g.id }}</td>
                <td>{{ g.status }}</td>
                <td>{{ g.players }}</td>
                <td>{{ formatCurrency(g.derash_amount) }}</td>
              </tr>
              <tr v-if="!(data.active_games && data.active_games.length)">
                <td colspan="4">No active games</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Today's Games -->
      <section class="section">
        <h2>📅 Today's Games</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>Time</th><th>Players</th><th>Bid</th><th>Real</th><th>System</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in (data.today_games || [])" :key="'tg-' + g.id">
                <td>{{ g.id }}</td>
                <td>{{ g.created_at }}</td>
                <td>{{ g.players }}</td>
                <td>{{ formatCurrency(g.bid_amount) }}</td>
                <td>{{ g.real_users }}</td>
                <td>{{ g.system_users }}</td>
                <td>{{ g.status }}</td>
              </tr>
              <tr v-if="!(data.today_games && data.today_games.length)">
                <td colspan="7">No games today</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Registered Users -->
      <section class="section">
        <h2>👥 Registered Users</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th><th>Username</th><th>Phone</th><th>Balance</th><th>Games</th><th>Wins</th><th>Deposits</th><th>Withdrawals</th><th>Joined</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in (data.registered_users || [])" :key="'u-' + u.id">
                <td>{{ u.id }}</td>
                <td>{{ u.username }}</td>
                <td>{{ u.phone_number }}</td>
                <td>{{ formatCurrency(u.balance) }}</td>
                <td>{{ u.games_played }}</td>
                <td>{{ u.wins }}</td>
                <td>{{ formatCurrency(u.total_deposits) }}</td>
                <td>{{ formatCurrency(u.total_withdrawals) }}</td>
                <td>{{ u.created_at }}</td>
              </tr>
              <tr v-if="!(data.registered_users && data.registered_users.length)">
                <td colspan="9">No registered users</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Game Settings -->
      <section class="section">
        <h2>⚙️ Game Settings</h2>
        <div v-if="settingsLoading" class="muted">Loading settings...</div>
        <div v-else class="settings-form">
          <div class="form-grid">
            <div class="form-group">
              <label>Bid Amount (ETB)</label>
              <input v-model.number="settings.bid_amount" type="number" step="0.01" min="0" />
            </div>
            <div class="form-group">
              <label>Card Selection Timer (sec)</label>
              <input v-model.number="settings.card_selection_timer" type="number" min="10" />
            </div>
            <div class="form-group">
              <label>Time Between Calls (sec)</label>
              <input v-model.number="settings.time_between_calls" type="number" min="1" />
            </div>
            <div class="form-group">
              <label>Total Cards</label>
              <input v-model.number="settings.total_cards" type="number" min="2" />
            </div>
            <div class="form-group">
              <label>Min Withdraw (ETB)</label>
              <input v-model.number="settings.min_withdraw" type="number" step="0.01" min="0" />
            </div>
            <div class="form-group">
              <label>Percentage Cut (%)</label>
              <input v-model.number="settings.percentage_cut" type="number" step="0.01" min="0" max="100" />
            </div>
            <div class="form-group checkbox">
              <label><input v-model="settings.automatic_mode_enabled" type="checkbox" /> Automatic mode enabled</label>
            </div>
            <div class="form-group checkbox">
              <label><input v-model="settings.allow_system_account" type="checkbox" /> Allow system account</label>
            </div>
            <div class="form-group checkbox">
              <label><input v-model="settings.free_play" type="checkbox" :disabled="!settings.allow_system_account" /> Free play</label>
            </div>
            <div class="form-group">
              <label>System accounts min</label>
              <input v-model.number="settings.system_accounts_min" type="number" min="1" max="100" />
            </div>
            <div class="form-group">
              <label>System accounts max</label>
              <input v-model.number="settings.system_accounts_max" type="number" min="1" max="100" />
            </div>
          </div>
          <button class="btn btn-primary" :disabled="settingsSaving" @click="saveSettings">{{ settingsSaving ? 'Saving…' : 'Save Settings' }}</button>
          <span v-if="settingsMessage" class="settings-msg" :class="settingsError ? 'error' : ''">{{ settingsMessage }}</span>
        </div>
      </section>
    </template>
  </div>
</template>

<script>
import {
  getAdminDashboardData,
  refreshDepositsWithdrawals,
  searchUser as apiSearchUser,
  approveDeposit as apiApproveDeposit,
  rejectDeposit as apiRejectDeposit,
  approveWithdraw as apiApproveWithdraw,
  rejectWithdraw as apiRejectWithdraw,
  getGameSettings,
  updateGameSettings
} from '../services/api'

export default {
  name: 'AdminDashboard',
  data() {
    return {
      data: null,
      loading: true,
      error: null,
      lastUpdated: null,
      searchQuery: '',
      searchResult: null,
      settings: {
        bid_amount: 10,
        card_selection_timer: 60,
        time_between_calls: 3,
        total_cards: 100,
        min_withdraw: 10,
        percentage_cut: 10,
        automatic_mode_enabled: true,
        allow_system_account: true,
        free_play: false,
        system_accounts_min: 15,
        system_accounts_max: 30
      },
      settingsLoading: false,
      settingsSaving: false,
      settingsMessage: '',
      settingsError: false
    }
  },
  async mounted() {
    await this.loadData()
    await this.loadSettings()
  },
  methods: {
    async loadData() {
      this.loading = true
      this.error = null
      try {
        this.data = await getAdminDashboardData()
        this.lastUpdated = new Date().toLocaleString()
      } catch (err) {
        console.error('Error loading admin dashboard:', err)
        this.error = err.response?.data?.error || err.response?.data?.message || 'Failed to load dashboard'
      } finally {
        this.loading = false
      }
    },
    async refreshData() {
      await this.loadData()
    },
    async refreshDeposits() {
      try {
        await refreshDepositsWithdrawals()
        await this.loadData()
      } catch (err) {
        console.error('Refresh deposits failed:', err)
      }
    },
    formatCurrency(value) {
      return new Intl.NumberFormat('en-ET', {
        style: 'currency',
        currency: 'ETB',
        minimumFractionDigits: 2
      }).format(Number(value) || 0)
    },
    depositPhotoUrl(id) {
      const base = window.location.origin
      return `${base}/admin-dashboard/deposits/${id}/photo/`
    },
    async doSearchUser() {
      if (!this.searchQuery.trim()) return
      this.searchResult = null
      try {
        const res = await apiSearchUser(this.searchQuery.trim())
        this.searchResult = typeof res === 'object' ? JSON.stringify(res, null, 2) : res
      } catch (err) {
        this.searchResult = 'Error: ' + (err.response?.data?.error || err.message || 'Search failed')
      }
    },
    async approveDeposit(id) {
      try {
        await apiApproveDeposit(id)
        await this.loadData()
      } catch (err) {
        console.error('Approve deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to approve')
      }
    },
    async rejectDeposit(id) {
      if (!confirm('Reject this deposit?')) return
      try {
        await apiRejectDeposit(id)
        await this.loadData()
      } catch (err) {
        console.error('Reject deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to reject')
      }
    },
    async approveWithdraw(id) {
      try {
        await apiApproveWithdraw(id)
        await this.loadData()
      } catch (err) {
        console.error('Approve withdraw failed:', err)
        alert(err.response?.data?.error || 'Failed to approve')
      }
    },
    async rejectWithdraw(id) {
      if (!confirm('Reject this withdrawal?')) return
      try {
        await apiRejectWithdraw(id)
        await this.loadData()
      } catch (err) {
        console.error('Reject withdraw failed:', err)
        alert(err.response?.data?.error || 'Failed to reject')
      }
    },
    async loadSettings() {
      this.settingsLoading = true
      try {
        const s = await getGameSettings()
        this.settings = { ...this.settings, ...s }
      } catch (err) {
        console.error('Load settings failed:', err)
      } finally {
        this.settingsLoading = false
      }
    },
    async saveSettings() {
      this.settingsSaving = true
      this.settingsMessage = ''
      this.settingsError = false
      try {
        await updateGameSettings(this.settings)
        this.settingsMessage = 'Settings saved.'
      } catch (err) {
        this.settingsError = true
        this.settingsMessage = err.response?.data?.error || err.message || 'Save failed'
      } finally {
        this.settingsSaving = false
      }
    }
  }
}
</script>

<style scoped>
.admin-dashboard {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
  background: #f5f5f5;
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.dashboard-header h1 {
  margin: 0;
  color: #2c3e50;
}

.last-updated {
  font-size: 12px;
  color: #666;
  margin-left: auto;
}

.refresh-btn {
  padding: 10px 20px;
  background: #6c3483;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}

.refresh-btn:hover {
  background: #5a2d6e;
}

.loading, .error {
  text-align: center;
  padding: 40px;
  font-size: 18px;
}

.error {
  color: #c0392b;
}

.section {
  background: white;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  margin-bottom: 24px;
}

.section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  color: #2c3e50;
}

.section h3 {
  margin: 20px 0 10px 0;
  font-size: 15px;
  color: #34495e;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.section-header h2 { margin-bottom: 0; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.stats-grid.three-cols {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.stats-card {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid #6c3483;
}

.stats-card.games { background: #e8f5e9; border-left-color: #2e7d32; }
.stats-card.revenue { background: #fff3e0; border-left-color: #e65100; }
.stats-card.auto { background: #e3f2fd; border-left-color: #1976d2; }
.stats-card.manual { background: #fff3e0; border-left-color: #f57c00; }
.stats-card.total-cards { background: #f3e5f5; border-left-color: #7b1fa2; }
.stats-card.deposits { background: #e8f5e9; border-left-color: #2e7d32; }
.stats-card.withdrawals { background: #ffebee; border-left-color: #c62828; }
.stats-card.balance { background: #e3f2fd; border-left-color: #1565c0; }

.stats-card h3 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #333;
}

.stat-line {
  margin: 4px 0;
  font-size: 14px;
}

.stat-value {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #2c3e50;
}

.muted { color: #888; font-size: 12px; }

.search-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.search-input {
  padding: 10px 12px;
  width: 280px;
  max-width: 100%;
  border: 1px solid #ddd;
  border-radius: 6px;
}

.user-detail {
  background: #f9f9f9;
  padding: 12px;
  border-radius: 6px;
  overflow: auto;
}

.user-detail pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
}

.table-wrap {
  overflow-x: auto;
  margin-bottom: 16px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.data-table th {
  background: #6c3483;
  color: white;
  font-weight: 600;
}

.data-table .text-cell { max-width: 120px; }

.btn {
  padding: 6px 12px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
}

.btn-primary { background: #27ae60; color: white; }
.btn-primary:hover { background: #219a52; }
.btn-secondary { background: #3498db; color: white; }
.btn-secondary:hover { background: #2980b9; }
.btn-approve { background: #2ecc71; color: white; margin-right: 6px; }
.btn-reject { background: #e74c3c; color: white; }

.link { color: #3498db; text-decoration: none; }
.link:hover { text-decoration: underline; }

.settings-form { background: #fafafa; padding: 16px; border-radius: 8px; }
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
.form-group label { display: block; margin-bottom: 4px; font-size: 13px; font-weight: 500; }
.form-group input[type="number"],
.form-group input[type="text"] {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 5px;
}
.form-group.checkbox label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.form-group.checkbox input { width: auto; }
.settings-msg { margin-left: 12px; font-size: 14px; }
.settings-msg.error { color: #c0392b; }

@media (max-width: 768px) {
  .admin-dashboard { padding: 12px; }
  .data-table th, .data-table td { padding: 6px 8px; font-size: 12px; }
  .stats-grid { grid-template-columns: 1fr; }
}
</style>
