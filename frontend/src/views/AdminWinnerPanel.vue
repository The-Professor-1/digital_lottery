<template>
  <div class="space-y-4">
    <div>
      <h2 class="section-title">Winner announcement</h2>
      <p class="hint">Choose a lottery item, then enter the winning ticket number for each prize. The system looks up the holder's phone and name from verified buyers, guest buyers, and admin-held walk-in tickets. Enter the walk-in phone and name only when the number is not found.</p>
    </div>

    <label>Lottery item
      <select v-model="itemId" class="admin-input" @change="onItemChange">
        <option value="">Select lottery item</option>
        <option v-for="item in items" :key="item.id" :value="String(item.id)">{{ item.name }}</option>
      </select>
    </label>

    <template v-if="selectedItem">
      <div class="winner-prize-list">
        <article v-for="(winner, index) in winnerForms" :key="index" class="winner-prize-card">
          <div class="row-between">
            <div class="min-w-0">
              <p class="prize-place">{{ winner.place || ('Prize ' + (index + 1)) }}</p>
              <p class="prize-title">{{ winner.prize_name || 'Prize' }}</p>
            </div>
            <span v-if="winner.amount" class="prize-amount">{{ formatMoney(winner.amount) }} Birr</span>
          </div>
          <label>Winning ticket
            <input
              v-model="winner.winning_ticket"
              class="admin-input"
              inputmode="numeric"
              placeholder="Enter the winning ticket number"
              @input="resetWinnerLookup(winner)"
              @blur="lookupWinner(index)"
            />
          </label>
          <div class="flex items-center gap-2">
            <button type="button" class="btn ghost small" :disabled="winner.lookuping" @click="lookupWinner(index)">
              {{ winner.lookuping ? 'Searching…' : 'Find holder' }}
            </button>
            <span v-if="winner.lookupSource" class="hint">Source: {{ winner.lookupSource }}</span>
          </div>
          <p v-if="winner.lookupState === 'found'" class="ok">
            Holder found: {{ winner.phone || '—' }}<span v-if="winner.name"> · {{ winner.name }}</span>
          </p>
          <p v-else-if="winner.lookupBlocked" class="error">
            {{ winner.lookupMessage || 'This ticket cannot be announced.' }}
          </p>
          <p v-else-if="winner.lookupState === 'not_found'" class="hint">
            {{ winner.lookupMessage || "No registered or held ticket found. Enter the walk-in winner's name and phone." }}
          </p>
          <div v-if="winner.lookupState === 'not_found' && !winner.lookupBlocked" class="grid-2">
            <label>Winner phone
              <input v-model="winner.phone" class="admin-input" inputmode="tel" placeholder="09…" />
            </label>
            <label>Winner name
              <input v-model="winner.name" class="admin-input" placeholder="Walk-in winner name" />
            </label>
          </div>
        </article>
      </div>

      <p class="hint">Round name: <strong>{{ selectedItem.name }}</strong></p>
      <label>Message (optional)
        <textarea v-model="form.message" rows="2" class="admin-input" placeholder="Optional note in the bell and Telegram message" />
      </label>
      <label class="check"><input v-model="notifyUsers" type="checkbox" /> Send Telegram notifications to winners and all participants</label>

      <div class="flex gap-2">
        <button type="button" class="btn primary" :disabled="saving" @click="announce">
          {{ saving ? 'Saving…' : ('Save ' + winnerForms.length + ' winner(s), notify & close round') }}
        </button>
        <button type="button" class="btn ghost" @click="loadWinners">Refresh list</button>
      </div>
    </template>
    <p v-else class="hint">Select a lottery item to load its prizes.</p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="ok">{{ message }}</p>

    <section class="card">
      <h3 class="subhead">Bell history ({{ winners.length }})</h3>
      <div v-if="winners.length" class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Name</th><th>Phone</th><th>Lottery</th><th>Prize</th><th></th></tr></thead>
          <tbody>
            <tr v-for="w in winners" :key="w.id">
              <td class="num">#{{ pad(w.winning_ticket) }}</td>
              <td>{{ w.name || '—' }}</td>
              <td>{{ w.phone || '—' }}</td>
              <td>{{ w.lottery_label || '—' }}</td>
              <td>{{ w.prize_name || '—' }}</td>
              <td><button type="button" class="btn danger small" @click="removeWinner(w)">Delete</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="hint">No winner announcements for this lottery yet.</p>
    </section>

    <section class="card">
      <h3 class="subhead">Closed round history ({{ rounds.length }})</h3>
      <div v-if="rounds.length" class="table-wrap">
        <table>
          <thead><tr><th>Closed</th><th>Lottery</th><th>Round</th><th>Winners</th><th>Tickets</th><th>Revenue</th></tr></thead>
          <tbody>
            <tr v-for="round in rounds" :key="round.id">
              <td>{{ formatWhen(round.closed_at) }}</td>
              <td>{{ round.lottery_name || '—' }}</td>
              <td>{{ round.round_label || '—' }}</td>
              <td>{{ round.winner_count }}</td>
              <td>{{ round.ticket_count }}</td>
              <td>{{ formatMoney(round.verified_revenue) }} Birr</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="hint">No closed rounds for this lottery yet.</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getLotteryItemsAdmin, announceItemWinner, getLotteryWinnersAdmin, deleteLotteryWinnerAdmin, lookupWinnerTicket,
} from '../services/api'

