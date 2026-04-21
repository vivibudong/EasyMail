<template>
  <div class="min-h-screen bg-gray-50 dark:bg-dark-950">
    <div class="pointer-events-none fixed inset-0 bg-mesh-gradient"></div>

    <div class="relative min-h-screen">
      <AppHeader
        :title="title"
        :description="description"
        :metrics="metrics"
        :non-success-accounts="nonSuccessAccounts"
        :queue-details="queueDetails"
        :show-task-button="showTaskButton"
        @show-account-detail="emit('show-account-detail', $event)"
        @open-task-center="emit('open-task-center')"
      />
      <main class="p-3 md:p-4 lg:p-4">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AccountIssue, HeaderMetric, QueueProgress } from '@/types'
import AppHeader from './AppHeader.vue'

defineProps<{
  title: string
  description?: string
  metrics?: HeaderMetric[]
  nonSuccessAccounts?: AccountIssue[]
  queueDetails?: QueueProgress | null
  showTaskButton?: boolean
}>()

const emit = defineEmits<{
  (event: 'show-account-detail', account: AccountIssue): void
  (event: 'open-task-center'): void
}>()
</script>
