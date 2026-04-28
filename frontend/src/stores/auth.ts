import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchMe, login as loginRequest } from '@/api/auth'
import type { AuthUser } from '@/types'

const TOKEN_KEY = 'easymail-token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<AuthUser | null>(null)
  const ready = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  async function initialize() {
    if (!token.value) {
      ready.value = true
      return
    }
    try {
      const response = await fetchMe()
      user.value = response.data.user
    } catch {
      logout()
    } finally {
      ready.value = true
    }
  }

  async function login(email: string, password: string) {
    const response = await loginRequest(email, password)
    setSession(response.data.token, response.data.user)
  }

  function setSession(nextToken: string, nextUser: AuthUser) {
    token.value = nextToken
    user.value = nextUser
    localStorage.setItem(TOKEN_KEY, token.value)
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  return {
    token,
    user,
    ready,
    isAuthenticated,
    initialize,
    login,
    setSession,
    logout,
  }
})
