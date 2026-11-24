import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { DashboardState } from '@/types'

export const useDashboardStore = defineStore('dashboard', () => {
  const state = ref<DashboardState | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  function setState(next: DashboardState) {
    state.value = next
    initialized.value = true
  }

  function reset() {
    state.value = null
    loading.value = false
    initialized.value = false
  }

  return {
    state,
    loading,
    initialized,
    setState,
    reset,
  }
})
