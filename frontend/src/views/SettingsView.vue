<template>
  <AppLayout title="系统设置" description="按模块管理导入规则、阅读偏好、通知与自动任务。">
    <div class="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside class="card p-3">
        <div class="space-y-1">
          <button
            v-for="item in sections"
            :key="item.key"
            class="flex w-full items-center rounded-xl px-3 py-2.5 text-left text-sm transition-colors"
            :class="
              currentSection === item.key
                ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/10 dark:text-primary-300'
                : 'text-gray-600 hover:bg-gray-50 dark:text-dark-300 dark:hover:bg-dark-800/60'
            "
            @click="switchSection(item.key)"
          >
            <span>{{ item.label }}</span>
          </button>
        </div>
      </aside>

      <div class="space-y-6">
        <section v-if="currentSection === 'import'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">导入规则</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              配置文本导入行为和分隔符规则。
            </p>
          </div>

          <div class="card-body grid gap-5">
            <label class="space-y-2">
              <span class="input-label mb-0">注释前缀</span>
              <input v-model="form.txt_comment_prefix" class="input" type="text" />
            </label>

            <div class="space-y-2">
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
          </div>
        </section>

        <section v-else-if="currentSection === 'reading'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">阅读偏好</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              控制打开邮件后的阅读行为。
            </p>
          </div>

          <div class="card-body">
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

        <section v-else-if="currentSection === 'notifications'" class="card">
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

            <div class="space-y-2 md:col-span-2">
              <span class="input-label mb-0">监听分组</span>
              <div class="rounded-xl border border-gray-200 p-3 dark:border-dark-700">
                <div class="flex flex-wrap gap-2">
                  <label
                    v-for="group in notificationGroupOptions"
                    :key="group.value"
                    class="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs text-gray-700 dark:border-dark-700 dark:text-dark-200"
                  >
                    <input v-model="form.telegram_mail_groups" :value="group.value" type="checkbox" />
                    {{ group.label }}
                  </label>
                </div>
                <p class="mt-2 text-xs text-gray-500 dark:text-dark-400">
                  只监听勾选分组中的邮箱；不勾选任何分组时，不发送新邮件通知。
                </p>
              </div>
            </div>

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

        <section v-else-if="currentSection === 'refresh'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">邮箱刷新</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              管理自动登录、定时收件和 Token 刷新任务。
            </p>
          </div>

          <div class="card-body grid gap-5 md:grid-cols-2">
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300 md:col-span-2">
              <input v-model="form.startup_auto_login" type="checkbox" />
              后端启动后自动登录已保存账号
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
              <input v-model="form.auto_receive_enabled" type="checkbox" />
              启用定时收件
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">收件间隔（分钟）</span>
              <input v-model.number="form.auto_receive_interval_minutes" class="input" type="number" min="5" />
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300">
              <input v-model="form.token_refresh_enabled" type="checkbox" />
              启用定时 Token 刷新
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">Token 刷新间隔（分钟）</span>
              <input v-model.number="form.token_refresh_interval_minutes" class="input" type="number" min="5" />
            </label>
          </div>

          <div class="card-footer space-y-4">
            <div class="flex flex-wrap gap-3">
              <button class="btn btn-secondary" :disabled="runningTokenRefresh" @click="handleRunTokenRefresh">
                {{ runningTokenRefresh ? '执行中...' : '立即全量刷新 Token' }}
              </button>
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium text-gray-900 dark:text-white">Token 刷新历史</div>
              <div class="max-h-72 space-y-2 overflow-y-auto">
                <div
                  v-for="item in tokenRefreshHistory"
                  :key="item.id"
                  class="rounded-xl border border-gray-100 px-3 py-2 text-xs dark:border-dark-700"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-medium text-gray-900 dark:text-white">{{ item.created_at }}</span>
                    <span class="text-gray-500 dark:text-dark-400">{{ item.trigger_source }}</span>
                  </div>
                  <div class="mt-1 text-gray-500 dark:text-dark-400">
                    成功 {{ item.payload.success_count || 0 }} / 失败 {{ item.payload.failed_count || 0 }}
                  </div>
                </div>
                <div v-if="!tokenRefreshHistory.length" class="text-xs text-gray-500 dark:text-dark-400">
                  暂无刷新历史
                </div>
              </div>
            </div>
          </div>
        </section>

        <section v-else-if="currentSection === 'backup'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">备份</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              管理自动备份、完整备份 ZIP 及恢复流程。
            </p>
          </div>

          <div class="card-body grid gap-5 md:grid-cols-2">
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-dark-300 md:col-span-2">
              <input v-model="form.backup_enabled" type="checkbox" />
              启用定期备份
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">备份间隔（分钟）</span>
              <input v-model.number="form.backup_interval_minutes" class="input" type="number" min="10" />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">最大保留份数</span>
              <input v-model.number="form.backup_keep_count" class="input" type="number" min="1" />
            </label>
            <label class="space-y-2 md:col-span-2">
              <span class="input-label mb-0">备份目录</span>
              <input v-model="form.backup_directory" class="input" type="text" />
            </label>
          </div>

          <div class="card-footer space-y-4">
            <div class="flex flex-wrap gap-3">
              <button class="btn btn-secondary" :disabled="runningBackup" @click="handleRunBackup">
                {{ runningBackup ? '执行中...' : '立即备份账号' }}
              </button>
              <button class="btn btn-secondary" @click="restoreBackupInput?.click()">恢复备份</button>
              <input
                ref="restoreBackupInput"
                class="hidden"
                type="file"
                accept=".zip,application/zip"
                @change="handleRestoreBackupFile"
              />
            </div>
            <div class="space-y-2 text-xs leading-6 text-gray-500 dark:text-dark-400">
              <p>完整备份会生成一个 ZIP，内含账号明文备份、结构化账号备份和系统设置备份。</p>
              <p>恢复时不会恢复邮件缓存、正文缓存和已读状态，只恢复账号与设置，并自动重新登录。</p>
            </div>
          </div>
        </section>

        <section v-else class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">安全</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              修改后台管理员账号与登录密码。保存后当前会话会自动切换到新账号。
            </p>
          </div>

          <div class="card-body grid gap-5 md:grid-cols-2">
            <label class="space-y-2 md:col-span-2">
              <span class="input-label mb-0">管理员账号</span>
              <input v-model.trim="securityForm.email" class="input" type="email" autocomplete="username" />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">当前密码</span>
              <input
                v-model="securityForm.currentPassword"
                class="input"
                type="password"
                autocomplete="current-password"
                placeholder="请输入当前登录密码"
              />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">新密码</span>
              <input
                v-model="securityForm.newPassword"
                class="input"
                type="password"
                autocomplete="new-password"
                placeholder="大于 12 位，包含大小写和数字"
              />
            </label>
            <label class="space-y-2">
              <span class="input-label mb-0">确认新密码</span>
              <input
                v-model="securityForm.confirmPassword"
                class="input"
                type="password"
                autocomplete="new-password"
                placeholder="再次输入新密码"
              />
            </label>
          </div>

          <div class="card-footer flex flex-wrap items-center gap-3">
            <button class="btn btn-primary" :disabled="savingSecurity" @click="handleSaveSecurity">
              {{ savingSecurity ? '保存中...' : '保存安全设置' }}
            </button>
            <div class="text-xs text-gray-500 dark:text-dark-400">
              密码必须大于 12 位，并同时包含大写字母、小写字母和数字。
            </div>
          </div>
        </section>

        <section v-if="currentSection === 'security'" class="card">
          <div class="card-header">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">API Token</h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-dark-400">
              为外部系统创建 API Key。完整密钥只会在创建后显示一次，请立即复制保存。
            </p>
          </div>

          <div class="card-body space-y-5">
            <div
              v-if="createdApiToken"
              class="rounded-2xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-800 dark:border-cyan-900/50 dark:bg-cyan-900/20 dark:text-cyan-200"
            >
              <div class="font-semibold">新的 API Key 已生成，只显示一次</div>
              <div class="mt-3 flex gap-2">
                <input class="input font-mono text-xs" :value="createdApiToken" readonly />
                <button class="btn btn-secondary" @click="copyApiToken">复制</button>
              </div>
            </div>

            <div class="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
              <label class="space-y-2">
                <span class="input-label mb-0">Token 名称</span>
                <input v-model.trim="apiTokenForm.name" class="input" type="text" placeholder="例如：外部查码服务" />
              </label>
              <div class="space-y-2">
                <span class="input-label mb-0">权限范围</span>
                <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  <label
                    v-for="scope in availableApiScopes"
                    :key="scope"
                    class="flex items-start gap-2 rounded-xl border border-gray-200 px-3 py-2 text-xs text-gray-700 dark:border-dark-700 dark:text-dark-200"
                  >
                    <input v-model="apiTokenForm.scopes" :value="scope" type="checkbox" />
                    <span>
                      <span class="block font-mono">{{ scope }}</span>
                      <span class="mt-0.5 block text-gray-500 dark:text-dark-400">{{ apiScopeLabels[scope] || 'API 权限' }}</span>
                    </span>
                  </label>
                </div>
              </div>
            </div>

            <button class="btn btn-primary" :disabled="creatingApiToken" @click="handleCreateApiToken">
              {{ creatingApiToken ? '创建中...' : '创建 API Key' }}
            </button>

            <div class="overflow-x-auto rounded-2xl border border-gray-100 dark:border-dark-700">
              <table class="min-w-full text-left text-sm">
                <thead class="bg-gray-50 text-xs text-gray-500 dark:bg-dark-800 dark:text-dark-400">
                  <tr>
                    <th class="px-4 py-3">名称</th>
                    <th class="px-4 py-3">权限</th>
                    <th class="px-4 py-3">状态</th>
                    <th class="px-4 py-3">最后使用</th>
                    <th class="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100 dark:divide-dark-700">
                  <tr v-for="item in apiTokens" :key="item.id">
                    <td class="px-4 py-3 font-medium text-gray-900 dark:text-white">{{ item.name }}</td>
                    <td class="max-w-md px-4 py-3">
                      <div class="flex flex-wrap gap-1">
                        <span
                          v-for="scope in item.scopes"
                          :key="scope"
                          class="rounded-full bg-gray-100 px-2 py-0.5 font-mono text-[10px] text-gray-600 dark:bg-dark-700 dark:text-dark-300"
                        >
                          {{ scope }}
                        </span>
                      </div>
                    </td>
                    <td class="px-4 py-3">
                      <span
                        class="rounded-full px-2 py-0.5 text-xs"
                        :class="item.enabled ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300' : 'bg-gray-100 text-gray-500 dark:bg-dark-700 dark:text-dark-400'"
                      >
                        {{ item.enabled ? '启用' : '已禁用' }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-xs text-gray-500 dark:text-dark-400">
                      {{ item.last_used_at || '从未使用' }}
                      <span v-if="item.last_used_ip"> / {{ item.last_used_ip }}</span>
                    </td>
                    <td class="px-4 py-3">
                      <button
                        class="btn btn-danger btn-sm"
                        :disabled="!item.enabled || disablingApiTokenId === item.id"
                        @click="handleDisableApiToken(item.id)"
                      >
                        {{ disablingApiTokenId === item.id ? '禁用中...' : '禁用' }}
                      </button>
                    </td>
                  </tr>
                  <tr v-if="!apiTokens.length">
                    <td class="px-4 py-6 text-center text-sm text-gray-500 dark:text-dark-400" colspan="5">
                      暂无 API Token
                    </td>
                  </tr>
                </tbody>
              </table>
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
import { updateAdminCredentials } from '@/api/auth'
import {
  createApiToken,
  disableApiToken,
  getApiTokens,
  getSettings,
  getTokenRefreshHistory,
  restoreAccountBackup,
  runAccountBackup,
  runTokenRefresh,
  saveSettings,
  sendTestNotification,
  type ApiTokenItem,
} from '@/api/dashboard'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import type { AppSettings } from '@/types'

const route = useRoute()
const router = useRouter()
const sections = [
  { key: 'import', label: '导入规则' },
  { key: 'reading', label: '阅读偏好' },
  { key: 'oauth', label: '微软授权' },
  { key: 'notifications', label: '通知' },
  { key: 'refresh', label: '邮箱刷新' },
  { key: 'backup', label: '备份' },
  { key: 'security', label: '安全' },
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
  telegram_mail_groups: [],
  telegram_mail_summary_minutes: 60,
  telegram_notify_backup: false,
})

