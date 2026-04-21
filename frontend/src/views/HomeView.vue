<template>
  <div
    class="relative flex min-h-screen flex-col overflow-hidden bg-gradient-to-br from-gray-50 via-primary-50/30 to-gray-100 dark:from-dark-950 dark:via-dark-900 dark:to-dark-950"
  >
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -right-40 -top-40 h-96 w-96 rounded-full bg-primary-400/20 blur-3xl"></div>
      <div class="absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-primary-500/15 blur-3xl"></div>
      <div class="absolute left-1/3 top-1/4 h-72 w-72 rounded-full bg-primary-300/10 blur-3xl"></div>
      <div
        class="absolute bottom-1/4 right-1/4 h-64 w-64 rounded-full bg-primary-400/10 blur-3xl"
      ></div>
      <div
        class="absolute inset-0 bg-[linear-gradient(rgba(20,184,166,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(20,184,166,0.03)_1px,transparent_1px)] bg-[size:64px_64px]"
      ></div>
    </div>

    <header class="relative z-20 px-6 py-4">
      <nav class="mx-auto flex max-w-6xl items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="h-10 w-10 overflow-hidden rounded-xl shadow-md">
            <img src="/logo.svg" alt="EasyMail" class="h-full w-full object-contain" />
          </div>
          <div>
            <div class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ siteConfig.siteName }}
            </div>
            <div class="text-xs text-gray-500 dark:text-dark-400">IMAP Mail Manager</div>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <button
            class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-dark-400 dark:hover:bg-dark-800 dark:hover:text-white"
            :title="dark ? '切换浅色模式' : '切换深色模式'"
            @click="onToggleTheme"
          >
            <Icon :name="dark ? 'sun' : 'moon'" size="md" />
          </button>
          <a
            :href="siteConfig.projectUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-dark-400 dark:hover:bg-dark-800 dark:hover:text-white"
            title="GitHub"
          >
            <Icon name="github" size="md" />
          </a>
          <RouterLink
            :to="authStore.isAuthenticated ? '/dashboard' : '/login'"
            class="inline-flex items-center rounded-full bg-gray-900 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-gray-800 dark:bg-gray-800 dark:hover:bg-gray-700"
          >
            {{ authStore.isAuthenticated ? '进入后台' : '立即登录' }}
          </RouterLink>
        </div>
      </nav>
    </header>

    <main class="relative z-10 flex-1 px-6 py-16">
      <div class="mx-auto max-w-6xl">
        <div class="mb-12 flex flex-col items-center justify-between gap-12 lg:flex-row lg:gap-16">
          <div class="flex-1 text-center lg:text-left">
            <h1 class="mb-4 text-4xl font-bold text-gray-900 dark:text-white md:text-5xl lg:text-6xl">
              {{ siteConfig.siteName }}
            </h1>
            <p class="mb-3 text-lg text-gray-600 dark:text-dark-300 md:text-xl">
              面向多邮箱账号的统一收件、管理与排查后台。
            </p>
            <p class="mb-8 text-sm leading-7 text-gray-500 dark:text-dark-400">
              使用 FastAPI + Vue + Docker Compose 构建，面向多邮箱导入、队列化登录收件、本地缓存和正文查看的一体化操作界面。
            </p>

            <div class="flex flex-wrap justify-center gap-3 lg:justify-start">
              <RouterLink
                :to="authStore.isAuthenticated ? '/dashboard' : '/login'"
                class="btn btn-primary px-8 py-3 text-base shadow-lg shadow-primary-500/30"
              >
                {{ authStore.isAuthenticated ? '打开后台' : '开始使用' }}
                <Icon name="arrowRight" size="md" />
              </RouterLink>
              <RouterLink to="/settings" class="btn btn-secondary px-6 py-3 text-base">
                查看配置项
              </RouterLink>
            </div>
          </div>

          <div class="flex flex-1 justify-center lg:justify-end">
            <div class="terminal-container">
              <div class="terminal-window">
                <div class="terminal-header">
                  <div class="terminal-buttons">
                    <span class="btn-close"></span>
                    <span class="btn-minimize"></span>
                    <span class="btn-maximize"></span>
                  </div>
                  <span class="terminal-title">easymail / inbox</span>
                </div>
                <div class="terminal-body">
                  <div class="code-line line-1">
                    <span class="code-prompt">$</span>
                    <span class="code-cmd">docker compose up -d</span>
                  </div>
                  <div class="code-line line-2">
                    <span class="code-comment"># backend: FastAPI · frontend: Vue</span>
                  </div>
                  <div class="code-line line-3">
                    <span class="code-success">SYNC OK</span>
                    <span class="code-response">accounts=42 unread=128</span>
                  </div>
                  <div class="code-line line-4">
                    <span class="code-prompt">$</span>
                    <span class="cursor"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mb-12 flex flex-wrap items-center justify-center gap-4 md:gap-6">
          <div
            class="inline-flex items-center gap-2.5 rounded-full border border-gray-200/50 bg-white/80 px-5 py-2.5 shadow-sm backdrop-blur-sm dark:border-dark-700/50 dark:bg-dark-800/80"
          >
            <Icon name="mail" size="sm" class="text-primary-500" />
            <span class="text-sm font-medium text-gray-700 dark:text-dark-200">批量导入账号</span>
          </div>
          <div
            class="inline-flex items-center gap-2.5 rounded-full border border-gray-200/50 bg-white/80 px-5 py-2.5 shadow-sm backdrop-blur-sm dark:border-dark-700/50 dark:bg-dark-800/80"
          >
            <Icon name="shield" size="sm" class="text-primary-500" />
            <span class="text-sm font-medium text-gray-700 dark:text-dark-200">OAuth2 / 密码混合登录</span>
          </div>
          <div
            class="inline-flex items-center gap-2.5 rounded-full border border-gray-200/50 bg-white/80 px-5 py-2.5 shadow-sm backdrop-blur-sm dark:border-dark-700/50 dark:bg-dark-800/80"
          >
            <Icon name="chart" size="sm" class="text-primary-500" />
            <span class="text-sm font-medium text-gray-700 dark:text-dark-200">收信与正文缓存</span>
          </div>
        </div>

        <div class="grid gap-6 md:grid-cols-3">
          <div
            class="group rounded-2xl border border-gray-200/50 bg-white/60 p-6 backdrop-blur-sm transition-all duration-300 hover:shadow-xl hover:shadow-primary-500/10 dark:border-dark-700/50 dark:bg-dark-800/60"
          >
            <div
              class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/30 transition-transform group-hover:scale-110"
            >
              <Icon name="dashboard" size="lg" class="text-white" />
            </div>
            <h3 class="mb-2 text-lg font-semibold text-gray-900 dark:text-white">三分屏后台</h3>
            <p class="text-sm leading-relaxed text-gray-600 dark:text-dark-400">
              左侧分类、中央邮箱与邮件列表、右侧正文阅读，适合批量处理邮箱任务。
            </p>
          </div>

          <div
            class="group rounded-2xl border border-gray-200/50 bg-white/60 p-6 backdrop-blur-sm transition-all duration-300 hover:shadow-xl hover:shadow-primary-500/10 dark:border-dark-700/50 dark:bg-dark-800/60"
          >
            <div
              class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-sky-500 shadow-lg shadow-cyan-500/30 transition-transform group-hover:scale-110"
            >
              <Icon name="server" size="lg" class="text-white" />
            </div>
            <h3 class="mb-2 text-lg font-semibold text-gray-900 dark:text-white">队列化收件</h3>
            <p class="text-sm leading-relaxed text-gray-600 dark:text-dark-400">
              登录、收信、正文下载全部由后端队列调度，页面轮询展示进度与当前执行账号。
            </p>
          </div>

          <div
            class="group rounded-2xl border border-gray-200/50 bg-white/60 p-6 backdrop-blur-sm transition-all duration-300 hover:shadow-xl hover:shadow-primary-500/10 dark:border-dark-700/50 dark:bg-dark-800/60"
          >
            <div
              class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-cyan-500 shadow-lg shadow-sky-500/30 transition-transform group-hover:scale-110"
            >
              <Icon name="settings" size="lg" class="text-white" />
            </div>
            <h3 class="mb-2 text-lg font-semibold text-gray-900 dark:text-white">设置兼容</h3>
            <p class="text-sm leading-relaxed text-gray-600 dark:text-dark-400">
              保留 TXT 分隔规则、跳过首行、启动自动登录、自动标记已读、邮件显示上限等原始偏好。
            </p>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Icon from '@/components/common/Icon.vue'
