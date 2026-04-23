<template>
  <AppLayout title="系统设置" description="按模块管理导入规则、微软授权和通知配置。">
    <div class="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside class="card p-3">
        <div class="space-y-1">
          <button
            v-for="item in sections"
            :key="item.key"
            class="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
            :class="
              currentSection === item.key
                ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/10 dark:text-primary-300'
                : 'text-gray-600 hover:bg-gray-50 dark:text-dark-300 dark:hover:bg-dark-800/60'
            "
            @click="switchSection(item.key)"
          >
            <span>{{ item.label }}</span>
            <span class="text-xs text-gray-400">{{ item.hint }}</span>
          </button>
        </div>
      </aside>

      <div class="space-y-6">
        <section v-if="currentSection === 'import'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">导入规则</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              配置文本导入行为、分隔符和基础显示偏好。
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
          </div>
        </section>

        <section v-else-if="currentSection === 'oauth'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">微软授权配置</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              用于手动授权添加邮箱。这里的配置会被完整备份并在恢复时还原。
            </p>
          </div>

          <div class="card-body grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <span class="input-label mb-0">Client ID</span>
              <input v-model="form.oauth_client_id" class="input" type="text" placeholder="你自己的 Azure 应用 Client ID" />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">Redirect URI</span>
              <input v-model="form.oauth_redirect_uri" class="input" type="text" placeholder="例如：http://localhost:8765/callback" />
            </label>
          </div>

          <div class="card-footer">
            <div class="space-y-2 text-xs leading-6 text-gray-500 dark:text-dark-400">
              <p>这里填写的 Client ID 与 Redirect URI 必须和 Azure 应用注册中的配置完全一致。</p>
              <p>推荐将 `http://localhost:8765/callback` 注册到“移动和桌面应用程序”平台，并授予 `offline_access openid profile email User.Read Mail.Read`。</p>
              <p>授权完成后页面打不开是正常现象，只需要复制浏览器地址栏完整回调地址即可。</p>
            </div>
          </div>
        </section>

        <section v-else class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">通知配置</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              配置 Telegram Bot 通知、监听范围与汇总频率。
            </p>
          </div>

          <div class="card-body grid gap-5 md:grid-cols-2">
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300 md:col-span-2">
              <input v-model="form.telegram_enabled" type="checkbox" />
              启用 Telegram 通知
            </label>

            <label class="space-y-2">
              <span class="input-label mb-0">Telegram Bot Token</span>
              <input v-model="form.telegram_bot_token" class="input" type="text" placeholder="123456:ABC..." />
            </label>

            <label class="space-y-2">
              <span class="input-label mb-0">Telegram Chat ID</span>
              <input v-model="form.telegram_chat_id" class="input" type="text" placeholder="例如：123456789" />
            </label>

            <label class="space-y-2">
              <span class="input-label mb-0">新邮件通知模式</span>
              <select v-model="form.telegram_mail_mode" class="input">
                <option value="off">关闭</option>
                <option value="instant">实时逐封</option>
                <option value="hourly">每小时汇总</option>
              </select>
            </label>

            <label class="space-y-2">
              <span class="input-label mb-0">监听分组</span>
              <select v-model="form.telegram_mail_group" class="input">
                <option value="__all__">全部邮箱</option>
                <option v-for="group in groupOptions" :key="group" :value="group">{{ group }}</option>
              </select>
            </label>

            <label class="space-y-2">
              <span class="input-label mb-0">汇总周期（分钟）</span>
              <input
                v-model.number="form.telegram_mail_summary_minutes"
                class="input"
                type="number"
                min="5"
                :disabled="form.telegram_mail_mode !== 'hourly'"
              />
            </label>

            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
              <input v-model="form.telegram_notify_backup" type="checkbox" />
              备份成功后发送通知
            </label>
          </div>

          <div class="card-footer flex flex-wrap items-center gap-3">
            <button class="btn btn-secondary" :disabled="testingNotification" @click="handleTestNotification">
              {{ testingNotification ? '发送中...' : '测试通知' }}
            </button>
            <div class="text-xs text-gray-500 dark:text-dark-400">
              建议先让目标账号与 Bot 私聊一次，再执行测试通知。
            </div>
          </div>
        </section>

        <section class="card p-6">
          <div class="flex flex-wrap items-center gap-3">
            <button class="btn btn-primary" :disabled="saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
            <div class="text-sm text-gray-500 dark:text-dark-400">
              当前页面的所有配置会一起保存，并会被完整备份到 ZIP 文件中。
            </div>
          </div>
        </section>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSettings, saveSettings, sendTestNotification } from '@/api/dashboard'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useToastStore } from '@/stores/toast'
import type { AppSettings } from '@/types'

const route = useRoute()
const router = useRouter()
const sections = [
  { key: 'import', label: '导入规则', hint: 'TXT / 分隔符' },
  { key: 'oauth', label: '微软授权', hint: 'Client ID / URI' },
  { key: 'notifications', label: '通知', hint: 'Telegram' },
]

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
  telegram_enabled: false,
  telegram_bot_token: '',
  telegram_chat_id: '',
  telegram_mail_mode: 'hourly',
  telegram_mail_group: '__all__',
  telegram_mail_summary_minutes: 60,
  telegram_notify_backup: false,
})

const saving = ref(false)
const testingNotification = ref(false)
const newDelimiter = ref('')
const toastStore = useToastStore()

const currentSection = computed(() => {
  const section = String(route.query.section || 'import')
  return sections.some((item) => item.key === section) ? section : 'import'
})

const groupOptions = computed(() => ['未分组', ...form.custom_groups.map((item) => item.name).filter((name) => name)])

onMounted(async () => {
  const response = await getSettings()
  Object.assign(form, response.data)
})

watch(
  () => route.query.section,
  (value) => {
    const section = String(value || 'import')
    if (!sections.some((item) => item.key === section)) {
      router.replace({ query: { ...route.query, section: 'import' } })
    }
  },
  { immediate: true },
)

function switchSection(section: string) {
  router.replace({ query: { ...route.query, section } })
}

function addDelimiter() {
  const raw = newDelimiter.value.trim()
  if (!raw) return
  const value = raw.toUpperCase() === 'TAB' ? '\\t' : raw
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

async function handleTestNotification() {
  testingNotification.value = true
  try {
    const saveResponse = await saveSettings(form)
    Object.assign(form, saveResponse.data)
    const response = await sendTestNotification()
    toastStore.push(response.message, 'success')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '测试通知发送失败', 'error')
  } finally {
    testingNotification.value = false
  }
}
</script>