const items = ref([])
const itemId = ref('')
const winners = ref([])
const rounds = ref([])
const winnerForms = ref([])
const notifyUsers = ref(true)
const saving = ref(false)
const error = ref('')
const message = ref('')
const form = reactive({ lottery_label: '', message: '' })

const selectedItem = computed(
  () => items.value.find((it) => String(it.id) === String(itemId.value)) || null
)

function pad(n) {
  return String(n || '').padStart(3, '0')
}

function formatMoney(n) {
  return Number(n || 0).toLocaleString('en-US')
}

function formatWhen(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch (e) {
    return value
  }
}

function buildWinnerForms(item) {
  const prizes = Array.isArray(item?.prizes) ? item.prizes : []
  if (!prizes.length) {
    return [{
      place: '',
      prize_name: item?.name || 'Prize',
      amount: 0,
      phone: '',
      name: '',
      winning_ticket: '',
      lookupState: null,
      lookupSource: '',
      lookupBlocked: false,
      lookupMessage: '',
      lookuping: false,
    }]
  }
  return prizes.map((prize, index) => ({
    place: prize.place || `Prize ${index + 1}`,
    prize_name: prize.title || prize.description || prize.place || `Prize ${index + 1}`,
    amount: Number(prize.amount || 0),
    phone: '',
    name: '',
    winning_ticket: '',
    lookupState: null,
    lookupSource: '',
    lookupBlocked: false,
    lookupMessage: '',
    lookuping: false,
  }))
}

function resetWinnerLookup(winner) {
  winner.lookupState = null
  winner.lookupSource = ''
  winner.lookupBlocked = false
  winner.lookupMessage = ''
  winner.phone = ''
  winner.name = ''
}

async function lookupWinner(index) {
  const winner = winnerForms.value[index]
  if (!winner) return
  const ticket = String(winner.winning_ticket || '').trim()
  if (!ticket) {
    resetWinnerLookup(winner)
    return
  }
  winner.lookuping = true
  error.value = ''
  try {
    const res = await lookupWinnerTicket({
      lottery_item_id: itemId.value,
      ticket_number: ticket,
    })
    // Ignore a late response if the admin changed the ticket while searching.
    if (String(winner.winning_ticket || '').trim() !== ticket) return
    if (res.found && res.phone) {
      winner.lookupState = 'found'
      winner.lookupBlocked = false
      winner.lookupMessage = ''
      winner.phone = res.phone || ''
      winner.name = res.name || ''
      winner.lookupSource = res.source || ''
    } else {
      winner.lookupState = 'not_found'
      winner.lookupBlocked = res.status === 'pending' || res.status === 'blocked'
      winner.lookupMessage = res.message || ''
      winner.lookupSource = res.source || ''
      winner.phone = res.phone || ''
      winner.name = res.name || ''
    }
  } catch (e) {
    if (String(winner.winning_ticket || '').trim() !== ticket) return
    winner.lookupState = 'not_found'
    winner.lookupSource = ''
    winner.lookupBlocked = false
    winner.lookupMessage = ''
    error.value = e.response?.data?.error || 'Could not look up ticket holder'
  } finally {
    winner.lookuping = false
  }
}

function onItemChange() {
  const item = selectedItem.value
  form.lottery_label = item ? (item.name || '') : ''
  winnerForms.value = item ? buildWinnerForms(item) : []
  notifyUsers.value = true
  loadWinners()
}

async function loadItems() {
  try {
    const data = await getLotteryItemsAdmin()
    items.value = data.items || []
    if (!itemId.value && items.value.length) {
      itemId.value = String(items.value[0].id)
      onItemChange()
    } else if (itemId.value) {
      onItemChange()
    }
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not load lottery items'
  }
}

async function loadWinners() {
  try {
    const data = await getLotteryWinnersAdmin(itemId.value ? { lottery_item_id: itemId.value } : {})
    winners.value = data.winners || []
    rounds.value = data.rounds || []
  } catch (e) {
    winners.value = []
  }
}

