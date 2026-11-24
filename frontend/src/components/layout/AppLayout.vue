<template>
  <div
    class="bg-gray-50 dark:bg-dark-950"
    :class="fullHeight ? 'h-screen overflow-hidden' : 'min-h-screen'"
  >
    <div class="pointer-events-none fixed inset-0 bg-mesh-gradient"></div>

    <div
      class="relative flex flex-col"
      :class="fullHeight ? 'h-full min-h-0' : 'min-h-screen'"
    >
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
      <main
        :class="
          fullHeight
            ? 'flex-1 min-h-0 overflow-hidden p-2 md:p-3'
            : 'flex-1 p-3 md:p-5'
        "
      >
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
  fullHeight?: boolean
}>()

const emit = defineEmits<{
  (event: 'show-account-detail', account: AccountIssue): void
  (event: 'open-task-center'): void
}>()
</script>
