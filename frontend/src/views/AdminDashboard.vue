<template>
  <div class="admin-dashboard">
    <div class="dashboard-header">
      <h1>Admin Dashboard</h1>
      <span v-if="data && lastUpdated" class="last-updated">Last updated: {{ lastUpdated }}</span>
      <button type="button" class="admin-login-link" @click="showLoginForm = true" title="Log in with staff account">🔐 Admin Login</button>
      <button class="refresh-btn" @click="refreshData">🔄 Refresh</button>
    </div>

    <!-- Inline admin login form -->
    <div v-if="showLoginForm" class="inline-login-overlay" @click.self="showLoginForm = false">
      <div class="inline-login-box">
        <h3>Staff login</h3>
        <p class="inline-login-hint">Use your Django staff account.</p>
        <form @submit.prevent="doAdminLogin" class="inline-login-form">
          <div class="form-group">
            <label>Username</label>
            <input v-model="loginUsername" type="text" required autocomplete="username" />
          </div>
          <div class="form-group">
            <label>Password</label>
            <input v-model="loginPassword" type="password" required autocomplete="current-password" />
          </div>
          <p v-if="loginError" class="inline-login-error">{{ loginError }}</p>
          <div class="inline-login-actions">
            <button type="submit" class="btn btn-primary" :disabled="loginLoading">{{ loginLoading ? 'Logging in…' : 'Log in' }}</button>
            <button type="button" class="btn btn-secondary" @click="closeLoginForm">Cancel</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Unauthorized banner - show when user needs to log in -->
    <div v-if="unauthorized" class="unauthorized-banner">
      <strong>⚠️ Authentication required</strong>
      <p>Log in with your staff account using the <strong>Admin Login</strong> button above.</p>
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
            <p class="stat-line"><strong>Yesterday:</strong> {{ data.games_yesterday || 0 }} <span class="muted">({{ data.date_yesterday || '' }})</span></p>
            <p class="stat-line"><strong>This Week:</strong> {{ data.games_week || 0 }} <span class="muted">({{ data.date_week || '' }})</span></p>
            <p class="stat-line"><strong>Last Week:</strong> {{ data.games_last_week || 0 }} <span class="muted">({{ data.date_last_week || '' }})</span></p>
            <p class="stat-line"><strong>This Month:</strong> {{ data.games_month || 0 }} <span class="muted">({{ data.date_month || '' }})</span></p>
            <p class="stat-line"><strong>Last Month:</strong> {{ data.games_last_month || 0 }} <span class="muted">({{ data.date_last_month || '' }})</span></p>
            <p class="stat-line"><strong>Total:</strong> <a href="#" class="stat-link" @click.prevent="scrollToTodayGames">{{ data.games_total || 0 }}</a></p>
          </div>
          <div class="stats-card revenue">
            <h3>Revenue</h3>
            <p class="stat-line"><strong>Today:</strong> {{ data.revenue_today_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>Yesterday:</strong> {{ data.revenue_yesterday_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>This Week:</strong> {{ data.revenue_week_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>Last Week:</strong> {{ data.revenue_last_week_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>This Month:</strong> {{ data.revenue_month_formatted || '0' }} ETB</p>
            <p class="stat-line"><strong>Last Month:</strong> {{ data.revenue_last_month_formatted || '0' }} ETB</p>
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
          <input v-model="searchQuery" type="text" placeholder="Phone number or Telegram @username" class="search-input" @keyup.enter="doSearchUser" />
          <button class="btn btn-primary" @click="doSearchUser">Search</button>
        </div>
        <div v-if="searchResult" class="user-detail">
          <pre>{{ searchResult }}</pre>
        </div>
      </section>

      <!-- Search Transaction Number (CBE) -->
      <section class="section">
        <h2>🔎 Search Transaction Number</h2>
        <p class="section-hint">CBE: enter FT... (e.g. FT26048WBS7024627387). Telebirr: enter receipt reference (e.g. DBK10S886V). Same list as auto-verified and manual approvals.</p>
        <div class="search-row">
          <input v-model="searchTxQuery" type="text" placeholder="CBE: FT... or Telebirr ref" class="search-input" @keyup.enter="doSearchTransaction" />
          <button class="btn btn-primary" @click="doSearchTransaction">Search</button>
        </div>
        <div v-if="searchTxResult !== null" class="user-detail">
          <pre>{{ searchTxResult }}</pre>
          <div v-if="searchTxResultObj" class="search-tx-actions" style="margin-top: 10px;">
            <button v-if="searchTxResultObj.valid_format && !searchTxResultObj.found && searchTxResultObj.platform === 'CBE'" type="button" class="btn btn-primary" @click="addCbeReceiptRef">Add (save CBE ref to prevent reuse)</button>
            <button v-else-if="searchTxResultObj.valid_format && !searchTxResultObj.found && searchTxResultObj.platform === 'Telebirr'" type="button" class="btn btn-primary" @click="addTelebirrReceiptRef">Add (save Telebirr ref to prevent reuse)</button>
            <button v-else-if="searchTxResultObj.found && searchTxResultObj.platform === 'CBE'" type="button" class="btn btn-secondary" @click="deleteCbeReceiptRef">Delete (allow this CBE ref again)</button>
            <button v-else-if="searchTxResultObj.found && searchTxResultObj.platform === 'Telebirr'" type="button" class="btn btn-secondary" @click="deleteTelebirrReceiptRef">Delete (allow this Telebirr ref again)</button>
          </div>
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
                <td class="text-cell">
                  <span v-if="!expandedDepositText[d.id]">{{ (d.deposit_text || '').slice(0, 40) }}{{ (d.deposit_text && d.deposit_text.length > 40) ? '…' : '' }}</span>
                  <span v-else class="deposit-text-full">{{ d.deposit_text }}</span>
                  <button v-if="d.deposit_text && d.deposit_text.length > 40" type="button" class="link-btn" @click="toggleDepositText(d.id)">
                    {{ expandedDepositText[d.id] ? 'Show less' : 'Show more' }}
                  </button>
                </td>
                <td>
                  <button v-if="d.photo_file_id" type="button" class="link-btn" @click="showDepositPhoto(d.id)">📷 Photo</button>
                  <span v-else class="muted">—</span>
                </td>
                <td>{{ d.created_at }}</td>
                <td>
                  <button class="btn btn-approve" @click="approveDeposit(d.id, d.platform)">Approve</button>
                  <button class="btn btn-reject" @click="rejectDeposit(d.id)">Delete</button>
                </td>
              </tr>
              <tr v-if="!(data.pending_deposits && data.pending_deposits.length)">
                <td colspan="8">No pending deposits</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3>❌ Failed Deposit Requests</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th><th>User</th><th>Amount</th><th>Platform</th><th>Reason</th><th>Ref</th><th>Suffix</th><th>Created</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="fd in (data.failed_deposits || [])" :key="'fd-' + fd.id">
                <td>{{ fd.id }}</td>
                <td>{{ fd.username }}</td>
                <td>{{ fd.amount != null ? formatCurrency(fd.amount) : '—' }}</td>
                <td>{{ fd.platform }}</td>
                <td class="text-cell">{{ (fd.failure_reason || '').slice(0, 30) }}{{ (fd.failure_reason && fd.failure_reason.length > 30) ? '…' : '' }}</td>
                <td>{{ fd.reference || '—' }}</td>
                <td>{{ fd.account_suffix || '—' }}</td>
                <td>{{ fd.created_at }}</td>
                <td>
                  <button class="btn btn-approve" @click="approveFailedDeposit(fd.id, fd.platform)">Approve</button>
                  <button class="btn btn-reject" @click="deleteFailedDeposit(fd.id)">Delete</button>
                </td>
              </tr>
              <tr v-if="!(data.failed_deposits && data.failed_deposits.length)">
                <td colspan="9">No failed deposit requests</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3>✅ Approved Deposits</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>User</th><th>Amount</th><th>Platform</th><th>Text</th><th>Photo</th><th>Created</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in (data.approved_deposits || [])" :key="'ad-' + d.id">
                <td>{{ d.id }}</td>
                <td>{{ d.username }}</td>
                <td>{{ formatCurrency(d.amount) }}</td>
                <td>{{ d.platform }}</td>
                <td class="text-cell">
                  <span v-if="!expandedDepositText['ad-' + d.id]">{{ (d.deposit_text || '').slice(0, 40) }}{{ (d.deposit_text && d.deposit_text.length > 40) ? '…' : '' }}</span>
                  <span v-else class="deposit-text-full">{{ d.deposit_text }}</span>
                  <button v-if="d.deposit_text && d.deposit_text.length > 40" type="button" class="link-btn" @click="toggleDepositText('ad-' + d.id)">
                    {{ expandedDepositText['ad-' + d.id] ? 'Show less' : 'Show more' }}
                  </button>
                </td>
                <td>
                  <button v-if="d.photo_file_id" type="button" class="link-btn" @click="showDepositPhoto(d.id)">📷 Photo</button>
                  <span v-else class="muted">—</span>
                </td>
                <td>{{ d.created_at }}</td>
              </tr>
              <tr v-if="!(data.approved_deposits && data.approved_deposits.length)">
                <td colspan="7">No approved deposits</td>
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
                  <button class="btn btn-secondary" @click="deleteWithdraw(w.id)">Delete</button>
                </td>
              </tr>
              <tr v-if="!(data.pending_withdraws && data.pending_withdraws.length)">
                <td colspan="9">No pending withdraws</td>
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
              <tr><th>ID</th><th>Status</th><th>Players</th><th>Derash</th><th>Actions</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in (data.active_games || [])" :key="'ag-' + g.id">
                <td>{{ g.id }}</td>
                <td>{{ g.status }}</td>
                <td>{{ g.players }}</td>
                <td>{{ formatCurrency(g.derash_amount) }}</td>
                <td>
                  <template v-if="g.status === 'waiting'">
                    <button class="btn btn-approve" @click="startGameAction(g.id)">Start Game</button>
                  </template>
                  <template v-else-if="g.status === 'active'">
                    <input v-model.number="callNumberInput[g.id]" type="number" min="1" max="75" placeholder="#" class="call-number-input" />
                    <button class="btn btn-secondary" @click="callNumberAction(g.id)">Call</button>
                    <button class="btn btn-reject" @click="endGameAction(g.id)">End</button>
                    <button class="btn btn-reject" @click="endGameAction(g.id, true)" title="End game even if not all 75 numbers called (for stuck games)">Force end</button>
                  </template>
                </td>
              </tr>
              <tr v-if="!(data.active_games && data.active_games.length)">
                <td colspan="5">No active games</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Today's Games -->
      <section class="section" id="today-games-section" ref="todayGamesSection">
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
      <section class="section" id="registered-users-section">
        <h2>👥 Registered Users</h2>
        <div class="user-actions-row">
          <label class="sort-label">Sort by:</label>
          <select v-model="registeredSort" class="sort-select" @change="loadData">
            <option value="created_at">Joined (newest)</option>
            <option value="balance">Balance (high first)</option>
            <option value="wins">Wins (high first)</option>
            <option value="games_played">Games played (high first)</option>
            <option value="total_deposits">Deposits (high first)</option>
            <option value="total_withdrawals">Withdrawals (high first)</option>
            <option value="transfer_in">Transfers in (high first)</option>
          </select>
          <button type="button" class="btn btn-reject" @click="toggleDeleteMode">{{ deleteMode ? 'Cancel' : 'Delete Users' }}</button>
          <button v-if="deleteMode" type="button" class="btn btn-reject" @click="deleteSelectedUsers">Delete Selected ({{ selectedUserIds.length }})</button>
          <template v-else>
            <button v-if="registeredLimit <= 10 && (data.registered_users_count || 0) > 10" type="button" class="btn btn-secondary" @click="seeMoreUsers">See more ({{ data.registered_users_count || 0 }} total)</button>
            <button v-else-if="registeredLimit > 10" type="button" class="btn btn-secondary" @click="seeLessUsers">See less</button>
          </template>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th v-if="deleteMode" class="col-check"><input type="checkbox" :checked="allUsersSelected" @change="toggleSelectAll" title="Select all" /></th>
                <th>ID</th><th>Username</th><th>Telegram ID</th><th>Phone</th><th>Name</th><th>ወጭ የማይደረግ (ጨዋታ)</th><th>ወጭ የሚቻል</th><th>Games</th><th>Wins</th><th>Deposits</th><th>Withdrawals</th><th>Transfers in</th><th>Approved</th><th>Joined</th>
                <th v-if="!deleteMode">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in (data.registered_users || [])" :key="'u-' + u.id">
                <td v-if="deleteMode" class="col-check"><input type="checkbox" :value="u.id" v-model="selectedUserIds" /></td>
                <td>{{ u.id }}</td>
                <td>{{ u.username }}</td>
                <td>{{ u.telegram_id || '-' }}</td>
                <td>{{ u.phone_number }}</td>
                <td>{{ u.name || '-' }}</td>
                <td>{{ formatCurrency(u.unwithdrawable_balance != null ? u.unwithdrawable_balance : 0) }}</td>
                <td>{{ formatCurrency(u.withdrawable_balance != null ? u.withdrawable_balance : 0) }}</td>
                <td>{{ u.games_played }}</td>
                <td>{{ u.wins }}</td>
                <td>{{ formatCurrency(u.total_deposits) }}</td>
                <td>{{ formatCurrency(u.total_withdrawals) }}</td>
                <td>{{ formatCurrency(u.transfer_in != null ? u.transfer_in : 0) }}</td>
                <td>{{ u.withdrawal_approved ? '✓' : '–' }}</td>
                <td>{{ u.created_at }}</td>
                <td v-if="!deleteMode" class="col-actions">
                  <button type="button" class="btn btn-secondary btn-sm" @click="editUser(u.id)">Edit</button>
                  <button type="button" class="btn btn-approve btn-sm" @click="viewUserDetails(u.id)">Details</button>
                </td>
              </tr>
              <tr v-if="!(data.registered_users && data.registered_users.length)">
                <td :colspan="deleteMode ? 16 : 15">No registered users yet</td>
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
            <div class="form-grid max-register-limit-row">
            <div class="form-group full-width">
              <label>📋 Max register limit (new users per 24h window)</label>
              <input v-model.number="settings.daily_new_start_limit" type="number" min="0" placeholder="0 = no limit" />
              <small class="form-hint">Registers (24h window): <strong>{{ (settings.new_starts_count_in_window ?? 0) }} / {{ settings.daily_new_start_limit }}</strong> — count updates when a new user shares contact. Users created today: <strong>{{ settings.users_created_today ?? 0 }}</strong>. 0 = no limit.</small>
            </div>
          </div>
          <h3 class="settings-subsection">🚫 Disable bot menus</h3>
          <div class="form-grid">
            <div class="form-group checkbox">
              <label><input v-model="settings.disable_bot_start" type="checkbox" /> Disable /start</label>
              <small class="form-hint">When ticked, the bot will not respond to /start (no welcome, no menu) until you untick and save.</small>
            </div>
            <div class="form-group checkbox">
              <label><input v-model="settings.disable_bot_register" type="checkbox" /> Disable /register</label>
              <small class="form-hint">When ticked, the bot will not respond to /register or contact share (no new registrations) until you untick and save.</small>
            </div>
            <div class="form-group checkbox">
              <label><input v-model="settings.disable_bot_transfer" type="checkbox" /> Disable /transfer</label>
              <small class="form-hint">When ticked, transfer is disabled (button, /transfer, or cached menu). Users with old keyboard will see a disabled message until you untick and save.</small>
            </div>
          </div>
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
              <label>Max Withdrawal (ETB)</label>
              <input v-model.number="settings.max_withdrawal" type="number" step="0.01" min="0" placeholder="0 or empty = no limit" />
              <small class="form-hint">Per 24h from approval. 0 or empty = no limit. User can request again after 24h from last approval.</small>
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
            <div class="form-group winning-patterns">
              <label>Winning Patterns</label>
              <div class="pattern-checkboxes">
                <label><input v-model="settings.winning_patterns" type="checkbox" value="horizontal" /> Horizontal</label>
                <label><input v-model="settings.winning_patterns" type="checkbox" value="vertical" /> Vertical</label>
                <label><input v-model="settings.winning_patterns" type="checkbox" value="diagonal" /> Diagonal</label>
                <label><input v-model="settings.winning_patterns" type="checkbox" value="corner" /> Corner</label>
                <label><input v-model="settings.winning_patterns" type="checkbox" value="full_card" /> Full Card</label>
              </div>
              <small class="form-hint">Select which patterns are valid for winning</small>
            </div>
            <div class="form-group">
              <label>Support Phone</label>
              <input v-model="settings.support_phone" type="text" placeholder="0952838412" />
              <small class="form-hint">Displayed in bot's /support command</small>
            </div>
            <div class="form-group full-width">
              <label>Instruction text (/instruction command)</label>
              <textarea v-model="settings.instruction_text" rows="12" placeholder="Leave empty to use bot default text"></textarea>
              <small class="form-hint">Shown when users send /instruction in the Telegram bot. Empty = use default from bot.</small>
            </div>
          </div>
          <h3 class="settings-subsection">🏦 Deposit Account Information</h3>
          <div class="form-grid deposit-accounts">
            <div class="form-group">
              <label>BOA - Account Holder</label>
              <input v-model="depositAccounts.BOA.name" type="text" />
            </div>
            <div class="form-group">
              <label>BOA - Account Number</label>
              <input v-model="depositAccounts.BOA.number" type="text" />
            </div>
            <div class="form-group">
              <label>CBE - Account Holder</label>
              <input v-model="depositAccounts.CBE.name" type="text" />
            </div>
            <div class="form-group">
              <label>CBE - Account Number</label>
              <input v-model="depositAccounts.CBE.number" type="text" />
            </div>
            <div class="form-group">
              <label>Telebirr - Account Holder</label>
              <input v-model="depositAccounts.Telebirr.name" type="text" />
            </div>
            <div class="form-group">
              <label>Telebirr - Account Number</label>
              <input v-model="depositAccounts.Telebirr.number" type="text" />
            </div>
            <div class="form-group full-width">
              <label>Telebirr Verify API Key</label>
              <input v-model="settings.telebirr_verify_api_key" type="password" placeholder="API key for auto-verify (optional)" autocomplete="off" />
              <small class="form-hint">When set, Telebirr deposits are verified automatically from receipt text (verifyapi.leulzenebe.pro).</small>
            </div>
            <div class="form-group full-width checkbox">
              <label>
                <input v-model="settings.cbe_use_fallback_proxy" type="checkbox" />
                CBE use fallback proxy (server outside Ethiopia)
              </label>
              <small class="form-hint">Enable if your server is outside Ethiopia (e.g. AWS). Asks the verify API to use fallback proxy for CBE so receipts can be verified.</small>
            </div>
          </div>
          <button class="btn btn-primary" :disabled="settingsSaving" @click="saveSettings">{{ settingsSaving ? 'Saving…' : 'Save Settings' }}</button>
          <span v-if="settingsMessage" class="settings-msg" :class="settingsError ? 'error' : ''">{{ settingsMessage }}</span>
        </div>
      </section>

      <!-- Restart Game -->
      <section class="section">
        <h2>🔄 Restart Game</h2>
        <div class="restart-box">
          <p class="restart-warning">⚠️ Sends message to players, optionally refund/cancel the game.</p>
          <div class="form-group">
            <label>Message to Players:</label>
            <textarea v-model="restartMessage" placeholder="Enter message..." rows="3"></textarea>
          </div>
          <div class="restart-options">
            <label><input v-model="restartRefund" type="checkbox" /> Refund bid to players</label>
            <label><input v-model="restartCancel" type="checkbox" /> Cancel the game</label>
          </div>
          <button class="btn btn-reject" @click="restartGameAction">🔄 Send Message & Process</button>
          <span v-if="restartResult" class="restart-msg">{{ restartResult }}</span>
        </div>
      </section>

      <!-- Send Telegram Message (by audience) -->
      <section class="section">
        <h2>📱 Send Telegram Message</h2>
        <div class="broadcast-box">
          <div class="form-group">
            <label>Send to:</label>
            <select v-model="broadcastTarget" class="broadcast-target-select">
              <option value="broadcast">Broadcast (all users)</option>
              <option value="deposit_requesters">Deposit askers</option>
              <option value="withdrawal_requesters">Withdrawal askers</option>
              <option value="not_approved">Not approved (deposit &lt; 50 BR or &lt; 5 games)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Message:</label>
            <textarea v-model="broadcastMessage" placeholder="Enter message..." rows="4"></textarea>
          </div>
          <div class="form-group">
            <label>Amount to Add (optional, 0 for message only):</label>
            <input v-model.number="broadcastAmount" type="number" step="0.01" min="0" placeholder="0" />
          </div>
          <button class="btn btn-primary" :disabled="broadcastSending" @click="sendBroadcast">{{ broadcastSending ? 'Sending…' : '📤 Send Message' }}</button>
          <span v-if="broadcastResult" class="broadcast-msg">{{ broadcastResult }}</span>
        </div>
      </section>

      <!-- Send to Individual User -->
      <section class="section">
        <h2>📨 Send Telegram Message to Individual User</h2>
        <div class="individual-box">
          <div class="form-group">
            <label>Phone Number or User ID:</label>
            <input v-model="individualPhoneOrId" type="text" placeholder="0912345678 or 123" />
          </div>
          <div class="form-group">
            <label>Message:</label>
            <textarea v-model="individualMessage" placeholder="Enter message..." rows="4"></textarea>
          </div>
          <button class="btn btn-approve" :disabled="individualSending" @click="sendIndividual">{{ individualSending ? 'Sending…' : '📤 Send to User' }}</button>
          <span v-if="individualResult" class="individual-msg">{{ individualResult }}</span>
        </div>
      </section>

      <!-- Recent Broadcasts -->
      <section class="section">
        <h2>📋 Recent Broadcast Messages</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>Message</th><th>Amount</th><th>Sent By</th><th>Recipients</th><th>Date</th><th>Action</th></tr>
            </thead>
            <tbody>
              <tr v-for="b in (data.recent_broadcasts || [])" :key="'b-' + b.id">
                <td>{{ b.id }}</td>
                <td class="text-cell">{{ b.message_text }}</td>
                <td>{{ b.amount_added ? formatCurrency(b.amount_added) : '-' }}</td>
                <td>{{ b.sent_by }}</td>
                <td>{{ b.recipients_count }} user(s)</td>
                <td>{{ b.created_at }}</td>
                <td><button class="btn btn-reject" @click="deleteBroadcastAction(b.id)">🗑️ Delete</button></td>
              </tr>
              <tr v-if="!(data.recent_broadcasts && data.recent_broadcasts.length)">
                <td colspan="7">No broadcast messages yet</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Second Admin Credentials -->
      <section class="section">
        <h2>👤 Second Admin Credentials</h2>
        <div class="second-admin-box">
          <div class="form-group">
            <label>Username:</label>
            <input v-model="secondAdminUsername" type="text" />
          </div>
          <div class="form-group">
            <label>Password (leave empty to keep current):</label>
            <input v-model="secondAdminPassword" type="password" placeholder="Leave empty to keep current" />
          </div>
          <button class="btn btn-secondary" :disabled="secondAdminSaving" @click="saveSecondAdmin">{{ secondAdminSaving ? 'Saving…' : '💾 Save Credentials' }}</button>
          <span v-if="secondAdminMessage" class="second-admin-msg">{{ secondAdminMessage }}</span>
          <p class="form-hint">Used to access dashboard at /secondadmin</p>
        </div>
      </section>

      <!-- Game Details -->
      <section class="section">
        <h2>📋 Game Details</h2>
        <button v-if="!showGameDetails" class="btn btn-secondary" @click="showGameDetails = true">See More ({{ (data.games_detail || []).length }} games)</button>
        <div v-if="showGameDetails" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>Status</th><th>Players</th><th>Bid</th><th>Derash</th><th>Winner</th><th>Called</th><th>Created</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in (data.games_detail || [])" :key="'gd-' + g.id">
                <td>{{ g.id }}</td>
                <td>{{ g.status }}</td>
                <td>{{ g.players }}</td>
                <td>{{ formatCurrency(g.bid_amount) }}</td>
                <td>{{ formatCurrency(g.derash_amount) }}</td>
                <td>{{ (g.winner_phones || []).join(', ') || '-' }}</td>
                <td>{{ (g.called_numbers || []).join(', ') || '-' }}</td>
                <td>{{ g.created_at }}</td>
              </tr>
              <tr v-if="!(data.games_detail && data.games_detail.length)">
                <td colspan="8">No games found</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Transfers -->
      <section class="section">
        <h2>💸 Transfers</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>ID</th><th>From</th><th>To</th><th>Amount</th><th>Date</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in (data.recent_transfers || [])" :key="'t-' + t.id">
                <td>{{ t.id }}</td>
                <td>{{ t.from_username }} ({{ t.from_phone }})</td>
                <td>{{ t.to_username }} ({{ t.to_phone }})</td>
                <td>{{ formatCurrency(t.amount) }}</td>
                <td>{{ t.created_at }}</td>
              </tr>
              <tr v-if="!(data.recent_transfers && data.recent_transfers.length)">
                <td colspan="5">No transfers yet</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <!-- Deposit photo modal -->
    <div v-if="showPhotoModal && photoModalDepositId" class="modal-overlay" @click.self="closePhotoModal">
      <div class="modal-content photo-modal">
        <button type="button" class="modal-close" @click="closePhotoModal">×</button>
        <img :src="depositPhotoUrl(photoModalDepositId)" alt="Deposit proof" @error="photoLoadError = true" />
        <p v-if="photoLoadError" class="muted">Photo not available (may have expired).</p>
      </div>
    </div>
  </div>
</template>

<script>
import {
  getAdminDashboardData,
  refreshDepositsWithdrawals,
  searchUser as apiSearchUser,
  searchTransaction as apiSearchTransaction,
  approveDeposit as apiApproveDeposit,
  rejectDeposit as apiRejectDeposit,
  deleteFailedDeposit as apiDeleteFailedDeposit,
  approveFailedDeposit as apiApproveFailedDeposit,
  addCbeReceiptRef as apiAddCbeReceiptRef,
  deleteCbeReceiptRef as apiDeleteCbeReceiptRef,
  addTelebirrReceiptRef as apiAddTelebirrReceiptRef,
  deleteTelebirrReceiptRef as apiDeleteTelebirrReceiptRef,
  approveWithdraw as apiApproveWithdraw,
  rejectWithdraw as apiRejectWithdraw,
  deleteWithdraw as apiDeleteWithdraw,
  getGameSettings,
  updateGameSettings,
  startGame,
  callNumber,
  endGame,
  restartGame,
  sendTelegramBroadcast,
  sendIndividualMessage,
  deleteBroadcast,
  getSecondAdminCredentials,
  saveSecondAdminCredentials,
  adminDashboardLogin,
  getAdminUserDetail,
  editAdminUser,
  deleteAdminUsers
} from '../services/api'

export default {
  name: 'AdminDashboard',
  data() {
    return {
      data: null,
      loading: true,
      error: null,
      lastUpdated: null,
      unauthorized: false,
      searchQuery: '',
      searchResult: null,
      searchTxQuery: '',
      searchTxResult: null,
      searchTxResultObj: null,
      settings: {
        bid_amount: 10,
        card_selection_timer: 60,
        time_between_calls: 3,
        total_cards: 100,
        min_withdraw: 10,
        max_withdrawal: null,
        percentage_cut: 10,
        automatic_mode_enabled: true,
        allow_system_account: true,
        free_play: false,
        system_accounts_min: 15,
        system_accounts_max: 100,
        daily_new_start_limit: 100,
        new_starts_count_in_window: 0,
        users_created_today: 0,
        disable_bot_start: false,
        disable_bot_register: false,
        disable_bot_transfer: false,
        support_phone: '',
        instruction_text: '',
        telebirr_verify_api_key: '',
        cbe_use_fallback_proxy: false
      },
      settingsLoading: false,
      settingsSaving: false,
      settingsMessage: '',
      settingsError: false,
      callNumberInput: {},
      restartMessage: '',
      restartRefund: false,
      restartCancel: false,
      restartResult: '',
      broadcastMessage: '',
      broadcastAmount: 0,
      broadcastTarget: 'broadcast',
      broadcastSending: false,
      broadcastResult: '',
      individualPhoneOrId: '',
      individualMessage: '',
      individualSending: false,
      individualResult: '',
      secondAdminUsername: '',
      secondAdminPassword: '',
      secondAdminSaving: false,
      secondAdminMessage: '',
      showGameDetails: false,
      depositAccounts: {
        BOA: { name: '', number: '' },
        CBE: { name: '', number: '' },
        Telebirr: { name: '', number: '' }
      },
      expandedDepositText: {},
      deleteMode: false,
      selectedUserIds: [],
      showPhotoModal: false,
      photoModalDepositId: null,
      photoLoadError: false,
      showLoginForm: false,
      loginUsername: '',
      loginPassword: '',
      loginError: '',
      loginLoading: false,
      registeredLimit: 10,
      registeredSort: 'created_at'
    }
  },
  computed: {
    adminLoginUrl() {
      const base = window.location.origin
      return `${base}/admin/`
    },
    allUsersSelected() {
      const users = this.data?.registered_users || []
      if (!users.length) return false
      return users.every(u => this.selectedUserIds.includes(u.id))
    }
  },
  async mounted() {
    await this.loadData()
    await this.loadSettings()
    await this.loadSecondAdminCredentials()
  },
  methods: {
    async loadData() {
      this.loading = true
      this.error = null
      try {
        this.data = await getAdminDashboardData({ registered_limit: this.registeredLimit, registered_sort: this.registeredSort })
        this.lastUpdated = new Date().toLocaleString()
        if (this.data?.second_admin_username) {
          this.secondAdminUsername = this.data.second_admin_username
        }
      } catch (err) {
        console.error('Error loading admin dashboard:', err)
        this.unauthorized = err.response?.status === 401
        this.error = err.response?.data?.error || err.response?.data?.message || 'Failed to load dashboard'
      } finally {
        this.loading = false
      }
    },
    async refreshData() {
      await this.loadData()
    },
    async seeMoreUsers() {
      this.registeredLimit = 500
      await this.loadData()
    },
    async seeLessUsers() {
      this.registeredLimit = 10
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
    async doSearchTransaction() {
      if (!this.searchTxQuery.trim()) return
      this.searchTxResult = null
      this.searchTxResultObj = null
      try {
        const res = await apiSearchTransaction(this.searchTxQuery.trim())
        this.searchTxResultObj = typeof res === 'object' ? res : null
        this.searchTxResult = typeof res === 'object' ? JSON.stringify(res, null, 2) : res
      } catch (err) {
        this.searchTxResult = 'Error: ' + (err.response?.data?.error || err.message || 'Search failed')
      }
    },
    async addCbeReceiptRef() {
      const tx = this.searchTxQuery.trim()
      if (!tx) return
      try {
        await apiAddCbeReceiptRef(tx)
        alert('CBE transaction number saved. It cannot be used again for a deposit.')
        await this.doSearchTransaction()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to add')
      }
    },
    async deleteCbeReceiptRef() {
      const tx = this.searchTxQuery.trim()
      if (!tx || !confirm('Remove this CBE ref so a deposit with it can be accepted again?')) return
      try {
        await apiDeleteCbeReceiptRef(tx)
        alert('Transaction number removed.')
        await this.doSearchTransaction()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to delete')
      }
    },
    async addTelebirrReceiptRef() {
      const ref = this.searchTxQuery.trim()
      if (!ref) return
      try {
        await apiAddTelebirrReceiptRef(ref)
        alert('Telebirr reference saved. It cannot be used again for a deposit.')
        await this.doSearchTransaction()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to add')
      }
    },
    async deleteTelebirrReceiptRef() {
      const ref = this.searchTxQuery.trim()
      if (!ref || !confirm('Remove this Telebirr ref so a deposit with it can be accepted again?')) return
      try {
        await apiDeleteTelebirrReceiptRef(ref)
        alert('Telebirr reference removed.')
        await this.doSearchTransaction()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to delete')
      }
    },
    async approveDeposit(id, platform) {
      let transactionNumber = null
      if (platform === 'CBE') {
        const tx = prompt('Enter CBE transaction number from receipt link (e.g. FT26048WBS7024627387). Required for approval.')
        if (tx == null || !String(tx).trim()) return
        transactionNumber = String(tx).trim()
      }
      try {
        await apiApproveDeposit(id, transactionNumber)
        await this.loadData()
      } catch (err) {
        console.error('Approve deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to approve')
      }
    },
    async rejectDeposit(id) {
      if (!confirm('Delete this deposit request? (No notification will be sent.)')) return
      try {
        await apiRejectDeposit(id)
        await this.loadData()
      } catch (err) {
        console.error('Reject deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to reject')
      }
    },
    async deleteFailedDeposit(id) {
      if (!confirm('Delete this failed deposit record?')) return
      try {
        await apiDeleteFailedDeposit(id)
        await this.loadData()
      } catch (err) {
        console.error('Delete failed deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to delete')
      }
    },
    async approveFailedDeposit(id, platform) {
      let transactionNumber = null
      if (platform === 'CBE') {
        const tx = prompt('Enter CBE transaction number (e.g. FT...) so it is saved and cannot be reused.')
        if (tx != null && String(tx).trim()) transactionNumber = String(tx).trim()
      } else if (platform === 'Telebirr') {
        const ref = prompt('Enter Telebirr reference (receipt number) so it is saved and cannot be reused.')
        if (ref != null && String(ref).trim()) transactionNumber = String(ref).trim()
      }
      if (!confirm('Credit the user and remove this failed record?')) return
      try {
        await apiApproveFailedDeposit(id, transactionNumber)
        await this.loadData()
      } catch (err) {
        console.error('Approve failed deposit failed:', err)
        alert(err.response?.data?.error || 'Failed to approve')
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
    async deleteWithdraw(id) {
      if (!confirm('Delete this withdrawal request? (No notification will be sent to the user.)')) return
      try {
        await apiDeleteWithdraw(id)
        await this.loadData()
        alert('Withdrawal request deleted.')
      } catch (err) {
        console.error('Delete withdraw failed:', err)
        alert(err.response?.data?.error || err.response?.data?.message || 'Failed to delete')
      }
    },
    async loadSettings() {
      this.settingsLoading = true
      try {
        const s = await getGameSettings()
        this.settings = { ...this.settings, ...s }
        this.settings.winning_patterns = Array.isArray(s.winning_patterns) ? [...s.winning_patterns] : ['horizontal', 'vertical', 'diagonal']
        const da = s.deposit_accounts || {}
        this.depositAccounts = {
          BOA: da.BOA || { name: '', number: '' },
          CBE: da.CBE || { name: '', number: '' },
          Telebirr: da.Telebirr || { name: '', number: '' }
        }
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
        const payload = {
          ...this.settings,
          deposit_accounts: this.depositAccounts,
          winning_patterns: Array.isArray(this.settings.winning_patterns) ? this.settings.winning_patterns : []
        }
        await updateGameSettings(payload)
        this.settingsMessage = 'Settings saved.'
      } catch (err) {
        this.settingsError = true
        this.unauthorized = err.response?.status === 401
        this.settingsMessage = err.response?.status === 401
          ? 'Please log in via Django Admin first (see link above), then try again.'
          : (err.response?.data?.error || err.message || 'Save failed')
      } finally {
        this.settingsSaving = false
      }
    },
    async startGameAction(gameId) {
      try {
        await startGame(gameId)
        alert('Game started!')
        await this.refreshData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to start game')
      }
    },
    async callNumberAction(gameId) {
      const num = this.callNumberInput[gameId]
      if (!num || num < 1 || num > 75) {
        alert('Enter a valid number (1-75)')
        return
      }
      try {
        const res = await callNumber(gameId, num)
        alert(`Number ${res.letter}-${res.number} called!`)
        this.callNumberInput = { ...this.callNumberInput, [gameId]: null }
        await this.refreshData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to call number')
      }
    },
    async endGameAction(gameId, force = false) {
      const msg = force ? 'Force end this game (even if not all numbers called)? Use this for stuck games.' : 'End this game?'
      if (!confirm(msg)) return
      try {
        await endGame(gameId, { force })
        alert('Game ended!')
        await this.refreshData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to end game')
      }
    },
    async restartGameAction() {
      try {
        const res = await restartGame({
          message: this.restartMessage,
          refund: this.restartRefund,
          cancel: this.restartCancel
        })
        this.restartResult = res.message || 'Done.'
        await this.refreshData()
      } catch (err) {
        this.restartResult = err.response?.data?.error || err.message || 'Failed'
      }
    },
    async sendBroadcast() {
      if (!this.broadcastMessage.trim()) {
        alert('Message is required')
        return
      }
      this.broadcastSending = true
      this.broadcastResult = ''
      try {
        const res = await sendTelegramBroadcast(this.broadcastMessage, this.broadcastAmount || 0, this.broadcastTarget)
        this.broadcastResult = res.message || `Sent to ${res.sent_count || 0} user(s)`
        await this.refreshData()
      } catch (err) {
        this.broadcastResult = err.response?.data?.error || err.message || 'Failed'
      } finally {
        this.broadcastSending = false
      }
    },
    async sendIndividual() {
      if (!this.individualPhoneOrId.trim() || !this.individualMessage.trim()) {
        alert('Phone/ID and message are required')
        return
      }
      this.individualSending = true
      this.individualResult = ''
      try {
        const res = await sendIndividualMessage(this.individualPhoneOrId, this.individualMessage)
        this.individualResult = res.message || 'Sent!'
      } catch (err) {
        this.individualResult = err.response?.data?.error || err.message || 'Failed'
      } finally {
        this.individualSending = false
      }
    },
    async deleteBroadcastAction(id) {
      if (!confirm('Delete this broadcast?')) return
      try {
        await deleteBroadcast(id)
        await this.refreshData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed')
      }
    },
    async loadSecondAdminCredentials() {
      try {
        const res = await getSecondAdminCredentials()
        if (res?.username && !this.secondAdminUsername) {
          this.secondAdminUsername = res.username
        }
      } catch (err) {
        console.error('Load second admin failed:', err)
      }
    },
    toggleDepositText(id) {
      this.expandedDepositText = { ...this.expandedDepositText, [id]: !this.expandedDepositText[id] }
    },
    showDepositPhoto(depositId) {
      this.photoModalDepositId = depositId
      this.photoLoadError = false
      this.showPhotoModal = true
    },
    closePhotoModal() {
      this.showPhotoModal = false
      this.photoModalDepositId = null
      this.photoLoadError = false
    },
    closeLoginForm() {
      this.showLoginForm = false
      this.loginUsername = ''
      this.loginPassword = ''
      this.loginError = ''
    },
    async doAdminLogin() {
      this.loginError = ''
      this.loginLoading = true
      try {
        await adminDashboardLogin(this.loginUsername.trim(), this.loginPassword)
        this.unauthorized = false
        this.closeLoginForm()
        await this.loadData()
      } catch (err) {
        this.loginError = err.response?.data?.error || err.message || 'Login failed'
      } finally {
        this.loginLoading = false
      }
    },
    scrollToTodayGames() {
      this.$nextTick(() => {
        const el = document.getElementById('today-games-section')
        if (el) el.scrollIntoView({ behavior: 'smooth' })
      })
    },
    toggleDeleteMode() {
      this.deleteMode = !this.deleteMode
      if (!this.deleteMode) this.selectedUserIds = []
    },
    toggleSelectAll() {
      const users = this.data?.registered_users || []
      if (this.allUsersSelected) {
        this.selectedUserIds = []
      } else {
        this.selectedUserIds = users.map(u => u.id)
      }
    },
    async deleteSelectedUsers() {
      if (!this.selectedUserIds.length) {
        alert('Select at least one user')
        return
      }
      if (!confirm(`Delete ${this.selectedUserIds.length} user(s)? This cannot be undone.`)) return
      try {
        const res = await deleteAdminUsers(this.selectedUserIds)
        alert(res.message || `Deleted ${res.deleted_count} user(s)`)
        this.selectedUserIds = []
        this.deleteMode = false
        await this.loadData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed to delete')
      }
    },
    async editUser(userId) {
      try {
        const res = await getAdminUserDetail(userId)
        const u = res.user
        const stats = res.statistics || {}
        const totalBal = (u.unwithdrawable_balance != null ? u.unwithdrawable_balance : 0) + (u.withdrawable_balance != null ? u.withdrawable_balance : 0)
        const balance = prompt('New balance (ETB) - will set as unwithdrawable:', totalBal)
        if (balance === null) return
        const phone = prompt('Phone number:', u.phone_number || '')
        if (phone === null) return
        const username = prompt('Username:', u.username || '')
        if (username === null) return
        const firstName = prompt('First name:', u.first_name || '')
        if (firstName === null) return
        const lastName = prompt('Last name:', u.last_name || '')
        if (lastName === null) return
        await editAdminUser(userId, {
          balance: parseFloat(balance) || 0, // backend treats as unwithdrawable total when only balance sent
          phone_number: phone,
          username: username,
          first_name: firstName,
          last_name: lastName
        })
        alert('User updated')
        await this.loadData()
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed')
      }
    },
    async viewUserDetails(userId) {
      try {
        const res = await getAdminUserDetail(userId)
        const u = res.user
        const stats = res.statistics || {}
        const tx = res.transactions || {}
        const lines = [
          `User: ${u.username} (ID: ${u.id})`,
          `Telegram ID: ${u.telegram_id || '-'}`,
          `Phone: ${u.phone_number || '-'}`,
          `Name: ${u.first_name || ''} ${u.last_name || ''}`.trim() || '-',
          `unwithdrawable: ${u.unwithdrawable_balance ?? 0} ETB`,
          `withdrawable: ${u.withdrawable_balance ?? 0} ETB`,
          '',
          'Statistics:',
          `Games: ${stats.games_played ?? '-'}, Wins: ${stats.wins ?? '-'}`,
          `Deposits: ${stats.total_deposits ?? 0} ETB, Withdrawals: ${stats.total_withdrawals ?? 0} ETB`,
          '',
          'Recent:',
          `Deposits: ${(tx.deposits || []).length}, Withdrawals: ${(tx.withdrawals || []).length}`,
          `Bets: ${(tx.bets || []).length}, Prizes: ${(tx.prizes || []).length}`
        ]
        alert(lines.join('\n'))
      } catch (err) {
        alert(err.response?.data?.error || err.message || 'Failed')
      }
    },
    async saveSecondAdmin() {
      if (!this.secondAdminUsername.trim()) {
        alert('Username is required')
        return
      }
      this.secondAdminSaving = true
      this.secondAdminMessage = ''
      try {
        await saveSecondAdminCredentials(this.secondAdminUsername, this.secondAdminPassword)
        this.secondAdminMessage = 'Credentials saved.'
        this.secondAdminPassword = ''
      } catch (err) {
        this.secondAdminMessage = err.response?.data?.error || err.message || 'Failed'
      } finally {
        this.secondAdminSaving = false
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

.admin-login-link {
  padding: 10px 16px;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  font-size: 14px;
}

.admin-login-link:hover {
  background: #2980b9;
}

.inline-login-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.inline-login-box {
  background: white;
  padding: 24px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  width: 100%;
  max-width: 360px;
}
.inline-login-box h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #2c3e50;
}
.inline-login-hint {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: #666;
}
.inline-login-form .form-group {
  margin-bottom: 14px;
}
.inline-login-form .form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
}
.inline-login-form input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.inline-login-error {
  color: #c0392b;
  font-size: 13px;
  margin: 0 0 12px 0;
}
.inline-login-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
.inline-login-actions .btn {
  flex: 1;
}

.unauthorized-banner {
  background: #fff3cd;
  border: 2px solid #ffc107;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}

.unauthorized-banner strong {
  display: block;
  margin-bottom: 8px;
}

.unauthorized-banner a {
  color: #007bff;
  font-weight: 600;
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

.stat-link { color: #2e7d32; text-decoration: underline; cursor: pointer; }
.stat-link:hover { color: #1b5e20; }
.link-btn { background: none; border: none; color: #3498db; cursor: pointer; font-size: 12px; padding: 2px 6px; }
.link-btn:hover { text-decoration: underline; }
.deposit-text-full { display: block; white-space: pre-wrap; word-break: break-word; max-width: 280px; }
.user-actions-row { margin-bottom: 12px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.sort-label { font-size: 13px; margin-right: 4px; }
.sort-select { padding: 6px 10px; border-radius: 6px; border: 1px solid #ccc; font-size: 13px; }
.col-check { width: 36px; }
.col-actions { white-space: nowrap; }
.btn-sm { padding: 4px 8px; font-size: 12px; }

.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.7); z-index: 10000;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.modal-content { background: white; border-radius: 10px; padding: 20px; position: relative; max-width: 90%; max-height: 90%; overflow: auto; }
.modal-close { position: absolute; top: 10px; right: 10px; background: #e74c3c; color: white; border: none; width: 32px; height: 32px; border-radius: 50%; font-size: 20px; cursor: pointer; line-height: 1; }
.photo-modal img { max-width: 100%; max-height: 80vh; display: block; }

@media (max-width: 768px) {
  .admin-dashboard { padding: 12px; }
  .data-table th, .data-table td { padding: 6px 8px; font-size: 12px; }
  .stats-grid { grid-template-columns: 1fr; }
}
</style>