async function announce() {
  if (!itemId.value) {
    error.value = 'Select a lottery item'
    return
  }
  if (!winnerForms.value.length) {
    error.value = 'This lottery has no prizes to announce'
    return
  }
  for (let index = 0; index < winnerForms.value.length; index += 1) {
    const form = winnerForms.value[index]
    if (!String(form.winning_ticket || '').trim()) {
      error.value = `Enter the winning ticket for ${form.place || `prize ${index + 1}`}`
      return
    }
    if (!form.lookupState) await lookupWinner(index)
    if (form.lookupBlocked) {
      error.value = `Cannot announce ${form.place || `prize ${index + 1}`}: ${form.lookupMessage || 'ticket is not eligible'}`
      return
    }
  }

  const seenTickets = new Set()
  for (const form of winnerForms.value) {
    const normalized = String(Number(form.winning_ticket)).trim()
    if (seenTickets.has(normalized)) {
      error.value = 'Each prize must have a different winning ticket.'
      return
    }
    seenTickets.add(normalized)
    if (form.lookupState === 'not_found' && (!String(form.phone || '').trim() || !String(form.name || '').trim())) {
      error.value = `Enter the walk-in winner name and phone for ${form.place || 'this prize'}`
      return
    }
  }
  if (!confirm('Save these winners, close this round, archive its receipts, and hide this lottery until you create a new item?')) {
    return
  }

  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const payloadWinners = winnerForms.value.map((w) => ({
      phone: w.phone,
      name: w.name,
      winning_ticket: w.winning_ticket,
      prize_name: w.prize_name,
    }))
    const res = await announceItemWinner({
      lottery_item_id: itemId.value,
      lottery_label: form.lottery_label,
      message: form.message,
      notify_users: notifyUsers.value,
      winners: payloadWinners,
    })
    const savedCount = (res.winners || []).length
    const notified = Number(res.notified || 0)
    message.value = `Saved ${savedCount} winner(s)${notified ? ` and notified ${notified} on Telegram` : ''}. Round closed. The lottery was hidden; add a new item to start the next round.`
    winnerForms.value = winnerForms.value.map((w) => ({
      ...w,
      phone: '',
      name: '',
      winning_ticket: '',
      lookupState: null,
      lookupSource: '',
      lookupBlocked: false,
      lookupMessage: '',
      lookuping: false,
    }))
    await loadWinners()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not announce winners'
  } finally {
    saving.value = false
  }
}

async function removeWinner(w) {
  if (!confirm('Delete this winner notification?')) return
  try {
    await deleteLotteryWinnerAdmin(w.id)
    await loadWinners()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not delete winner'
  }
}

onMounted(async () => {
  await loadItems()
  await loadWinners()
})
</script>

<style scoped>
.section-title { margin: 0; font-size: 1.05rem; color: #f5a623; }
.hint { margin: 0.2rem 0 0; font-size: 0.8rem; color: #9ca3af; }
.subhead { margin: 0 0 0.4rem; font-size: 0.92rem; color: #e5e7eb; }
.card { border: 1px solid #2a3140; border-radius: 12px; background: #0d0d0d; padding: 0.85rem; }
.winner-prize-list { display: flex; flex-direction: column; gap: 0.75rem; }
.winner-prize-card { border: 1px solid #334155; border-radius: 12px; background: #11151c; padding: 0.85rem; display: flex; flex-direction: column; gap: 0.55rem; }
.prize-place { margin: 0; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: #f5a623; font-weight: 700; }
.prize-title { margin: 0.15rem 0 0; font-size: 0.95rem; color: #fff; font-weight: 700; }
.prize-amount { color: #f5a623; font-weight: 700; font-size: 0.85rem; white-space: nowrap; }
.row-between { display: flex; justify-content: space-between; gap: 0.75rem; align-items: flex-start; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.65rem; }
label { display: block; font-size: 0.8rem; color: #d1d5db; margin-bottom: 0.45rem; }
.admin-input { display: block; width: 100%; margin-top: 0.25rem; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid #334155; background: #11151c; color: #fff; box-sizing: border-box; }
.check { display: flex; align-items: center; gap: 0.45rem; }
.btn { border: none; border-radius: 8px; padding: 0.55rem 0.75rem; font-weight: 600; cursor: pointer; background: #374151; color: #fff; }
.btn.primary { background: linear-gradient(90deg, #f5a623, #ffb84d); color: #111; }
.btn.ghost { background: transparent; border: 1px solid #4b5563; }
.btn.danger { background: #7f1d1d; color: #fecaca; }
.btn.small { padding: 0.3rem 0.5rem; font-size: 0.72rem; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { text-align: left; padding: 0.5rem 0.45rem; border-bottom: 1px solid #1f2937; }
th { color: #9ca3af; font-weight: 600; }
.num { color: #f5a623; font-weight: 700; white-space: nowrap; }
.error { color: #fecaca; font-size: 0.85rem; margin: 0; }
.ok { color: #86efac; font-size: 0.85rem; margin: 0; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