const saving = ref(false)
const savingSecurity = ref(false)
const testingNotification = ref(false)
const runningTokenRefresh = ref(false)
const runningBackup = ref(false)
const newDelimiter = ref('')
const toastStore = useToastStore()
const authStore = useAuthStore()
const restoreBackupInput = ref<HTMLInputElement | null>(null)
const tokenRefreshHistory = ref<
  Array<{
    id: number
    created_at: string
    trigger_source: string
    payload: Record<string, any>
  }>
>([])
const apiTokens = ref<ApiTokenItem[]>([])
const availableApiScopes = ref<string[]>([])
const createdApiToken = ref('')
const creatingApiToken = ref(false)
const disablingApiTokenId = ref('')
const apiTokenForm = reactive({
  name: '',
  scopes: ['read:accounts', 'read:mails'],
})
const apiScopeLabels: Record<string, string> = {
  'read:accounts': '查询邮箱、分组、标签、队列、版本',
  'read:mails': '查询邮件、详情和验证码',
  'write:accounts': '导入账号',
  'write:taxonomy': '管理分组、标签和旗标',
  'task:receive': '执行收件任务',
  'task:login': '执行重新登录任务',
  'task:backup': '执行备份',
  'notify:send': '发送手动通知',
  'read:logs': '查询日志',
  'admin:tokens': '预留管理权限',
}

