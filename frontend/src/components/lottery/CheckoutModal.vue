<template>
  <Transition name="sheet">
    <div
      v-if="store.showCheckout"
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/70"
      @click.self="closeCheckout"
    >
      <div
        class="sheet-panel w-full max-w-phone bg-ink-100 rounded-t-3xl border-t border-white/10 flex flex-col max-h-[94dvh]"
      >
        <div class="px-4 pt-4 pb-2 flex items-start justify-between">
          <div>
            <h2 class="text-lg font-bold text-white">{{ t.completePurchase }}</h2>
            <p class="text-sm text-white/50 mt-0.5">
              {{ store.checkoutStep < 3 ? t.stepOf(store.checkoutStep, 3) : t.confirmStep }}
            </p>
          </div>
          <button type="button" class="p-1 text-white/70" @click="closeCheckout">
            <X :size="20" />
          </button>
        </div>

        <div class="px-4 pb-3 flex gap-1.5">
          <div
            v-for="s in 3"
            :key="s"
            class="h-1.5 flex-1 rounded-full transition-colors"
            :class="s <= store.checkoutStep ? 'bg-gold' : 'bg-ink-300'"
          />
        </div>

        <div class="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
          <!-- Step 1 -->
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

          <!-- Step 2 -->
          <template v-else-if="store.checkoutStep === 2">
            <div>
              <p class="text-sm text-white/85">{{ t.selectBank }}</p>
              <p class="text-xs text-white/45 mt-1">{{ t.selectBankHint }}</p>
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

            <div>
              <p class="text-sm text-white/80 mb-2">{{ t.paymentProof }}</p>
              <label
                class="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-gold/50 bg-ink-200/50 py-8 px-4 cursor-pointer"
              >
                <Upload :size="28" class="text-gold" />
                <span class="text-sm text-white/85">{{ t.uploadProof }}</span>
                <span class="text-xs text-white/40">{{ t.uploadHint }}</span>
                <span v-if="store.paymentProofName" class="text-xs text-forest mt-1">
                  {{ store.paymentProofName }}
                </span>
                <input type="file" accept="image/png,image/jpeg" class="hidden" @change="onFile" />
              </label>
            </div>

            <label class="block">
              <span class="text-sm text-white/70">{{ t.paidFrom }}</span>
              <input
                v-model="store.paidFromAccount"
                type="text"
                class="mt-1.5 w-full rounded-xl bg-ink-200 border border-white/10 px-3 py-3 text-sm text-white outline-none"
              />
            </label>
            <p v-if="store.submitError" class="text-sm text-red-300">{{ store.submitError }}</p>
          </template>

          <!-- Step 3 -->
          <template v-else>
            <div class="text-center py-8 space-y-3">
              <div
                class="mx-auto w-16 h-16 rounded-2xl bg-forest/20 border border-forest/40 flex items-center justify-center"
              >
                <Check :size="32" class="text-forest" />
              </div>
              <h3 class="text-xl font-bold">{{ t.receiptReceived }}</h3>
              <p class="text-sm text-white/80 px-4 leading-relaxed">
                {{ t.receiptPendingHint }}
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
              :disabled="store.submitting || !store.paymentProofFile"
              @click="onSubmit"
            >
              {{ store.submitting ? '…' : t.continue + ' >' }}
            </button>
          </template>
          <template v-else>
            <button type="button" class="btn-green flex-1 py-3.5 text-sm" @click="onDone">
              {{ t.done }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { X, User, Phone, Receipt, Upload, Check } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { formatBirr, padNumber } from '../../data/mock'
import { store, closeCheckout, totalPrice, submitOrder, finishOrder } from '../../stores/lottery'

const { t } = useI18n()
const router = useRouter()

function onFile(e) {
  const file = e.target.files?.[0] || null
  store.paymentProofFile = file
  store.paymentProofName = file ? file.name : ''
  store.submitError = ''
}

async function onSubmit() {
  await submitOrder()
}

function onDone() {
  finishOrder()
  router.push('/tickets')
}
</script>
