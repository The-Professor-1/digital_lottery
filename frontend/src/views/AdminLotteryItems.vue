<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-2">
      <div>
        <h2 class="section-title">Lottery items</h2>
        <p class="hint">Each item has its own countdown, prices, taken numbers and flexible prize list.</p>
      </div>
      <button type="button" class="btn primary" @click="resetForm">+ New item</button>
    </div>

    <div v-if="items.length" class="space-y-2">
      <article v-for="item in items" :key="item.id" class="item-row">
        <img v-if="item.image_url" :src="item.image_url" alt="" class="item-thumb" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <strong class="text-white">{{ item.name }}</strong>
            <span class="badge" :class="item.is_active ? 'on' : 'off'">{{ item.is_active ? 'Active' : 'Hidden' }}</span>
          </div>
          <p class="hint">
            {{ item.ticket_price }} Birr · {{ item.total_tickets }} tickets · {{ (item.prizes || []).length }} prizes
            · {{ item.held_count || 0 }} held numbers
          </p>
        </div>
        <div class="flex gap-1.5">
          <button type="button" class="btn ghost" @click="edit(item)">Edit</button>
          <button type="button" class="btn danger" @click="remove(item)">Delete</button>
        </div>
      </article>
    </div>
    <p v-else class="hint">No lottery items yet. Add one below.</p>

    <form class="form-card" @submit.prevent="save">
      <h3 class="subhead">{{ form.id ? 'Edit item' : 'Add item' }}</h3>
      <div class="grid-2">
        <label>Name <input v-model="form.name" class="admin-input" required placeholder="e.g. Grand Draw" /></label>
        <label>Homepage title <input v-model="form.hero_title" class="admin-input" placeholder="Shown above prizes" /></label>
      </div>
      <label>Description <textarea v-model="form.description" rows="2" class="admin-input" placeholder="Optional short description" /></label>
      <div class="grid-2">
        <label>Ticket price <input v-model.number="form.ticket_price" type="number" min="0" class="admin-input" /></label>
        <label>Total tickets <input v-model.number="form.total_tickets" type="number" min="1" class="admin-input" /></label>
        <label>Countdown days <input v-model.number="form.countdown_days" type="number" min="0" class="admin-input" /></label>
        <label>Hours <input v-model.number="form.countdown_hours" type="number" min="0" class="admin-input" /></label>
        <label>Minutes <input v-model.number="form.countdown_minutes" type="number" min="0" class="admin-input" /></label>
        <label>Seconds <input v-model.number="form.countdown_seconds" type="number" min="0" class="admin-input" /></label>
        <label>Sort order <input v-model.number="form.sort_order" type="number" min="0" class="admin-input" /></label>
        <label>Draw mode
          <select v-model="form.draw_mode" class="admin-input">
            <option value="date">Date deadline</option>
            <option value="sold_out">When sold out</option>
            <option value="manual">Admin starts draw</option>
          </select>
        </label>
      </div>
      <label>Main image URL <input v-model="form.image_url" class="admin-input" placeholder="https://… or upload below" /></label>
      <label>Upload main image <input type="file" accept="image/*" class="admin-input" @change="imageFile = $event.target.files?.[0] || null" /></label>
      <label class="check"><input v-model="form.is_active" type="checkbox" /> Active on landing page</label>
      <label class="check"><input v-model="form.automatic_announcement" type="checkbox" /> Automatic announcement video</label>
      <label class="check"><input v-model="form.reset_timer" type="checkbox" /> Restart countdown from the values above</label>

      <div class="prizes-head">
        <div>
          <h4 class="subhead">Prizes</h4>
          <p class="hint">Add any number of prizes. Each can be text, an amount, an image, or a mix.</p>
        </div>
        <button type="button" class="btn ghost" @click="addPrize">+ Add prize</button>
      </div>

      <article v-for="(prize, index) in form.prizes" :key="index" class="prize-row">
        <div class="grid-2">
          <label>Place <input v-model="prize.place" class="admin-input" placeholder="1st / 2nd / Special" /></label>
          <label>Amount (Birr) <input v-model.number="prize.amount" type="number" min="0" class="admin-input" /></label>
        </div>
        <label>Title <input v-model="prize.title" class="admin-input" placeholder="e.g. Toyota Vitz 2019" /></label>
        <label>Description <input v-model="prize.description" class="admin-input" placeholder="Optional details" /></label>
        <div class="grid-2">
          <label>Image URL <input v-model="prize.image_url" class="admin-input" placeholder="https://…" /></label>
          <label>Upload image <input type="file" accept="image/*" class="admin-input" @change="uploadPrize($event, index)" /></label>
        </div>
        <img v-if="prize.image_url" :src="prize.image_url" alt="" class="prize-preview" />
        <button type="button" class="btn danger small" @click="removePrize(index)">Remove prize</button>
        <p v-if="uploadingPrize === index" class="hint">Uploading…</p>
      </article>

      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="message" class="ok">{{ message }}</p>
      <div class="flex gap-2">
        <button type="submit" class="btn primary" :disabled="saving">{{ saving ? 'Saving…' : 'Save item' }}</button>
        <button v-if="form.id" type="button" class="btn ghost" @click="resetForm">Cancel</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  getLotteryItemsAdmin, saveLotteryItemAdmin, deleteLotteryItemAdmin, uploadPrizeImage,
} from '../services/api'