const currentSection = computed(() => {
  const section = String(route.query.section || 'import')
  return sections.some((item) => item.key === section) ? section : 'import'
})

const groupOptions = computed(() => ['未分组', ...form.custom_groups.map((item) => item.name).filter((name) => name)])
const notificationGroupOptions = computed(() => [
  { value: '__all__', label: '全部邮箱' },
  ...groupOptions.value.map((group) => ({ value: group, label: group })),
])

const securityForm = reactive({
  email: '',
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

onMounted(async () => {
  const response = await getSettings()
  Object.assign(form, response.data)
  securityForm.email = authStore.user?.email || ''
  await loadTokenRefreshHistory()
  await loadApiTokens()
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

function validateSecurityForm() {
  const email = securityForm.email.trim().toLowerCase()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    toastStore.push('管理员账号必须为邮箱格式', 'error')
    return null
  }
  if (!securityForm.currentPassword) {
    toastStore.push('请输入当前密码', 'error')
    return null
  }
  if (securityForm.newPassword.length <= 12) {
    toastStore.push('新密码长度必须大于 12 位', 'error')
    return null
  }
  if (!/[a-z]/.test(securityForm.newPassword)) {
    toastStore.push('新密码必须包含小写字母', 'error')
    return null
  }
  if (!/[A-Z]/.test(securityForm.newPassword)) {
    toastStore.push('新密码必须包含大写字母', 'error')
    return null
  }
  if (!/\d/.test(securityForm.newPassword)) {
    toastStore.push('新密码必须包含数字', 'error')
    return null
  }
  if (securityForm.newPassword !== securityForm.confirmPassword) {
    toastStore.push('两次输入的新密码不一致', 'error')
    return null
  }
  return email
}

async function handleSaveSecurity() {
  const email = validateSecurityForm()
  if (!email) return
  savingSecurity.value = true
  try {
    const response = await updateAdminCredentials({
      email,
      current_password: securityForm.currentPassword,
      new_password: securityForm.newPassword,
    })
    authStore.setSession(response.data.token, response.data.user)
    securityForm.email = response.data.user.email
    securityForm.currentPassword = ''
    securityForm.newPassword = ''
    securityForm.confirmPassword = ''
    toastStore.push(response.message, 'success')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '安全设置保存失败', 'error')
  } finally {
    savingSecurity.value = false
  }
}

async function loadApiTokens() {
  try {
    const response = await getApiTokens()
    apiTokens.value = response.data.items
    availableApiScopes.value = response.data.available_scopes.filter((scope) => scope !== 'admin:tokens')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '加载 API Token 失败', 'error')
  }
}

async function handleCreateApiToken() {
  if (!apiTokenForm.name.trim()) {
    toastStore.push('请输入 Token 名称', 'error')
    return
  }
  if (!apiTokenForm.scopes.length) {
    toastStore.push('请至少选择一个权限', 'error')
    return
  }
  creatingApiToken.value = true
  try {
    const response = await createApiToken({
      name: apiTokenForm.name.trim(),
      scopes: apiTokenForm.scopes,
    })
    createdApiToken.value = response.data.token
    apiTokenForm.name = ''
    apiTokenForm.scopes = ['read:accounts', 'read:mails']
    await loadApiTokens()
    toastStore.push(response.message, 'success')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '创建 API Key 失败', 'error')
  } finally {
    creatingApiToken.value = false
  }
}