import { siteConfig } from '@/config'
import { toggleTheme } from '@/lib/theme'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const dark = ref(document.documentElement.classList.contains('dark'))

onMounted(async () => {
  if (!authStore.ready) {
    await authStore.initialize()
  }
})

function onToggleTheme() {
  dark.value = toggleTheme()
}
</script>

<style scoped>
.terminal-container {
  width: min(100%, 520px);
}

.terminal-window {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(15, 23, 42, 0.92);
  border-radius: 1.5rem;
  overflow: hidden;
  box-shadow: 0 30px 70px rgba(2, 6, 23, 0.22);
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1rem;
  background: rgba(15, 23, 42, 0.94);
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.terminal-buttons {
  display: flex;
  gap: 0.4rem;
}

.terminal-buttons span {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 9999px;
  display: block;
}

.btn-close {
  background: #cbd5e1;
}

.btn-minimize {
  background: #7dd3fc;
}

.btn-maximize {
  background: #38bdf8;
}

.terminal-title {
  color: rgba(226, 232, 240, 0.7);
  font-size: 0.82rem;
}

.terminal-body {
  padding: 1.5rem;
  min-height: 17rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.95rem;
  color: #e2e8f0;
}

.code-line {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 1rem;
}

.code-prompt {
  color: #2dd4bf;
}

.code-cmd {
  color: #f8fafc;
}

.code-comment {
  color: #94a3b8;
}

.code-success {
  color: #67e8f9;
}

.code-response {
  color: #38bdf8;
}

.cursor {
  width: 0.7rem;
  height: 1.1rem;
  background: #2dd4bf;
  display: inline-block;
  animation: blink 1.1s steps(2, start) infinite;
}

@keyframes blink {
  to {
    opacity: 0;
  }
}
</style>
