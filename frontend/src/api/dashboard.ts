import { apiClient, type ApiResponse } from './client'
import type { AppSettings, BodyTask, DashboardState, MailItem } from '@/types'

export async function getDashboardState(accountEmail?: string) {
  const { data } = await apiClient.get<ApiResponse<DashboardState>>('/dashboard/state', {
    params: accountEmail ? { account_email: accountEmail } : undefined,
  })
  return data
}

export async function importAccounts(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<ApiResponse<{ imported: number; changed: number }>>(
    '/accounts/import',
    form,
  )
  return data
}

export async function receiveAccounts(payload: { emails: string[]; include_all?: boolean }) {
  const { data } = await apiClient.post<ApiResponse<{ queued: number }>>('/accounts/receive', {
    emails: payload.emails,
    include_all: payload.include_all ?? false,
  })
  return data
}

export async function reloginAccounts(payload: { emails: string[]; include_all?: boolean }) {
  const { data } = await apiClient.post<ApiResponse<{ queued: number }>>('/accounts/relogin', {
    emails: payload.emails,
    include_all: payload.include_all ?? false,
  })
  return data
}

export async function deleteAccounts(emails: string[]) {
  const { data } = await apiClient.post<ApiResponse<{ deleted: number }>>('/accounts/delete', {
    emails,
  })
  return data
}

export async function updateFlag(email: string, flagColor: string) {
  const { data } = await apiClient.patch<ApiResponse<Record<string, never>>>('/accounts/flag', {
    email,
    flag_color: flagColor,
  })
  return data
}

export async function createGroup(name: string) {
  const { data } = await apiClient.post<ApiResponse<{ custom_groups: Array<{ name: string; color: string; priority: number }> }>>('/groups', {
    name,
  })
  return data
}

export async function createGroupDetailed(payload: { name: string; color: string; priority: number }) {
  const { data } = await apiClient.post<ApiResponse<{ custom_groups: Array<{ name: string; color: string; priority: number }> }>>('/groups', payload)
  return data
}

export async function updateGroup(payload: { original_name: string; name: string; color: string; priority: number }) {
  const { data } = await apiClient.put<ApiResponse<{ custom_groups: Array<{ name: string; color: string; priority: number }> }>>('/groups', payload)
  return data
}

export async function deleteGroup(name: string) {
  const { data } = await apiClient.delete<ApiResponse<{ custom_groups: Array<{ name: string; color: string; priority: number }> }>>('/groups', {
    params: { name },
  })
  return data
}

export async function createTag(payload: { name: string; color: string; priority: number }) {
  const { data } = await apiClient.post<ApiResponse<{ custom_tags: Array<{ name: string; color: string; priority: number }> }>>('/tags', payload)
  return data
}

export async function updateTag(payload: { original_name: string; name: string; color: string; priority: number }) {
  const { data } = await apiClient.put<ApiResponse<{ custom_tags: Array<{ name: string; color: string; priority: number }> }>>('/tags', payload)
  return data
}

export async function deleteTag(name: string) {
  const { data } = await apiClient.delete<ApiResponse<{ custom_tags: Array<{ name: string; color: string; priority: number }> }>>('/tags', {
    params: { name },
  })
  return data
}

export async function assignAccountGroup(email: string, groupName: string) {
  const { data } = await apiClient.patch<ApiResponse<Record<string, never>>>('/accounts/group', {
    email,
    group_name: groupName,
  })
  return data
}

export async function setAccountTags(email: string, tags: string[]) {
  const { data } = await apiClient.patch<ApiResponse<{ tags: string[] }>>('/accounts/tags', {
    email,
    tags,
  })
  return data
}

export async function getAccountDetail(email: string) {
  const { data } = await apiClient.get<
    ApiResponse<{
      account: {
        email: string
        password: string
        auth_code_or_client_id: string
        token: string
        imap_host: string
        imap_port: number
        group_name: string
        flag_color: string
        tags: string[]
      }
    }>
  >('/accounts/detail', {
    params: { email },
  })
  return data
}