async function handleDisableApiToken(tokenId: string) {
  disablingApiTokenId.value = tokenId
  try {
    const response = await disableApiToken(tokenId)
    toastStore.push(response.message, 'success')
    await loadApiTokens()
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '禁用 API Token 失败', 'error')
  } finally {
    disablingApiTokenId.value = ''
  }
}

async function copyApiToken() {
  if (!createdApiToken.value) return
  await navigator.clipboard.writeText(createdApiToken.value)
  toastStore.push('API Key 已复制', 'success')
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

async function loadTokenRefreshHistory() {
  try {
    const response = await getTokenRefreshHistory()
    tokenRefreshHistory.value = response.data.items
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '加载刷新历史失败', 'error')
  }
}

async function handleRunTokenRefresh() {
  runningTokenRefresh.value = true
  try {
    const response = await runTokenRefresh()
    toastStore.push(response.message, 'success')
    await loadTokenRefreshHistory()
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || 'Token 刷新失败', 'error')
  } finally {
    runningTokenRefresh.value = false
  }
}

async function handleRunBackup() {
  runningBackup.value = true
  try {
    const response = await runAccountBackup()
    toastStore.push(`${response.message}：${response.data.path}`, 'success')
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '账号备份失败', 'error')
  } finally {
    runningBackup.value = false
  }
}

async function handleRestoreBackupFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const response = await restoreAccountBackup(file)
    toastStore.push(
      `${response.message}：恢复 ${response.data.accounts} 个账号，${response.data.custom_groups} 个分组，${response.data.custom_tags} 个标签`,
      'success',
    )
  } catch (error: any) {
    toastStore.push(error?.response?.data?.detail || '恢复备份失败', 'error')
  }
}
</script>
