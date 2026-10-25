<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="src"
        class="fixed inset-0 z-[120] bg-black/95 flex items-center justify-center p-4"
        @click.self="$emit('close')"
      >
        <button
          type="button"
          class="absolute top-[max(1rem,env(safe-area-inset-top))] right-4 w-11 h-11 rounded-full bg-white/10 border border-white/20 flex items-center justify-center text-white"
          aria-label="Close image"
          @click="$emit('close')"
        >
          <X :size="22" />
        </button>
        <img
          :src="src"
          :alt="alt || 'Lottery image'"
          class="max-w-full max-h-full object-contain rounded-xl shadow-2xl"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { X } from 'lucide-vue-next'

defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
})
defineEmits(['close'])
</script>
