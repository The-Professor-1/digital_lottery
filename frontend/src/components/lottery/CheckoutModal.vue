<template>
  <Transition name="sheet">
    <div
      v-if="store.showCheckout"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/70"
      @click.self="!store.verifying && closeCheckout()"
    >
      <div
        class="sheet-panel w-full max-w-phone bg-ink-100 rounded-t-3xl border-t border-white/10 flex flex-col max-h-[94dvh]"
      >
        <div class="px-4 pt-4 pb-2 flex items-start justify-between">
          <div>
            <h2 class="text-lg font-bold text-white">{{ t.completePurchase }}</h2>
            <p class="text-sm text-white/50 mt-0.5">
              {{ store.checkoutStep < 4 ? t.stepOf(store.checkoutStep, 4) : t.confirmStep }}
            </p>
          </div>
          <button
            type="button"
            class="p-1 text-white/70"
            :disabled="store.verifying"
            @click="closeCheckout"
          >
            <X :size="20" />
          </button>
        </div>

        <div class="px-4 pb-3 flex gap-1.5">
          <div
            v-for="s in 4"
            :key="s"
            class="h-1.5 flex-1 rounded-full transition-colors"
            :class="s <= store.checkoutStep ? 'bg-gold' : 'bg-ink-300'"
          />
        </div>

        <div class="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
          <!-- Step 1: identity -->
          <template v-if="store.checkoutStep === 1">
            <div class="rounded-2xl bg-ink-200 border border-white/5 p-4">
              <p class="font-semibold text-white">{{ store.raffle.displayName }}</p>
              <p class="text-sm text-white/50 mt-1">
                {{ store.quantity }} {{ t.ticketsLabel }} × {{ formatBirr(store.raffle.ticketPrice) }}
              </p>
              <p class="text-gold text-2xl font-bold mt-2">{{ formatBirr(totalPrice()) }}</p>
              <div class="flex flex-wrap gap-1.5 mt-3">
                <span
                  v-for="n in store.selectedNumbers"
                  :key="n"
                  class="inline-block bg-gold text-black text-xs font-bold px-2 py-1 rounded-md"
                >
                  #{{ padNumber(n) }}
                </span>
              </div>
            </div>

            <label class="block">
              <span class="text-sm text-white/70">{{ t.fullName }}</span>
              <div
                class="mt-1.5 flex items-center gap-2 rounded-xl bg-ink-200 border border-white/10 px-3 py-3"
              >
                <User :size="18" class="text-white/40" />
                <input
                  v-model="store.fullName"
                  type="text"
                  autocomplete="name"
                  class="selectable-field flex-1 bg-transparent outline-none text-white placeholder:text-white/30 text-sm"
                  :placeholder="t.fullNamePlaceholder"
                />
              </div>
            </label>

            <label class="block">
              <span class="text-sm text-white/70">{{ t.phoneNumber }}</span>
              <div
                class="mt-1.5 flex items-center gap-2 rounded-xl bg-ink-200 border border-white/10 px-3 py-3"
              >
                <Phone :size="18" class="text-white/40" />
                <input
                  v-model="store.phone"
                  type="tel"
                  inputmode="tel"
                  autocomplete="tel"
                  class="selectable-field flex-1 bg-transparent outline-none text-white text-sm"
                />
              </div>
            </label>
          </template>

          <!-- Step 2: bank only -->
          <template v-else-if="store.checkoutStep === 2">
            <div>
              <p class="text-sm text-white/85">{{ t.selectBank }}</p>
              <p class="text-xs text-white/45 mt-1">{{ t.selectBankRequired }}</p>
            </div>

            <button
              v-for="bank in store.banks"
              :key="bank.id"
              type="button"
              class="w-full flex items-center gap-3 rounded-2xl bg-ink-200 border p-3 text-left transition-colors"
              :class="
                store.selectedBankId === bank.id
                  ? 'border-gold/60 bg-gold/5'
                  : 'border-white/5'
              "
              @click="store.selectedBankId = bank.id"
            >
              <div
                class="w-10 h-10 rounded-xl bg-gold flex items-center justify-center shrink-0"
              >
                <Receipt :size="18" class="text-black" />
              </div>
              <div class="min-w-0 flex-1">
                <p class="font-semibold text-white text-sm truncate">{{ bank.name }}</p>
                <p class="text-xs text-white/45 truncate">{{ bank.holder }}</p>
                <div class="mt-1.5 flex items-center gap-2">
                  <p class="text-sm text-gold font-semibold tabular-nums selectable-field">
                    {{ bank.account }}
                  </p>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-lg bg-white/10 hover:bg-white/15 px-2 py-1 text-[11px] text-white/85 shrink-0"
                    :title="t.copyAccount"
                    @click.stop="copyAndSelectBank(bank)"
                  >
                    <Copy :size="13" />
                    {{ copiedId === bank.id ? t.copied : t.copy }}
                  </button>
                </div>
              </div>
            </button>
          </template>

          <!-- Step 3: screenshot after bank chosen -->
          <template v-else-if="store.checkoutStep === 3">
            <div class="rounded-2xl bg-ink-200 border border-white/5 p-3 space-y-2">
              <p class="text-xs text-white/45">{{ t.payingTo }}</p>
              <p class="text-sm text-white font-semibold">{{ selectedBank?.name }}</p>
              <p v-if="selectedBank?.holder" class="text-xs text-white/50">{{ selectedBank.holder }}</p>
              <div class="flex items-center gap-2">
                <p class="text-sm text-gold font-semibold tabular-nums selectable-field">
                  {{ selectedBank?.account }}
                </p>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 rounded-lg bg-white/10 hover:bg-white/15 px-2 py-1 text-[11px] text-white/85"
                  @click="copyText(selectedBank?.account, 'selected')"
                >
                  <Copy :size="13" />
                  {{ copiedId === 'selected' ? t.copied : t.copy }}
                </button>
              </div>
              <p class="text-xs text-gold mt-1">{{ formatBirr(totalPrice()) }}</p>
            </div>

            <div>
              <p class="text-sm text-white/80 mb-2">{{ t.paymentProof }}</p>
              <label
                class="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-gold/50 bg-ink-200/50 py-8 px-4 cursor-pointer"
              >
                <Upload :size="28" class="text-gold" />
                <span class="text-sm text-white/85">{{ t.uploadProof }}</span>
                <span class="text-xs text-white/40">{{ t.uploadHint }}</span>
                <span v-if="preparingReceipt" class="text-xs text-gold mt-1">
                  {{ t.preparingImage }}
                </span>
                <span v-else-if="store.paymentProofName" class="text-xs text-forest mt-1">
                  {{ store.paymentProofName }}
                </span>
                <input type="file" accept="image/png,image/jpeg" class="hidden" @change="onFile" />
              </label>
            </div>

            <p v-if="store.submitError" class="text-sm text-red-300 leading-relaxed whitespace-pre-wrap">
              {{ store.submitError }}
            </p>
          </template>

          <!-- Step 4: result -->
          <template v-else>
            <div class="text-center py-8 space-y-3">
              <div
                class="mx-auto w-16 h-16 rounded-2xl border flex items-center justify-center"
                :class="
                  store.orderVerified
                    ? 'bg-forest/20 border-forest/40'
                    : 'bg-amber-500/10 border-amber-400/40'
                "
              >
                <Check v-if="store.orderVerified" :size="32" class="text-forest" />
                <Clock v-else :size="32" class="text-amber-300" />
              </div>
              <h3 class="text-xl font-bold">
                {{ store.orderVerified ? t.paymentVerified : t.receiptPendingTitle }}
              </h3>
              <p class="text-sm text-white/80 px-4 leading-relaxed">
                {{ store.submitMessage || (store.orderVerified ? t.paymentVerifiedHint : t.receiptPendingHint) }}
              </p>
            </div>
          </template>
        </div>

        <div class="p-4 border-t border-white/5 flex gap-2">
          <template v-if="store.checkoutStep === 1">
            <button
              type="button"
              class="btn-gold flex-1 py-3.5 text-sm"
              :disabled="!store.fullName.trim() || !store.phone.trim()"
              @click="store.checkoutStep = 2"
            >
              {{ t.continue }} &gt;
            </button>
          </template>
          <template v-else-if="store.checkoutStep === 2">
            <button
              type="button"
              class="flex-1 py-3.5 rounded-2xl border border-white/20 text-white text-sm font-semibold"
              @click="store.checkoutStep = 1"
            >
              {{ t.back }}
            </button>
            <button
              type="button"
              class="btn-green flex-[1.4] py-3.5 text-sm"
              :disabled="!store.selectedBankId"
              @click="store.checkoutStep = 3"
            >
              {{ t.continue }} &gt;
            </button>
          </template>
          <template v-else-if="store.checkoutStep === 3">
            <button
              type="button"
              class="flex-1 py-3.5 rounded-2xl border border-white/20 text-white text-sm font-semibold"
              :disabled="store.verifying"
              @click="store.checkoutStep = 2"
            >
              {{ t.back }}
            </button>
            <button
              type="button"
              class="btn-green flex-[1.4] py-3.5 text-sm"
              :disabled="store.verifying || !store.paymentProofFile"
              @click="onSubmit"
            >
              {{ store.verifying ? t.checking : t.continue + ' >' }}
            </button>
          </template>
          <template v-else>
            <button type="button" class="btn-green flex-1 py-3.5 text-sm" @click="onDone">
              {{ t.done }}
            </button>
          </template>
        </div>
      </div>

      <div
        v-if="store.verifying"
        class="absolute inset-0 z-[60] flex items-center justify-center bg-black/75 px-6"
      >
        <div class="w-full max-w-xs rounded-2xl bg-ink-100 border border-white/10 p-6 text-center space-y-3">
          <div
            class="mx-auto w-12 h-12 rounded-full border-2 border-gold border-t-transparent animate-spin"
          />
          <p class="text-white font-semibold">{{ t.checking }}</p>
          <p class="text-xs text-white/50">{{ t.checkingHint }}</p>
        </div>
      </div>

      <div
        v-if="store.conflictDialog"
        class="absolute inset-0 z-[70] flex items-end justify-center bg-black/80 px-3 pb-3"
        @click.self="store.conflictDialog = false"
      >
        <div class="w-full max-w-phone rounded-2xl bg-ink-100 border border-white/10 p-4 space-y-3 max-h-[80dvh] flex flex-col">
          <h3 class="text-base font-bold text-white">{{ t.numbersTakenTitle }}</h3>
          <p class="text-sm text-red-300 leading-relaxed">{{ store.conflictMessage }}</p>

          <div v-if="store.conflictKept.length" class="space-y-1.5">
            <p class="text-xs text-white/55">{{ t.keptNumbersLabel }}</p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="n in store.conflictKept"
                :key="'k' + n"
                class="inline-block bg-forest/40 border border-forest/50 text-white text-xs font-bold px-2 py-1 rounded-md tabular-nums"
              >
                {{ padNumber(n) }}
              </span>
            </div>
          </div>

          <p class="text-xs text-white/55">
            {{ t.selectMore(conflictNeedMore) }}
          </p>
          <div class="flex-1 overflow-y-auto grid grid-cols-6 gap-1.5 py-1">
            <button
              v-for="n in store.conflictAvailable"
              :key="n"
              type="button"
              class="aspect-square rounded-lg text-[11px] font-semibold tabular-nums"
              :class="
                store.conflictPicked.includes(n)
                  ? 'bg-gold text-black'
                  : 'bg-ink-300 text-white/90'
              "
              @click="toggleConflictPick(n)"
            >
              {{ padNumber(n) }}
            </button>
          </div>
          <p class="text-xs text-white/50">
            {{ store.conflictKept.length + store.conflictPicked.length }} / {{ store.quantity }}
            {{ t.selected }}
          </p>
          <div class="flex gap-2">
            <button
              type="button"
              class="flex-1 py-3 rounded-xl border border-white/20 text-white text-sm"
              @click="store.conflictDialog = false"
            >
              {{ t.back }}
            </button>
            <button
              type="button"
              class="btn-green flex-[1.3] py-3 text-sm"
              :disabled="store.conflictPicked.length !== conflictNeedMore"
              @click="applyConflictAndRetry"
            >
              {{ t.continue }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { X, User, Phone, Receipt, Upload, Check, Clock, Copy } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { formatBirr, padNumber } from '../../data/mock'
import {
  store,
  closeCheckout,
  totalPrice,
  submitOrder,
  finishOrder,
} from '../../stores/lottery'

const { t } = useI18n()
const router = useRouter()
const copiedId = ref('')
const preparingReceipt = ref(false)
let copyTimer = null

const MAX_RECEIPT_DIMENSION = 2000
const RECEIPT_JPEG_QUALITY = 0.88
const MAX_RECEIPT_BYTES = 9 * 1024 * 1024

const selectedBank = computed(() =>
  store.banks.find((b) => b.id === store.selectedBankId)
)

const conflictNeedMore = computed(() =>
  Math.max(0, store.quantity - (store.conflictKept?.length || 0))
)

async function copyText(value, id) {
  const text = String(value || '').trim()
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', '')
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    copiedId.value = id
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copiedId.value = ''
    }, 1600)
  } catch (e) {
    console.warn('copy failed', e)
  }
}

