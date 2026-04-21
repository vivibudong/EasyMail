import axios from 'axios'
import { apiBase } from '@/config'

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

export const apiClient = axios.create({
  baseURL: apiBase,
})

apiClient.interceptors.request.use((request) => {
  const token = localStorage.getItem('easymail-token')
  if (token) {
    request.headers.Authorization = `Bearer ${token}`
  }
  return request
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('easymail-token')
    }
    return Promise.reject(error)
  },
)
