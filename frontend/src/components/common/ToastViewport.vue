<template>
  <div class="pointer-events-none fixed bottom-4 right-4 z-[120] flex w-[min(92vw,24rem)] flex-col gap-3">
    <transition-group name="toast-stack">
      <div
        v-for="item in toastStore.items"
        :key="item.id"
        class="pointer-events-auto rounded-2xl border bg-white/95 px-4 py-3 shadow-lg backdrop-blur-xl dark:bg-dark-800/95"
        :class="toastClass(item.kind)"
      >
        <div class="flex items-start gap-3">
          <div class="mt-0.5 rounded-full p-1" :class="iconWrapClass(item.kind)">
            <Icon :name="iconName(item.kind)" size="sm" />
          </div>
          <div class="min-w-0 flex-1 text-sm leading-6">{{ item.message }}</div>
          <button
            class="text-xs text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-dark-300"
            @click="toastStore.remove(item.id)"
          >
            关闭
          </button>
        </div>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/common/Icon.vue'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

function toastClass(kind: 'success' | 'error' | 'info') {
  if (kind === 'success') {
    return 'border-sky-200 text-slate-700 dark:border-sky-800/50 dark:text-dark-100'
  }
  if (kind === 'error') {
    return 'border-red-200 text-slate-700 dark:border-red-800/50 dark:text-dark-100'
  }
  return 'border-cyan-200 text-slate-700 dark:border-cyan-800/50 dark:text-dark-100'
}

function iconWrapClass(kind: 'success' | 'error' | 'info') {
  if (kind === 'success') {
    return 'bg-sky-100 text-sky-600 dark:bg-sky-900/30 dark:text-sky-300'
  }
  if (kind === 'error') {
    return 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-300'
  }
  return 'bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-300'
}

function iconName(kind: 'success' | 'error' | 'info') {
  if (kind === 'error') return 'xCircle'
  if (kind === 'success') return 'checkCircle'
  return 'infoCircle'
}
</script>
