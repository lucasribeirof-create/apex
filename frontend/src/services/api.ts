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

// Interceptor global de resposta — loga erros de servidor e de rede
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const url = error?.config?.url || ''
    if (!error?.response || error?.code === 'ERR_NETWORK') {
      console.error(`[APEX] Sem resposta do servidor: ${url}`)
    } else if (status >= 500) {
      console.error(`[APEX] Erro ${status} no servidor: ${url}`, error?.response?.data)
    } else if (status === 401 || status === 403) {
      console.warn(`[APEX] Acesso negado (${status}): ${url}`)    } else if (status === 400) {
      const detail = error?.response?.data?.detail ?? ''
      if (detail === 'Usuário não encontrado') {
        // Store tem userId obsoleto — limpa e manda pro seletor
        useStore.getState().reset()
        if (!window.location.pathname.includes('/selecionar') && !window.location.pathname.includes('/onboarding')) {
          window.location.replace('/selecionar')
        }
      }    } else if (status === 422) {
      // Erro de validação Pydantic — detalhe útil no console
      console.warn(`[APEX] Dados inválidos (422): ${url}`, error?.response?.data?.detail)
    }
    return Promise.reject(error)
  },
)

export default api
