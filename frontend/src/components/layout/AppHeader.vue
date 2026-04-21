<template>
  <header class="glass sticky top-0 z-30 border-b border-gray-200/50 dark:border-dark-700/50">
    <div class="flex h-14 items-center justify-between px-3 md:px-4">
      <div class="flex items-center gap-4">
        <RouterLink
          to="/dashboard"
          class="flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl shadow-glow transition-transform hover:scale-[1.02]"
        >
          <img src="/logo.svg" alt="EasyMail" class="h-full w-full object-contain" />
        </RouterLink>
        <div>
          <h1 class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
          <p v-if="description" class="text-xs text-gray-500 dark:text-dark-400">
            {{ description }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2 md:gap-3">
        <div v-if="metrics?.length" class="hidden items-center gap-2 xl:flex">
          <div
            v-for="metric in metrics"
            :key="metric.label"
            class="relative"
          >
            <button
              class="inline-flex items-center gap-2 rounded-full border border-cyan-100 bg-white/80 px-3 py-1.5 text-xs text-slate-600 shadow-sm dark:border-cyan-900/40 dark:bg-dark-800/70 dark:text-dark-200"
              :class="{ 'cursor-pointer hover:border-cyan-200 hover:bg-cyan-50/60 dark:hover:border-cyan-800 dark:hover:bg-dark-700/60': metric.clickable }"
              :data-header-popover-trigger="metric.key || ''"
              @click.stop="handleMetricClick(metric)"
            >
              <Icon :name="metric.icon" size="sm" class="text-primary-500" />
              <span class="text-slate-400 dark:text-dark-400">{{ metric.label }}</span>
              <span class="font-semibold text-slate-700 dark:text-white">{{ metric.value }}</span>
            </button>

            <transition name="dropdown">
              <div
                v-if="metric.key === 'success' && activePopover === 'success'"
                class="dropdown absolute right-0 top-full mt-2 w-80 p-0"
                data-header-popover
              >
                <div class="border-b border-gray-100 px-4 py-3 text-sm font-semibold dark:border-dark-700">
                  未成功邮箱
                </div>
                <div class="max-h-80 overflow-y-auto p-2">
                  <div
                    v-if="!nonSuccessAccounts?.length"
                    class="px-3 py-4 text-sm text-gray-500 dark:text-dark-400"
                  >
                    当前全部邮箱都已登录成功。
                  </div>
                  <button
                    v-for="account in nonSuccessAccounts || []"
                    :key="account.email"
                    class="mb-1 block w-full rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50 dark:hover:bg-dark-700/60"
                    @click.stop="emit('show-account-detail', account)"
                  >
                    <div class="truncate font-medium text-gray-900 dark:text-white">{{ account.email }}</div>
                    <div class="mt-0.5 text-xs text-gray-500 dark:text-dark-400">
                      {{ account.status }}
                    </div>
                    <div class="mt-1 line-clamp-2 text-xs text-red-500">
                      {{ account.last_error_summary || '等待处理' }}
                    </div>
                  </button>
                </div>
              </div>
            </transition>

            <transition name="dropdown">
              <div
                v-if="metric.key === 'queue' && activePopover === 'queue'"
                class="dropdown absolute right-0 top-full mt-2 w-96 p-0"
                data-header-popover
              >
                <div class="border-b border-gray-100 px-4 py-3 text-sm font-semibold dark:border-dark-700">
                  队列详情
                </div>
                <div class="space-y-3 p-4 text-sm">
                  <div class="grid grid-cols-2 gap-3">
                    <div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-dark-700/50">
                      <div class="text-xs text-gray-500 dark:text-dark-400">登录队列</div>
                      <div class="mt-1 font-semibold text-gray-900 dark:text-white">
                        {{ queueDetails?.login_done ?? 0 }}/{{ queueDetails?.login_total ?? 0 }}
                      </div>
                    </div>
                    <div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-dark-700/50">
                      <div class="text-xs text-gray-500 dark:text-dark-400">收件队列</div>
                      <div class="mt-1 font-semibold text-gray-900 dark:text-white">
                        {{ queueDetails?.receive_done ?? 0 }}/{{ queueDetails?.receive_total ?? 0 }}
                      </div>
                    </div>
                  </div>
                  <div class="space-y-2 text-xs text-gray-600 dark:text-dark-300">
                    <div>登录中：{{ queueDetails?.login_busy_email || '无' }}</div>
                    <div>收信中：{{ queueDetails?.receive_busy_email || '无' }}</div>
                    <div>等待登录：{{ queueDetails?.pending_login_emails?.length || 0 }}</div>
                    <div>等待收信：{{ queueDetails?.pending_receive_emails?.length || 0 }}</div>
                    <div>等待正文：{{ queueDetails?.pending_body_keys?.length || 0 }}</div>
                  </div>
                  <div class="space-y-3">
                    <div>
                      <div class="mb-1 text-xs font-medium text-gray-500 dark:text-dark-400">待登录邮箱</div>
                      <div class="max-h-24 overflow-y-auto rounded-xl bg-gray-50 px-3 py-2 text-xs dark:bg-dark-700/50">
                        {{ (queueDetails?.pending_login_emails || []).join('、') || '无' }}
                      </div>
                    </div>
                    <div>
                      <div class="mb-1 text-xs font-medium text-gray-500 dark:text-dark-400">待收件邮箱</div>
                      <div class="max-h-24 overflow-y-auto rounded-xl bg-gray-50 px-3 py-2 text-xs dark:bg-dark-700/50">
                        {{ (queueDetails?.pending_receive_emails || []).join('、') || '无' }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </transition>
          </div>
        </div>

        <button class="btn btn-secondary btn-sm" @click="onToggleTheme">
          <Icon :name="dark ? 'sun' : 'moon'" size="sm" />
          <span class="hidden sm:inline">{{ dark ? '浅色' : '深色' }}</span>
        </button>

        <button
          v-if="showTaskButton"
          class="btn btn-secondary btn-sm"
          @click="$emit('open-task-center')"
        >
          <Icon name="refresh" size="sm" />
          <span class="hidden sm:inline">任务</span>
        </button>

        <div class="relative">
          <button
            class="flex items-center gap-2 rounded-xl p-1.5 transition-colors hover:bg-gray-100 dark:hover:bg-dark-800"
            @click="dropdownOpen = !dropdownOpen"
          >
            <div
              class="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 text-sm font-medium text-white shadow-sm"
            >
              {{ initials }}
            </div>
            <div class="hidden text-left md:block">
              <div class="text-sm font-medium text-gray-900 dark:text-white">
                {{ authStore.user?.email }}
              </div>
              <div class="text-xs text-gray-500 dark:text-dark-400">admin</div>
            </div>
            <Icon name="chevronDown" size="sm" class="hidden text-gray-400 md:block" />
          </button>

          <transition name="dropdown">
            <div v-if="dropdownOpen" class="dropdown right-0 mt-2 w-56">
              <div class="border-b border-gray-100 px-4 py-3 dark:border-dark-700">
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ authStore.user?.email }}
                </div>
                <div class="text-xs text-gray-500 dark:text-dark-400">管理员账号</div>
              </div>
              <div class="py-1">
                <RouterLink to="/dashboard" class="dropdown-item" @click="dropdownOpen = false">
                  <Icon name="dashboard" size="sm" />
                  后台面板
                </RouterLink>
                <a
                  :href="siteConfig.projectUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="dropdown-item"
                  @click="dropdownOpen = false"
                >
                  <Icon name="github" size="sm" />
                  项目地址
                </a>
                <RouterLink to="/logs" class="dropdown-item" @click="dropdownOpen = false">
                  <Icon name="book" size="sm" />
                  日志
                </RouterLink>
                <RouterLink to="/settings" class="dropdown-item" @click="dropdownOpen = false">
                  <Icon name="settings" size="sm" />
                  系统设置
                </RouterLink>
              </div>
              <div class="border-t border-gray-100 py-1 dark:border-dark-700">
                <button
                  class="dropdown-item w-full text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                  @click="handleLogout"
                >
                  <Icon name="logout" size="sm" />
                  退出登录
                </button>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import Icon from '@/components/common/Icon.vue'
import { siteConfig } from '@/config'
import { toggleTheme } from '@/lib/theme'
import { useAuthStore } from '@/stores/auth'
import type { AccountIssue, HeaderMetric, QueueProgress } from '@/types'

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

const router = useRouter()
const authStore = useAuthStore()
const dropdownOpen = ref(false)
const activePopover = ref<'success' | 'queue' | null>(null)
const dark = ref(document.documentElement.classList.contains('dark'))

const initials = computed(() => {
  const email = authStore.user?.email || 'AD'
  return email.split('@')[0].slice(0, 2).toUpperCase()
})

function onToggleTheme() {
  dark.value = toggleTheme()
}

function handleMetricClick(metric: HeaderMetric) {
  if (!metric.clickable || !metric.key) return
  activePopover.value = activePopover.value === metric.key ? null : metric.key
}

function handleLogout() {
  dropdownOpen.value = false
  authStore.logout()
  router.push('/login')
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.dropdown') && !target.closest('button')) {
    dropdownOpen.value = false
  }
  if (!target.closest('[data-header-popover]') && !target.closest('[data-header-popover-trigger]')) {
    activePopover.value = null
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>
