import { apiClient, type ApiResponse } from './client'
import type { AuthUser } from '@/types'

export interface LoginResult {
  token: string
  user: AuthUser
}

export async function login(email: string, password: string) {
  const { data } = await apiClient.post<ApiResponse<LoginResult>>('/auth/login', {
    email,
    password,
  })
  return data
}

export async function fetchMe() {
  const { data } = await apiClient.get<ApiResponse<{ user: AuthUser }>>('/auth/me')
  return data
}
