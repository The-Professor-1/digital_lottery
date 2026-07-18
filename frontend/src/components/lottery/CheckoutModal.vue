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
                  class="flex-1 bg-transparent outline-none text-white placeholder:text-white/30 text-sm"
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
                  class="flex-1 bg-transparent outline-none text-white text-sm"
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
              </div>
              <p class="text-sm text-white font-medium tabular-nums">{{ bank.account }}</p>
            </button>
          </template>

          <!-- Step 3: SMS after bank chosen -->
          <template v-else-if="store.checkoutStep === 3">
            <div class="rounded-2xl bg-ink-200 border border-white/5 p-3">
              <p class="text-xs text-white/45">{{ t.payingTo }}</p>
              <p class="text-sm text-white font-semibold">{{ selectedBank?.name }}</p>
              <p class="text-xs text-gold mt-1">{{ formatBirr(totalPrice()) }}</p>
            </div>

            <label class="block">
              <span class="text-sm text-white/80">{{ t.pasteSms }}</span>
              <p class="text-xs text-white/45 mt-1 mb-2">{{ smsHint }}</p>
              <textarea
                v-model="store.receiptSms"
                rows="6"
                class="w-full rounded-2xl bg-ink-200 border border-white/10 px-3 py-3 text-sm text-white outline-none placeholder:text-white/30 resize-none"
                :placeholder="t.pasteSmsPlaceholder"
                @input="store.submitError = ''"
              />
            </label>

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
                {{ store.orderVerified ? t.paymentVerified : t.manualReviewTitle }}
              </h3>
              <p class="text-sm text-white/80 px-4 leading-relaxed">
                {{ store.submitMessage || (store.orderVerified ? t.paymentVerifiedHint : t.manualReview) }}
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
              :disabled="store.verifying || !(store.receiptSms || '').trim()"
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
          <p class="text-xs text-white/55">{{ t.pickFromAvailable }}</p>
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
            {{ store.conflictPicked.length }} / {{ store.quantity }} {{ t.selected }}
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
              :disabled="store.conflictPicked.length !== store.quantity"
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { X, User, Phone, Receipt, Check, Clock } from 'lucide-vue-next'
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

const selectedBank = computed(() =>
  store.banks.find((b) => b.id === store.selectedBankId)
)

const providerLabel = computed(() => {
  const name = (selectedBank.value?.name || selectedBank.value?.id || '').toLowerCase()
  if (name.includes('tele')) return 'telebirr'
  if (name.includes('cbe') || name.includes('commercial')) return 'CBE'
  return 'telebirr / CBE'
})

const smsHint = computed(() => t.value.fullSmsHint(providerLabel.value))

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
  if (store.conflictPicked.length >= store.quantity) return
  store.conflictPicked.push(n)
}

async function applyConflictAndRetry() {
  if (store.conflictPicked.length !== store.quantity) return
  store.selectedNumbers = [...store.conflictPicked]
  store.conflictDialog = false
  store.conflictAvailable = []
  store.conflictPicked = []
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
