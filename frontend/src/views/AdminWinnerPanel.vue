<template>
  <div class="space-y-4">
    <div>
      <h2 class="section-title">Winner announcement</h2>
      <p class="hint">Fill the winner details once. They appear in the in-app bell and can be sent to every verified buyer of the selected lottery on Telegram.</p>
    </div>

    <label>Lottery
      <select v-model="itemId" class="admin-input" @change="onItemChange">
        <option value="">Main lottery (global)</option>
        <option v-for="item in items" :key="item.id" :value="String(item.id)">{{ item.name }}</option>
      </select>
    </label>

    <div class="grid-2">
      <label>Lottery label <input v-model="form.lottery_label" class="admin-input" placeholder="e.g. Round 12" /></label>
      <label>Winning ticket <input v-model="form.winning_ticket" class="admin-input" inputmode="numeric" placeholder="061" /></label>
      <label>Winner name <input v-model="form.name" class="admin-input" placeholder="Winner name" /></label>
      <label>Winner phone <input v-model="form.phone" class="admin-input" inputmode="tel" placeholder="09…" /></label>
      <label>Prize / lottery name <input v-model="form.prize_name" class="admin-input" placeholder="Auto from selected item" /></label>
    </div>
    <label>Message (optional) <textarea v-model="form.message" rows="2" class="admin-input" placeholder="Optional note in the bell" /></label>
    <label class="check"><input v-model="notifyUsers" type="checkbox" /> Send Telegram notification to verified buyers</label>

    <div class="flex gap-2">
      <button type="button" class="btn primary" :disabled="saving" @click="announce">{{ saving ? 'Saving…' : (notifyUsers ? 'Announce &amp; notify' : 'Save app notification') }}</button>
      <button type="button" class="btn ghost" @click="loadWinners">Refresh list</button>
    </div>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  getLotteryItemsAdmin, announceItemWinner, getLotteryWinnersAdmin, deleteLotteryWinnerAdmin,
} from '../services/api'

const items = ref([])
const itemId = ref('')
const winners = ref([])
const notifyUsers = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const form = reactive({
  lottery_label: '', winning_ticket: '', name: '', phone: '', prize_name: '', message: '',
})

function pad(n) {
  return String(n || '').padStart(3, '0')
}

function selectedItem() {
  return items.value.find((it) => String(it.id) === String(itemId.value)) || null
}

function onItemChange() {
  notifyUsers.value = !!itemId.value
  const item = selectedItem()
  if (item) {
    if (!form.lottery_label) form.lottery_label = item.name || ''
    const firstPrize = (item.prizes || [])[0]
    if (!form.prize_name) form.prize_name = firstPrize?.title || firstPrize?.description || item.name || ''
  }
  loadWinners()
}

async function loadItems() {
  try {
    const data = await getLotteryItemsAdmin()
    items.value = data.items || []
    if (itemId.value) notifyUsers.value = true
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not load lottery items'
  }
}

async function loadWinners() {
  try {
    const data = await getLotteryWinnersAdmin(itemId.value ? { lottery_item_id: itemId.value } : {})
    winners.value = data.winners || []
  } catch (e) {
    winners.value = []
  }
}

async function announce() {
  if (!form.winning_ticket.trim()) {
    error.value = 'Winning ticket is required'
    return
  }
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const res = await announceItemWinner({
      lottery_item_id: itemId.value || null,
      ...form,
      notify_users: notifyUsers.value,
    })
    const count = Number(res.notified || 0)
    message.value = count ? 'Saved and sent to ' + count + ' buyer(s).' : 'Saved in the in-app bell.'
    form.winning_ticket = ''
    form.name = ''
    form.phone = ''
    form.message = ''
    await loadWinners()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not announce winner'
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
.section-title { margin: 0; font-size: 1.05rem; color: rgb(var(--gold)); }
.hint { margin: 0.2rem 0 0; font-size: 0.8rem; color: rgb(var(--muted)); }
.subhead { margin: 0 0 0.4rem; font-size: 0.92rem; color: rgb(var(--content)); }
.card { border: 1px solid rgb(var(--line)); border-radius: 12px; background: rgb(var(--surface)); padding: 0.85rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.65rem; }
label { display: block; font-size: 0.8rem; color: rgb(var(--content) / 0.78); margin-bottom: 0.45rem; }
.admin-input { display: block; width: 100%; margin-top: 0.25rem; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid rgb(var(--line)); background: rgb(var(--surface-2)); color: rgb(var(--content)); box-sizing: border-box; }
.check { display: flex; align-items: center; gap: 0.45rem; }
.btn { border: none; border-radius: 8px; padding: 0.55rem 0.75rem; font-weight: 600; cursor: pointer; background: rgb(var(--surface-3)); color: rgb(var(--content)); }
.btn.primary { background: linear-gradient(90deg, rgb(var(--gold)), rgb(var(--gold-light))); color: rgb(var(--on-gold)); }
.btn.ghost { background: transparent; border: 1px solid rgb(var(--line-strong)); }
.btn.danger { background: rgb(var(--danger-bg)); color: rgb(var(--danger-text)); }
.btn.small { padding: 0.3rem 0.5rem; font-size: 0.72rem; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { text-align: left; padding: 0.5rem 0.45rem; border-bottom: 1px solid rgb(var(--line)); }
th { color: rgb(var(--muted)); font-weight: 600; }
.num { color: rgb(var(--gold)); font-weight: 700; white-space: nowrap; }
.error { color: rgb(var(--danger-text)); font-size: 0.85rem; margin: 0; }
.ok { color: rgb(var(--success)); font-size: 0.85rem; margin: 0; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
