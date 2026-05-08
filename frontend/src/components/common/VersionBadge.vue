<template>
  <div ref="rootRef" class="relative">
    <button
      class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2 text-left shadow-sm transition-colors"
      :class="badgeClass"
      @click.stop="dropdownOpen = !dropdownOpen"
    >
      <span class="h-1.5 w-1.5 rounded-full" :class="dotClass" />
      <span class="leading-[0.85rem]">
        <span class="block text-[9px] font-semibold uppercase tracking-[0.12em] opacity-75">EasyMail</span>
        <span class="block text-[11px] font-semibold">v{{ versionInfo?.current_version || '0.1.4' }}</span>
      </span>
      <span v-if="checking" class="text-[10px] opacity-70">检查中</span>
    </button>

    <transition name="dropdown">
      <div
        v-if="dropdownOpen"
        class="dropdown absolute left-0 top-full z-50 mt-2 w-80 p-0 text-sm"
      >
        <div class="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-dark-700">
          <div>
            <div class="font-semibold text-gray-900 dark:text-white">版本信息</div>
            <div class="mt-0.5 text-xs text-gray-500 dark:text-dark-400">
              {{ versionInfo?.has_update ? '检测到新版本' : '当前已是最新版' }}
            </div>
          </div>
          <button
            class="rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-60 dark:border-dark-700 dark:text-dark-300 dark:hover:bg-dark-700"
            :disabled="checking"
            @click.stop="loadVersion(true)"
          >
            刷新
          </button>
        </div>

        <div class="space-y-3 p-4">
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-dark-700/50">
              <div class="text-gray-500 dark:text-dark-400">当前版本</div>
              <div class="mt-1 font-semibold text-gray-900 dark:text-white">
                v{{ versionInfo?.current_version || '0.1.4' }}
              </div>
            </div>
            <div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-dark-700/50">
              <div class="text-gray-500 dark:text-dark-400">最新版本</div>
              <div class="mt-1 font-semibold text-gray-900 dark:text-white">
                v{{ versionInfo?.latest_version || versionInfo?.current_version || '0.1.4' }}
              </div>
            </div>
          </div>

          <div
            v-if="versionInfo?.has_update"
            class="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200"
          >
            <div class="font-semibold">新版本可用</div>
            <div class="mt-1 line-clamp-3 whitespace-pre-line">
              {{ releaseSummary || '点击查看更新日志了解变更内容。' }}
            </div>
          </div>
          <div
            v-else
            class="rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-200"
          >
            当前运行版本已是最新版。
          </div>

          <div
            v-if="versionInfo?.warning"
            class="rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-dark-700/50 dark:text-dark-400"
          >
            检查更新提示：{{ versionInfo.warning }}
          </div>

          <div
            v-if="updateMessage || updateError"
            class="rounded-xl px-3 py-2 text-xs"
            :class="updateError ? 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-300' : 'bg-cyan-50 text-cyan-700 dark:bg-cyan-900/20 dark:text-cyan-200'"
          >
            {{ updateError || updateMessage }}
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              class="btn btn-primary btn-sm flex-1"
              :disabled="updating || !versionInfo?.has_update"
              @click.stop="handleUpdate"
            >
              {{ updating ? '更新中...' : '更新' }}
            </button>
            <button
              class="btn btn-secondary btn-sm flex-1"
              :disabled="restarting"
              @click.stop="handleRestart"
            >
              {{ restarting ? `重启中 ${restartCountdown}s` : '立即重启' }}
            </button>
          </div>

          <a
            :href="versionInfo?.release_info?.html_url || 'https://github.com/vivibudong/EasyMail/releases'"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex w-full items-center justify-center rounded-xl border border-gray-200 px-3 py-2 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-dark-700 dark:text-dark-300 dark:hover:bg-dark-700"
          >
            查看 Git 更新日志
          </a>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { apiClient } from '@/api/client'
import { checkUpdates, restartSystem, updateSystem, type VersionInfo } from '@/api/system'

const rootRef = ref<HTMLElement | null>(null)
const dropdownOpen = ref(false)
const checking = ref(false)
const updating = ref(false)
const restarting = ref(false)
const restartCountdown = ref(0)
const versionInfo = ref<VersionInfo | null>(null)
const updateMessage = ref('')
const updateError = ref('')

const badgeClass = computed(() => {
  if (versionInfo.value?.has_update) {
    return 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200'
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-200'
})

const dotClass = computed(() => (versionInfo.value?.has_update ? 'bg-amber-400' : 'bg-emerald-500'))

const releaseSummary = computed(() => {
  const body = versionInfo.value?.release_info?.body || ''
  return body
    .split('\n')
    .map((line) => line.replace(/^#+\s*/, '').trim())
    .filter(Boolean)
    .slice(0, 3)
    .join('\n')
})

async function loadVersion(force = false) {
  checking.value = true
  updateError.value = ''
  try {
    const response = await checkUpdates(force)
    versionInfo.value = response.data
  } catch (error) {
    updateError.value = error instanceof Error ? error.message : '检查更新失败'
  } finally {
    checking.value = false
  }
}

async function handleUpdate() {
  updating.value = true
  updateMessage.value = ''
  updateError.value = ''
  try {
    const response = await updateSystem()
    updateMessage.value = response.message || '更新完成，请点击立即重启'
  } catch (error: any) {
    updateError.value = error?.response?.data?.detail || error?.message || '在线更新失败'
  } finally {
    updating.value = false
  }
}

async function handleRestart() {
  restarting.value = true
  updateError.value = ''
  updateMessage.value = '服务正在重启，请稍候...'
  restartCountdown.value = 8
  try {
    await restartSystem()
  } catch {
    // Restart may close the connection before the response returns.
  }
  const timer = window.setInterval(async () => {
    restartCountdown.value -= 1
    if (restartCountdown.value <= 0) {
      window.clearInterval(timer)
      await waitForHealth()
    }
  }, 1000)
}

async function waitForHealth() {
  for (let index = 0; index < 20; index += 1) {
    try {
      await apiClient.get('/health', { baseURL: '/', timeout: 1500 })
      window.location.reload()
      return
    } catch {
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
    }
  }
  restarting.value = false
  updateError.value = '重启状态未确认，请手动刷新页面。'
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (rootRef.value && !rootRef.value.contains(target)) {
    dropdownOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  loadVersion()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>
