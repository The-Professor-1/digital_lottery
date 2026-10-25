<template>
  <div class="space-y-4">
    <div>
      <h2 class="section-title">Taken numbers &amp; phone numbers</h2>
      <p class="hint">Hold a number for a walk-in buyer, or paste many numbers at once. Each number keeps the phone you enter.</p>
    </div>

    <label>Lottery
      <select v-model="itemId" class="admin-input" @change="reload">
        <option value="">Main lottery (global)</option>
        <option v-for="item in items" :key="item.id" :value="String(item.id)">{{ item.name }}</option>
      </select>
    </label>

    <div class="grid-2">
      <form class="card" @submit.prevent="addOne">
        <h3 class="subhead">Hold one ticket</h3>
        <label>Number <input v-model="single.number" class="admin-input" inputmode="numeric" placeholder="e.g. 061" /></label>
        <label>Phone <input v-model="single.phone" class="admin-input" inputmode="tel" placeholder="09… (kept for the next ticket)" /></label>
        <label>Name <input v-model="single.name" class="admin-input" placeholder="Optional name" /></label>
        <label>Note <input v-model="single.note" class="admin-input" placeholder="Optional note" /></label>
        <button type="submit" class="btn primary" :disabled="busy">{{ busy ? 'Saving…' : 'Hold ticket' }}</button>
      </form>

      <form class="card" @submit.prevent="addBulk">
        <h3 class="subhead">One person, many tickets</h3>
        <p class="hint">Enter one phone and all tickets that belong to that person.</p>
        <label>Phone <input v-model="bulk.phone" class="admin-input" inputmode="tel" placeholder="09…" /></label>
        <label>Name <input v-model="bulk.name" class="admin-input" placeholder="Optional name" /></label>
        <label>Ticket numbers <textarea v-model="bulk.numbers" rows="5" class="admin-input" placeholder="e.g. 12, 45, 90 or 12 45 90" /></label>
        <button type="submit" class="btn primary" :disabled="busy">{{ busy ? 'Saving…' : 'Hold all tickets' }}</button>
      </form>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="ok">{{ message }}</p>

    <section class="card">
      <div class="flex items-center justify-between gap-2">
        <h3 class="subhead">Held tickets by phone ({{ groups.length }} phones · {{ held.length }} tickets)</h3>
        <button type="button" class="btn ghost" @click="reload">Refresh</button>
      </div>
      <div v-if="groups.length" class="space-y-2">
        <article v-for="group in groups" :key="group.key" class="group-row">
          <div class="group-head">
            <div class="min-w-0">
              <strong class="text-content">{{ group.phone || 'No phone' }}</strong>
              <span v-if="group.name" class="muted"> · {{ group.name }}</span>
              <p v-if="group.note" class="hint">{{ group.note }}</p>
            </div>
            <button type="button" class="btn ghost small" @click="addMoreForGroup(group)">+ Add more tickets</button>
          </div>
          <div class="flex flex-wrap gap-1.5 mt-2">
            <button
              v-for="(number, index) in group.numbers"
              :key="group.ids[index]"
              type="button"
              class="num-chip"
              :title="'Remove #' + pad(number)"
              @click="removeHeldById(group.ids[index], number)"
            >
              #{{ pad(number) }} ×
            </button>
          </div>
        </article>
      </div>
      <p v-else class="hint">No admin-held tickets for this lottery yet.</p>
    </section>

    <section class="card">
      <div class="flex items-center justify-between gap-2">
        <h3 class="subhead">Verified buyer numbers ({{ soldRows.length }})</h3>
        <button type="button" class="btn ghost" @click="loadSold">Refresh</button>
      </div>
      <div v-if="soldRows.length" class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Phone</th><th>Name</th><th>Amount</th></tr></thead>
          <tbody>
            <tr v-for="row in soldRows" :key="row.id">
              <td class="num">{{ row.numbers.map(pad).join(', ') }}</td>
              <td>{{ row.phone || '—' }}</td>
              <td>{{ row.full_name || '—' }}</td>
              <td>{{ row.amount }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="hint">No verified numbers for this lottery yet.</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getLotteryItemsAdmin, getHeldNumbersAdmin, addHeldNumberAdmin, bulkHeldNumbersAdmin,
  deleteHeldNumberAdmin, getLotteryPurchasesAdmin,
} from '../services/api'

const items = ref([])
const itemId = ref('')
const held = ref([])
const soldRows = ref([])
const busy = ref(false)
const error = ref('')
const message = ref('')
const single = reactive({ number: '', phone: '', name: '', note: '' })
const bulk = reactive({ numbers: '', phone: '', name: '' })

const groups = computed(() => {
  const byPhone = new Map()
  for (const row of held.value) {
    const key = row.phone || '__no_phone__'
    if (!byPhone.has(key)) {
      byPhone.set(key, {
        key,
        phone: row.phone || '',
        name: row.name || '',
        note: row.note || '',
        numbers: [],
        ids: [],
      })
    }
    const group = byPhone.get(key)
    group.numbers.push(Number(row.number))
    group.ids.push(row.id)
    if (!group.name && row.name) group.name = row.name
    if (!group.note && row.note) group.note = row.note
  }
  return Array.from(byPhone.values()).sort((a, b) => {
    if (!a.phone) return 1
    if (!b.phone) return -1
    return a.phone.localeCompare(b.phone)
  })
})

