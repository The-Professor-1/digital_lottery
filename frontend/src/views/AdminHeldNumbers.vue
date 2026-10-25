<template>
  <div class="space-y-4">
    <div>
      <h2 class="section-title">Taken numbers &amp; phone numbers</h2>
      <p class="hint">Enter one phone and its ticket numbers. For a single walk-in ticket, enter just one number; for several tickets, separate them with commas or spaces.</p>
    </div>

    <label>Lottery
      <select v-model="itemId" class="admin-input" @change="reload">
        <option value="">Main lottery (global)</option>
        <option v-for="item in items" :key="item.id" :value="String(item.id)">{{ item.name }}</option>
      </select>
    </label>

    <form class="card" @submit.prevent="addBulk">
      <h3 class="subhead">Hold tickets for one phone</h3>
      <p class="hint">One number is enough for a single ticket. Multiple numbers can be comma- or space-separated.</p>
      <label>Phone <input v-model="bulk.phone" class="admin-input" inputmode="tel" placeholder="09…" /></label>
      <label>Name <input v-model="bulk.name" class="admin-input" placeholder="Optional name" /></label>
      <label>Ticket numbers <textarea v-model="bulk.numbers" rows="3" class="admin-input" placeholder="e.g. 12, 45, 90 or one number like 12" /></label>
      <label>Note <input v-model="bulk.note" class="admin-input" placeholder="Optional note" /></label>
      <button type="submit" class="btn primary" :disabled="busy">{{ busy ? 'Saving…' : 'Hold ticket(s)' }}</button>
    </form>

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
              <strong class="text-white">{{ group.phone || 'No phone' }}</strong>
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
  getLotteryItemsAdmin, getHeldNumbersAdmin, bulkHeldNumbersAdmin,
  deleteHeldNumberAdmin, getLotteryPurchasesAdmin,
} from '../services/api'

const items = ref([])
const itemId = ref('')
const held = ref([])
const soldRows = ref([])
const busy = ref(false)
const error = ref('')
const message = ref('')
const bulk = reactive({ numbers: '', phone: '', name: '', note: '' })

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
      note: bulk.note,
    })
    const skipped = Array.isArray(res.skipped) && res.skipped.length
      ? ' Skipped already-taken: ' + res.skipped.map(pad).join(', ')
      : ''
    message.value = 'Added ' + (res.added || 0) + ' ticket(s) for ' + (bulk.phone || 'this person') + '.' + skipped
    bulk.numbers = ''
    bulk.note = ''
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
.section-title { margin: 0; font-size: 1.05rem; color: #f5a623; }
.hint { margin: 0.2rem 0 0; font-size: 0.8rem; color: #9ca3af; }
.subhead { margin: 0 0 0.4rem; font-size: 0.92rem; color: #e5e7eb; }
.card { border: 1px solid #2a3140; border-radius: 12px; background: #0d0d0d; padding: 0.85rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
label { display: block; font-size: 0.8rem; color: #d1d5db; margin-bottom: 0.45rem; }
.admin-input { display: block; width: 100%; margin-top: 0.25rem; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid #334155; background: #11151c; color: #fff; box-sizing: border-box; }
.btn { border: none; border-radius: 8px; padding: 0.55rem 0.75rem; font-weight: 600; cursor: pointer; background: #374151; color: #fff; }
.btn.primary { background: linear-gradient(90deg, #f5a623, #ffb84d); color: #111; }
.btn.ghost { background: transparent; border: 1px solid #4b5563; }
.btn.danger { background: #7f1d1d; color: #fecaca; }
.btn.small { padding: 0.3rem 0.5rem; font-size: 0.72rem; }
.btn:disabled { opacity: 0.5; }
.group-row { border: 1px solid #2a3140; border-radius: 10px; background: #11151c; padding: 0.7rem 0.8rem; }
.group-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.6rem; flex-wrap: wrap; }
.num-chip { background: #064e3b; color: #6ee7b7; font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.5rem; border-radius: 6px; border: none; cursor: pointer; }
.num-chip:hover { background: #7f1d1d; color: #fecaca; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { text-align: left; padding: 0.5rem 0.45rem; border-bottom: 1px solid #1f2937; }
th { color: #9ca3af; font-weight: 600; }
.num { color: #f5a623; font-weight: 700; white-space: nowrap; }
.muted { color: #9ca3af; }
.error { color: #fecaca; font-size: 0.85rem; margin: 0; }
.ok { color: #86efac; font-size: 0.85rem; margin: 0; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