const items = ref([])
const saving = ref(false)
const uploadingPrize = ref(-1)
const error = ref('')
const message = ref('')
const imageFile = ref(null)

function emptyForm() {
  return {
    id: '', name: '', description: '', hero_title: '', image_url: '',
    ticket_price: 3000, total_tickets: 3500, sort_order: 0,
    countdown_days: 12, countdown_hours: 10, countdown_minutes: 24, countdown_seconds: 45,
    draw_mode: 'date', is_active: true, automatic_announcement: true, reset_timer: false, prizes: [],
  }
}
const form = reactive(emptyForm())

async function load() {
  try {
    const data = await getLotteryItemsAdmin()
    items.value = data.items || []
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not load lottery items'
  }
}

function edit(item) {
  Object.assign(form, emptyForm(), {
    ...item,
    prizes: (item.prizes || []).map((p) => ({ ...p })),
  })
  imageFile.value = null
  error.value = ''
  message.value = ''
}

function resetForm() {
  Object.assign(form, emptyForm())
  imageFile.value = null
  error.value = ''
  message.value = ''
}

function addPrize() {
  form.prizes.push({ place: String(form.prizes.length + 1), title: '', description: '', amount: 0, image_url: '' })
}

function removePrize(index) {
  form.prizes.splice(index, 1)
}

async function uploadPrize(event, index) {
  const file = event.target.files?.[0]
  if (!file) return
  uploadingPrize.value = index
  error.value = ''
  try {
    const res = await uploadPrizeImage(file)
    form.prizes[index].image_url = res.url || ''
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not upload prize image'
  } finally {
    uploadingPrize.value = -1
  }
}

async function save() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const fd = new FormData()
    for (const key of ['id', 'name', 'description', 'hero_title', 'image_url', 'ticket_price',
      'total_tickets', 'sort_order', 'countdown_days', 'countdown_hours', 'countdown_minutes',
      'countdown_seconds', 'draw_mode']) {
      if (form[key] !== '' && form[key] !== null && form[key] !== undefined) fd.append(key, form[key])
    }
    fd.append('is_active', form.is_active ? 'true' : 'false')
    fd.append('automatic_announcement', form.automatic_announcement ? 'true' : 'false')
    fd.append('reset_timer', form.reset_timer ? 'true' : 'false')
    fd.append('prizes', JSON.stringify(form.prizes || []))
    if (imageFile.value) fd.append('image', imageFile.value)
    const res = await saveLotteryItemAdmin(fd)
    message.value = 'Item saved.'
    await load()
    if (res.item?.id) edit(res.item)
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not save item'
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  if (!confirm('Delete "' + item.name + '"? Purchases and winner history stay in the database.')) return
  try {
    await deleteLotteryItemAdmin(item.id)
    message.value = 'Item deleted.'
    await load()
    if (String(form.id) === String(item.id)) resetForm()
  } catch (e) {
    error.value = e.response?.data?.error || 'Could not delete item'
  }
}

onMounted(load)
</script>

<style scoped>
.section-title { margin: 0; font-size: 1.05rem; color: #f5a623; }
.hint { margin: 0.2rem 0 0; font-size: 0.8rem; color: #9ca3af; }
.subhead { margin: 0.4rem 0 0.2rem; font-size: 0.95rem; color: #e5e7eb; }
.item-row, .form-card, .prize-row { border: 1px solid #2a3140; border-radius: 12px; background: #0d0d0d; padding: 0.85rem; }
.item-row { display: flex; gap: 0.75rem; align-items: center; }
.item-thumb { width: 54px; height: 54px; border-radius: 8px; object-fit: cover; }
.badge { font-size: 0.65rem; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 5px; text-transform: uppercase; }
.badge.on { background: #064e3b; color: #6ee7b7; }
.badge.off { background: #3f3f46; color: #d4d4d8; }
.form-card { display: flex; flex-direction: column; gap: 0.55rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.55rem; }
label { display: block; font-size: 0.8rem; color: #d1d5db; }
.admin-input { display: block; width: 100%; margin-top: 0.25rem; padding: 0.55rem 0.65rem; border-radius: 8px; border: 1px solid #334155; background: #11151c; color: #fff; box-sizing: border-box; }
.check { display: flex; align-items: center; gap: 0.45rem; }
.prizes-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 0.75rem; flex-wrap: wrap; }
.prize-row { margin-top: 0.35rem; display: flex; flex-direction: column; gap: 0.5rem; background: #11151c; }
.prize-preview { width: 100%; max-height: 170px; object-fit: contain; border-radius: 8px; background: #0d0d0d; }
.btn { border: none; border-radius: 8px; padding: 0.55rem 0.75rem; font-weight: 600; cursor: pointer; background: #374151; color: #fff; }
.btn.primary { background: linear-gradient(90deg, #f5a623, #ffb84d); color: #111; }
.btn.ghost { background: transparent; border: 1px solid #4b5563; }
.btn.danger { background: #7f1d1d; color: #fecaca; }
.btn.small { padding: 0.35rem 0.55rem; font-size: 0.75rem; align-self: flex-start; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #fecaca; font-size: 0.85rem; margin: 0; }
.ok { color: #86efac; font-size: 0.85rem; margin: 0; }
@media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
