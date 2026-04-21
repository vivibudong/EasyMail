import { defineStore } from 'pinia'
import { ref } from 'vue'

type ToastKind = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}

let nextToastId = 1

export const useToastStore = defineStore('toast', () => {
  const items = ref<ToastItem[]>([])

  function push(message: string, kind: ToastKind = 'info', duration = 3600) {
    const id = nextToastId++
    items.value.push({ id, message, kind })
    window.setTimeout(() => remove(id), duration)
  }

  function remove(id: number) {
    items.value = items.value.filter((item) => item.id !== id)
  }

  return { items, push, remove }
})