function pad(n) {
  return String(n).padStart(3, '0')
}

async function loadItems() {
  try {
    const data = await getLotteryItemsAdmin()
    items.value = data.items || []
    if (!itemId.value && items.value.length) itemId.value = String(items.value[0].id)
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not load lottery items'
  }
}

async function reload() {
  error.value = ''
  if (!itemId.value) {
    held.value = []
    soldRows.value = []
    return
  }
  try {
    const data = await getHeldNumbersAdmin({ lottery_item_id: itemId.value })
    held.value = data.held_numbers || []
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not load held numbers'
  }
  await loadSold()
}

async function loadSold() {
  if (!itemId.value) return
  try {
    const data = await getLotteryPurchasesAdmin({
      status: 'verified',
      lottery_item_id: itemId.value,
    })
    soldRows.value = data.purchases || []
  } catch (e) {
    soldRows.value = []
  }
}

async function addOne() {
  if (!single.number) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await addHeldNumberAdmin({
      lottery_item_id: itemId.value || null,
      number: single.number,
      phone: single.phone,
      name: single.name,
      note: single.note,
    })
    message.value = 'Ticket held.'
    single.number = ''
    single.note = ''
    await reload()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not hold number'
  } finally {
    busy.value = false
  }
}

async function addBulk() {
  if (!bulk.numbers.trim()) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const res = await bulkHeldNumbersAdmin({
      lottery_item_id: itemId.value || null,
      numbers: bulk.numbers,
      phone: bulk.phone,
      name: bulk.name,
    })
    const skipped = Array.isArray(res.skipped) && res.skipped.length
      ? ' Skipped already-taken: ' + res.skipped.map(pad).join(', ')
      : ''
    message.value = 'Added ' + (res.added || 0) + ' ticket(s) for ' + (bulk.phone || 'this person') + '.' + skipped
    bulk.numbers = ''
    await reload()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not hold numbers'
  } finally {
    busy.value = false
  }
}

function addMoreForGroup(group) {
  bulk.phone = group.phone || ''
  bulk.name = group.name || ''
  bulk.numbers = ''
  message.value = 'Add more numbers for ' + (group.phone || 'this person') + ' in the form above.'
}

async function removeHeldById(id, number) {
  if (!confirm('Remove held ticket #' + pad(number) + '?')) return
  try {
    await deleteHeldNumberAdmin(id, itemId.value || null)
    await reload()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not remove ticket'
  }
}

onMounted(async () => {
  await loadItems()
  await reload()
})
</script>

<style scoped>
.section-title { margin: 0; font-size: 1.05rem; color: rgb(var(--gold)); }
.hint { margin: 0.2rem 0 0; font-size: 0.8rem; color: rgb(var(--muted)); }
.subhead { margin: 0 0 0.4rem; font-size: 0.92rem; color: rgb(var(--content)); }
.card { border: 1px solid rgb(var(--line)); border-radius: 12px; background: rgb(var(--surface)); padding: 0.85rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
label { display: block; font-size: 0.8rem; color: rgb(var(--content) / 0.78); margin-bottom: 0.45rem; }
.admin-input { display: block; width: 100%; margin-top: 0.25rem; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid rgb(var(--line)); background: rgb(var(--surface-2)); color: rgb(var(--content)); box-sizing: border-box; }
.btn { border: none; border-radius: 8px; padding: 0.55rem 0.75rem; font-weight: 600; cursor: pointer; background: rgb(var(--surface-3)); color: rgb(var(--content)); }
.btn.primary { background: linear-gradient(90deg, rgb(var(--gold)), rgb(var(--gold-light))); color: rgb(var(--on-gold)); }
.btn.ghost { background: transparent; border: 1px solid rgb(var(--line-strong)); }
.btn.danger { background: rgb(var(--danger-bg)); color: rgb(var(--danger-text)); }
.btn.small { padding: 0.3rem 0.5rem; font-size: 0.72rem; }
.btn:disabled { opacity: 0.5; }
.group-row { border: 1px solid rgb(var(--line)); border-radius: 10px; background: rgb(var(--surface-2)); padding: 0.7rem 0.8rem; }
.group-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.6rem; flex-wrap: wrap; }
.num-chip { background: rgb(var(--success-bg)); color: rgb(var(--success)); font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.5rem; border-radius: 6px; border: none; cursor: pointer; }
.num-chip:hover { background: rgb(var(--danger-bg)); color: rgb(var(--danger-text)); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { text-align: left; padding: 0.5rem 0.45rem; border-bottom: 1px solid rgb(var(--line)); }
th { color: rgb(var(--muted)); font-weight: 600; }
.num { color: rgb(var(--gold)); font-weight: 700; white-space: nowrap; }
.muted { color: rgb(var(--muted)); }
.error { color: rgb(var(--danger-text)); font-size: 0.85rem; margin: 0; }
.ok { color: rgb(var(--success)); font-size: 0.85rem; margin: 0; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