async function copyAndSelectBank(bank) {
  if (bank?.id) store.selectedBankId = bank.id
  await copyText(bank?.account, bank?.id)
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read image')) }
    img.src = url
  })
}

async function prepareReceiptImage(file) {
  if (!file) return file
  const type = String(file.type || '').toLowerCase()
  const name = String(file.name || '').toLowerCase()
  if (!type.startsWith('image/') && !/\.(png|jpe?g|webp|bmp|gif|heic|heif)$/.test(name)) return file
  try {
    const img = await loadImage(file)
    const width = img.naturalWidth || img.width
    const height = img.naturalHeight || img.height
    if (!width || !height) return file
    const scale = Math.min(1, MAX_RECEIPT_DIMENSION / Math.max(width, height))
    if (scale === 1 && file.size <= 1.5 * 1024 * 1024 && type === 'image/jpeg') return file
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', RECEIPT_JPEG_QUALITY))
    if (!blob) return file
    if (blob.size >= file.size && file.size <= MAX_RECEIPT_BYTES) return file
    const base = (file.name || 'receipt').replace(/\.[^.]+$/, '') || 'receipt'
    return new File([blob], base + '.jpg', { type: 'image/jpeg', lastModified: Date.now() })
  } catch (e) {
    return file
  }
}

async function onFile(e) {
  const original = e.target.files?.[0] || null
  store.submitError = ''
  store.paymentProofFile = null
  store.paymentProofName = ''
  if (!original) return
  preparingReceipt.value = true
  try {
    const prepared = await prepareReceiptImage(original)
    if (prepared.size > MAX_RECEIPT_BYTES) {
      store.submitError = t.value.imageTooLarge
      return
    }
    store.paymentProofFile = prepared
    store.paymentProofName = prepared.name
  } finally {
    preparingReceipt.value = false
    try { e.target.value = '' } catch (err) {}
  }
}

async function onSubmit() {
  const ok = await submitOrder()
  if (ok) store.checkoutStep = 4
}

function toggleConflictPick(n) {
  const idx = store.conflictPicked.indexOf(n)
  if (idx >= 0) {
    store.conflictPicked.splice(idx, 1)
    return
  }
  if (store.conflictPicked.length >= conflictNeedMore.value) return
  store.conflictPicked.push(n)
}

async function applyConflictAndRetry() {
  if (store.conflictPicked.length !== conflictNeedMore.value) return
  store.selectedNumbers = [...store.conflictKept, ...store.conflictPicked]
  store.quantity = store.selectedNumbers.length
  store.conflictDialog = false
  store.conflictAvailable = []
  store.conflictPicked = []
  store.conflictKept = []
  store.conflictMessage = ''
  const ok = await submitOrder()
  if (ok) store.checkoutStep = 4
}

function onDone() {
  const goHome = store.orderVerified
  finishOrder()
  router.push(goHome ? '/' : '/tickets')
}
</script>
