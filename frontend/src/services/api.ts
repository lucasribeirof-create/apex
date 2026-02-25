import axios from 'axios'
import { useStore } from '@/store/useStore'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Automatically inject the active user id as a header so the backend
// can serve the correct portfolio without URL params on every call.
api.interceptors.request.use((config) => {
  const userId = useStore.getState().userId
  if (userId) {
    config.headers['x-user-id'] = userId
  }
  return config
})

export default api
