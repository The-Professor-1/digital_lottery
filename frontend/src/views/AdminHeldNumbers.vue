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
        <h3 class="subhead">Hold one number</h3>
        <label>Number <input v-model="single.number" class="admin-input" inputmode="numeric" placeholder="e.g. 061" /></label>
        <label>Phone <input v-model="single.phone" class="admin-input" inputmode="tel" placeholder="09…" /></label>
        <label>Name <input v-model="single.name" class="admin-input" placeholder="Optional name" /></label>
        <label>Note <input v-model="single.note" class="admin-input" placeholder="Optional note" /></label>
        <button type="submit" class="btn primary" :disabled="busy">{{ busy ? 'Saving…' : 'Hold number' }}</button>
      </form>

      <form class="card" @submit.prevent="addBulk">
        <h3 class="subhead">Hold many numbers</h3>
        <label>Numbers <textarea v-model="bulk.numbers" rows="5" class="admin-input" placeholder="e.g. 12, 45, 90 or 12 45 90" /></label>
        <label>Phone for these numbers <input v-model="bulk.phone" class="admin-input" inputmode="tel" placeholder="Optional" /></label>
        <label>Name <input v-model="bulk.name" class="admin-input" placeholder="Optional" /></label>
        <button type="submit" class="btn primary" :disabled="busy">{{ busy ? 'Saving…' : 'Hold all numbers' }}</button>
      </form>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="ok">{{ message }}</p>

    <section class="card">
      <div class="flex items-center justify-between gap-2">
        <h3 class="subhead">Admin-held numbers ({{ held.length }})</h3>
        <button type="button" class="btn ghost" @click="reload">Refresh</button>
      </div>
      <div v-if="held.length" class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Phone</th><th>Name</th><th>Note</th><th></th></tr></thead>
          <tbody>
            <tr v-for="row in held" :key="row.id">
              <td class="num">{{ pad(row.number) }}</td>
              <td>{{ row.phone || '—' }}</td>
              <td>{{ row.name || '—' }}</td>
              <td class="muted">{{ row.note || '—' }}</td>
              <td><button type="button" class="btn danger small" @click="removeHeld(row)">Remove</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="hint">No admin-held numbers for this lottery yet.</p>
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
import { onMounted, reactive, ref } from 'vue'
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
    message.value = 'Number held.'
    single.number = ''
    single.phone = ''
    single.name = ''
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
    message.value = 'Added ' + (res.added || 0) + ' number(s).'
    bulk.numbers = ''
    bulk.phone = ''
    bulk.name = ''
    await reload()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not hold numbers'
  } finally {
    busy.value = false
  }
}

async function removeHeld(row) {
  if (!confirm('Remove held number #' + pad(row.number) + '?')) return
  try {
    await deleteHeldNumberAdmin(row.id, itemId.value || null)
    await reload()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not remove number'
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
