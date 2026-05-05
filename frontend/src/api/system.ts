import { apiClient, type ApiResponse } from './client'

export interface ReleaseInfo {
  name: string
  body: string
  published_at: string
  html_url: string
}

export interface VersionInfo {
  current_version: string
  latest_version: string
  has_update: boolean
  release_info: ReleaseInfo
  cached: boolean
  warning: string
  build_type: string
}

export interface UpdateResult {
  need_restart: boolean
  output?: string
}

export async function checkUpdates(force = false) {
  const response = await apiClient.get<ApiResponse<VersionInfo>>('/system/check-updates', {
    params: force ? { force: true } : undefined,
  })
  return response.data
}

export async function updateSystem() {
  const response = await apiClient.post<ApiResponse<UpdateResult>>('/system/update')
  return response.data
}

export async function restartSystem() {
  const response = await apiClient.post<ApiResponse<{ restarting: boolean }>>('/system/restart')
  return response.data
}
