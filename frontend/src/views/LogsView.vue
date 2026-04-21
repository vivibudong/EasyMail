<template>
  <AppLayout title="日志" description="查看系统运行日志、刷新失败原因和账号操作记录。">
    <div class="mx-auto max-w-7xl space-y-4">
      <section class="card">
        <div class="card-header flex flex-wrap items-center gap-3">
          <div class="grid min-w-[180px] gap-2 md:grid-cols-4 md:items-end">
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-dark-400">类型</span>
              <select v-model="filters.category" class="input">
                <option value="">全部</option>
                <option v-for="item in categories" :key="item" :value="item">
                  {{ item }}
                </option>
              </select>
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-dark-400">级别</span>
              <select v-model="filters.level" class="input">
                <option value="">全部</option>
                <option value="info">info</option>
                <option value="warn">warn</option>
                <option value="error">error</option>
              </select>
            </label>
            <label class="space-y-1 md:col-span-2">
              <span class="text-xs text-gray-500 dark:text-dark-400">关键字</span>
              <input v-model="filters.keyword" class="input" type="text" placeholder="邮箱 / 信息 / 错误内容" />
            </label>
          </div>
          <div class="ml-auto flex items-center gap-2">
            <button class="btn btn-secondary btn-sm" @click="loadLogs">筛选</button>
            <button class="btn btn-secondary btn-sm" @click="resetFilters">重置</button>
          </div>
        </div>

        <div class="card-body grid gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
          <div class="max-h-[70vh] overflow-y-auto pr-1">
            <button
              v-for="item in logs"
              :key="item.id"
              class="mb-2 w-full rounded-xl border px-3 py-3 text-left transition-all duration-200"
              :class="
                selectedLog?.id === item.id
                  ? 'border-primary-200 bg-primary-50/70 dark:border-primary-800/50 dark:bg-primary-900/10'
                  : 'border-gray-100 bg-white/80 hover:border-gray-200 dark:border-dark-700 dark:bg-dark-800/60 dark:hover:border-dark-600'
              "
              @click="selectedLog = item"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase" :class="levelClass(item.level)">
                  {{ item.level }}
                </span>
                <span class="text-[10px] text-gray-400 dark:text-dark-500">{{ item.created_at }}</span>
              </div>
              <div class="mt-2 truncate text-sm font-medium text-gray-900 dark:text-white">
                {{ item.message }}
              </div>
              <div class="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-dark-400">
                <span>{{ item.category }}</span>
                <span>·</span>
                <span>{{ item.action }}</span>
              </div>
              <div class="mt-1 truncate text-xs text-gray-400 dark:text-dark-500">
                {{ item.subject }}
              </div>
            </button>

            <div v-if="!logs.length" class="empty-state rounded-2xl border border-dashed border-gray-200 dark:border-dark-700">
              <div class="empty-state-title text-sm">暂无日志</div>
              <div class="empty-state-description text-xs">当前筛选条件下没有日志记录。</div>
            </div>
          </div>

          <div class="min-h-[18rem]">
            <div v-if="selectedLog" class="card h-full p-5">
              <div class="mb-3 flex items-center gap-2">
                <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase" :class="levelClass(selectedLog.level)">
                  {{ selectedLog.level }}
                </span>
                <span class="text-xs text-gray-500 dark:text-dark-400">{{ selectedLog.category }}</span>
                <span class="text-xs text-gray-300 dark:text-dark-600">/</span>
                <span class="text-xs text-gray-500 dark:text-dark-400">{{ selectedLog.action }}</span>
              </div>
              <div class="mb-2 text-base font-semibold text-gray-900 dark:text-white">
                {{ selectedLog.message }}
              </div>
              <div class="mb-4 text-sm text-gray-500 dark:text-dark-400">
                {{ selectedLog.subject }}
              </div>
              <div class="mb-3 text-xs text-gray-400 dark:text-dark-500">{{ selectedLog.created_at }}</div>
              <pre class="mail-body !min-h-0 max-h-[48vh] overflow-y-auto">{{ formatDetail(selectedLog.detail) }}</pre>
            </div>

            <div
              v-else
              class="empty-state h-full rounded-2xl border border-dashed border-gray-200 dark:border-dark-700"
            >
              <div class="empty-state-title text-sm">请选择一条日志</div>
              <div class="empty-state-description text-xs">右侧会显示完整详情，便于排查 token、收件和备份问题。</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getLogs } from '@/api/dashboard'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useToastStore } from '@/stores/toast'

type LogItem = {
  id: number
  created_at: string
  level: string
  category: string
  action: string
  subject: string
  message: string
  detail: unknown
}

const toastStore = useToastStore()
const logs = ref<LogItem[]>([])
const selectedLog = ref<LogItem | null>(null)
const filters = ref({
  category: '',
  level: '',
  keyword: '',
})

const categories = [
  'auth',
  'token_refresh',
  'mail_fetch',
  'mail_body',
  'account',
  'group',
  'tag',
  'backup',
  'settings',
  'export',
  'scheduler',
]

onMounted(() => {
  loadLogs()
})

async function loadLogs() {
  try {
    const response = await getLogs(filters.value)
    logs.value = response.data.items
    selectedLog.value = logs.value[0] || null
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '加载日志失败', 'error')
  }
}

function resetFilters() {
  filters.value = { category: '', level: '', keyword: '' }
  loadLogs()
}

function levelClass(level: string) {
  if (level === 'error') return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
  if (level === 'warn') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
  return 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300'
}

function formatDetail(detail: unknown) {
  if (typeof detail === 'string') return detail
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return String(detail)
  }
}
</script>