export async function updateAccount(payload: {
  original_email: string
  email: string
  password: string
  auth_code_or_client_id: string
  token: string
  imap_host: string
  imap_port: number
  group_name: string
  flag_color: string
  tags: string[]
}) {
  const { data } = await apiClient.put<ApiResponse<{ account: unknown }>>('/accounts', payload)
  return data
}

export async function startGraphReauth(email: string) {
  const { data } = await apiClient.post<
    ApiResponse<{
      session_id: string
      email: string
      client_id: string
      user_code: string
      verification_uri: string
      expires_in: number
      interval: number
      status: string
      message: string
    }>
  >('/accounts/graph-reauth/start', { email })
  return data
}

export async function getGraphReauthStatus(sessionId: string) {
  const { data } = await apiClient.get<
    ApiResponse<{
      session_id: string
      email: string
      client_id: string
      user_code: string
      verification_uri: string
      expires_in: number
      interval: number
      status: string
      message: string
    }>
  >('/accounts/graph-reauth/status', {
    params: { session_id: sessionId },
  })
  return data
}

export async function openMail(localKey: string) {
  const { data } = await apiClient.post<
    ApiResponse<{
      mail: MailItem
      body_task: BodyTask
    }>
  >('/mails/open', { local_key: localKey })
  return data
}

export async function toggleMailStar(localKey: string, isStarred?: boolean) {
  const { data } = await apiClient.patch<ApiResponse<{ is_starred: boolean }>>('/mails/star', {
    local_key: localKey,
    is_starred: isStarred,
  })
  return data
}

export async function getBodyStatus(localKey: string) {
  const { data } = await apiClient.get<
    ApiResponse<{
      mail: MailItem
      body_task: BodyTask
    }>
  >('/mails/body-status', {
    params: { local_key: localKey },
  })
  return data
}

export async function getSettings() {
  const { data } = await apiClient.get<ApiResponse<AppSettings>>('/settings')
  return data
}

export async function saveSettings(settings: AppSettings) {
  const { data } = await apiClient.put<ApiResponse<AppSettings>>('/settings', settings)
  return data
}

export async function runTokenRefresh() {
  const { data } = await apiClient.post<
    ApiResponse<{
      total: number
      success_count: number
      failed_count: number
      results: Array<{
        email: string
        success: boolean
        imap: string
        graph: string
      }>
    }>
  >('/token-refresh/run')
  return data
}

export async function getTokenRefreshHistory(limit = 20) {
  const { data } = await apiClient.get<
    ApiResponse<{
      items: Array<{
        id: number
        created_at: string
        trigger_source: string
        payload: Record<string, unknown>
      }>
    }>
  >('/token-refresh/history', {
    params: { limit },
  })
  return data
}

export async function exportAccounts(options?: { groupName?: string; emails?: string[] }) {
  const response = await apiClient.get('/accounts/export', {
    params: {
      group_name: options?.groupName || '__all__',
      emails: options?.emails?.join(',') || '',
    },
    responseType: 'blob',
  })
  return response
}

export async function runAccountBackup() {
  const { data } = await apiClient.post<
    ApiResponse<{
      path: string
      retained: number
      trigger_source: string
    }>
  >('/backup/run')
  return data
}

export async function getLogs(options?: {
  category?: string
  level?: string
  keyword?: string
  limit?: number
}) {
  const { data } = await apiClient.get<
    ApiResponse<{
      items: Array<{
        id: number
        created_at: string
        level: string
        category: string
        action: string
        subject: string
        message: string
        detail: unknown
      }>
    }>
  >('/logs', {
    params: {
      category: options?.category || '',
      level: options?.level || '',
      keyword: options?.keyword || '',
      limit: options?.limit || 200,
    },
  })
  return data
}
