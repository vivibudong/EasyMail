<template>
  <AuthLayout>
    <div class="space-y-6">
      <div class="text-center">
        <h2 class="text-2xl font-bold text-gray-900 dark:text-white">管理员登录</h2>
        <p class="mt-2 text-sm text-gray-500 dark:text-dark-400">
          使用 Compose 部署后的后台凭证进入多邮箱管理面板。
        </p>
      </div>

      <form class="space-y-5" @submit.prevent="handleLogin">
        <div>
          <label for="email" class="input-label">邮箱</label>
          <div class="relative">
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5">
              <Icon name="mail" size="md" class="text-gray-400 dark:text-dark-500" />
            </div>
            <input
              id="email"
              v-model="form.email"
              class="input pl-11"
              type="email"
              autocomplete="email"
              required
              autofocus
              placeholder="输入管理员邮箱"
            />
          </div>
        </div>

        <div>
          <label for="password" class="input-label">密码</label>
          <div class="relative">
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5">
              <Icon name="lock" size="md" class="text-gray-400 dark:text-dark-500" />
            </div>
            <input
              id="password"
              v-model="form.password"
              class="input pl-11"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              required
              placeholder="输入管理员密码"
            />
            <button
              type="button"
              class="absolute inset-y-0 right-0 flex items-center px-3 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-dark-300"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
        </div>

        <div
          v-if="errorMessage"
          class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-900/20 dark:text-red-400"
        >
          {{ errorMessage }}
        </div>

        <button type="submit" :disabled="isLoading" class="btn btn-primary w-full">
          <span v-if="isLoading" class="spinner h-4 w-4"></span>
          <Icon v-else name="login" size="md" />
          {{ isLoading ? '登录中...' : '登录后台' }}
        </button>
      </form>

      <div class="text-center text-sm text-gray-500 dark:text-dark-400">
        首次部署后请先检查 `docker-compose.yml` 和 `.env` 中的管理员凭证。
      </div>
    </div>
  </AuthLayout>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '@/components/common/Icon.vue'
import AuthLayout from '@/components/layout/AuthLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const authStore = useAuthStore()
const toastStore = useToastStore()

const form = reactive({
  email: '',
  password: '',
})

const isLoading = ref(false)
const errorMessage = ref('')
const showPassword = ref(false)

async function handleLogin() {
  errorMessage.value = ''
  isLoading.value = true
  try {
    await authStore.login(form.email, form.password)
    toastStore.push('登录成功', 'success')
    await router.push('/dashboard')
  } catch (error: any) {
    errorMessage.value = error?.response?.data?.detail || '登录失败，请检查邮箱或密码'
  } finally {
    isLoading.value = false
  }
}
</script>
