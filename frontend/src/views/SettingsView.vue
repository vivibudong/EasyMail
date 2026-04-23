<template>
  <AppLayout title="系统设置" description="管理导入规则、显示偏好和基础行为配置。">
    <div class="mx-auto max-w-4xl space-y-6">
      <section class="card">
        <div class="card-header">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">导入与行为设置</h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
            这些配置会被后端持久化，并用于 TXT 导入、启动行为和邮件列表展示。
          </p>
        </div>

        <div class="card-body grid gap-5 md:grid-cols-2">
          <label class="space-y-2">
            <span class="input-label mb-0">注释前缀</span>
            <input v-model="form.txt_comment_prefix" class="input" type="text" />
          </label>

          <label class="space-y-2">
            <span class="input-label mb-0">邮件显示上限</span>
            <input v-model.number="form.mail_list_limit" class="input" type="number" min="0" />
          </label>

          <div class="space-y-2 md:col-span-2">
            <span class="input-label mb-0">邮箱导入分隔符</span>
            <div class="rounded-xl border border-gray-200 p-3 dark:border-dark-700">
              <div class="mb-3 flex flex-wrap gap-2">
                <span
                  v-for="(item, index) in form.import_delimiters"
                  :key="`${item}-${index}`"
                  class="inline-flex items-center gap-2 rounded-full bg-sky-50 px-3 py-1 text-xs text-sky-700 dark:bg-sky-900/20 dark:text-sky-300"
                >
                  {{ item }}
                  <button class="text-sky-500 hover:text-sky-700" @click="removeDelimiter(index)">×</button>
                </span>
              </div>
              <div class="flex gap-2">
                <input v-model="newDelimiter" class="input" type="text" placeholder="例如：||、;、TAB" />
                <button class="btn btn-secondary" @click="addDelimiter">添加</button>
              </div>
              <p class="mt-2 text-xs text-gray-500 dark:text-dark-400">
                导入时会自动尝试这些分隔符，并自动忽略前后的空格；旧格式中的 `\\|\\|`、`-{3,}` 也会自动兼容。
              </p>
            </div>
          </div>
        </div>

        <div class="card-footer flex flex-wrap gap-3">
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
            <input v-model="form.txt_skip_first_line" type="checkbox" />
            导入时跳过首行
          </label>
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
            <input v-model="form.startup_auto_login" type="checkbox" />
            后端启动后自动登录已保存账号
          </label>
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
            <input v-model="form.mark_read_on_open" type="checkbox" />
            点击邮件后自动标记为已读
          </label>
          <div class="ml-auto">
            <button class="btn btn-primary" :disabled="saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </div>
      </section>

      <section class="grid gap-6 md:grid-cols-2">
        <div class="card p-6 md:col-span-2">
          <h3 class="mb-3 text-base font-semibold text-gray-900 dark:text-white">微软授权配置</h3>
          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <span class="input-label mb-0">Client ID</span>
              <input v-model="form.oauth_client_id" class="input" type="text" placeholder="你自己的 Azure 应用 Client ID" />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">Redirect URI</span>
              <input v-model="form.oauth_redirect_uri" class="input" type="text" placeholder="例如：http://localhost:8765/callback" />
            </label>
          </div>
          <div class="mt-3 space-y-2 text-xs leading-6 text-gray-500 dark:text-dark-400">
            <p>这里填写的 Client ID 与 Redirect URI 必须和你在 Azure 应用注册中的配置完全一致。</p>
            <p>建议保留 `http://localhost:8765/callback` 这类本机回调地址；授权完成后页面打不开是正常现象，只需要复制浏览器地址栏完整回调地址。</p>
            <p>系统会固定请求 `offline_access openid profile User.Read Mail.Read`，用于获取并验证可用于收件的 refresh token。</p>
          </div>
        </div>

        <div class="card p-6">
          <h3 class="mb-3 text-base font-semibold text-gray-900 dark:text-white">账号导入格式</h3>
          <div class="space-y-2 text-sm leading-7 text-gray-600 dark:text-dark-300">
            <p>支持多段文本导入格式：</p>
            <code class="code-block block">email || password || client_id || refresh_token</code>
            <p>也支持 `---`、`|`、`,`、`;`、`TAB` 等分隔形式。</p>
          </div>
        </div>

        <div class="card p-6">
          <h3 class="mb-3 text-base font-semibold text-gray-900 dark:text-white">运行说明</h3>
          <ul class="space-y-2 text-sm leading-7 text-gray-600 dark:text-dark-300">
            <li>账号、已读状态和邮件缓存都保存到后端 `data` 目录。</li>
            <li>勾选“启动自动登录”后，重启 Compose 会自动重新入队登录。</li>
            <li>正文下载采用后台任务轮询，避免浏览器长时间阻塞。</li>
          </ul>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getSettings, saveSettings } from '@/api/dashboard'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useToastStore } from '@/stores/toast'
import type { AppSettings } from '@/types'

const form = reactive<AppSettings>({
  auto_receive_interval: 120,
  import_delimiters: ['---', '||', '|', ',', ';', '\\t'],
  txt_comment_prefix: '#',
  txt_skip_first_line: false,
  startup_auto_login: true,
  mail_list_limit: 0,
  mark_read_on_open: true,
  custom_groups: [],
  custom_tags: [],
  auto_receive_enabled: false,
  auto_receive_interval_minutes: 15,
  token_refresh_enabled: false,
  token_refresh_interval_minutes: 360,
  backup_enabled: false,
  backup_interval_minutes: 1440,
  backup_directory: 'backups',
  backup_keep_count: 10,
  oauth_client_id: '',
  oauth_redirect_uri: 'http://localhost:8765/callback',
})

const saving = ref(false)
const newDelimiter = ref('')
const toastStore = useToastStore()

onMounted(async () => {
  const response = await getSettings()
  Object.assign(form, response.data)
})

function addDelimiter() {
  const raw = newDelimiter.value.trim()
  if (!raw) return
  const value = raw.toUpperCase() === 'TAB' ? '\\t' : raw
  if (!value) return
  if (!form.import_delimiters.includes(value)) {
    form.import_delimiters.push(value)
  }
  newDelimiter.value = ''
}

function removeDelimiter(index: number) {
  form.import_delimiters.splice(index, 1)
}

async function handleSave() {
  saving.value = true
  try {
    const response = await saveSettings(form)
    Object.assign(form, response.data)
    toastStore.push(response.message, 'success')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '设置保存失败', 'error')
  } finally {
    saving.value = false
  }
}
</script>
