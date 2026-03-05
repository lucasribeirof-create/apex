import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useStore } from '@/store/useStore'
import api from '@/services/api'
import AppLayout from '@/components/layout/AppLayout'
import OnboardingPage from '@/pages/Onboarding'
import UserPickerPage from '@/pages/UserPicker'
import DashboardPage from '@/pages/Dashboard'
import BriefingPage from '@/pages/Briefing'
import PositionsPage from '@/pages/Positions'
import ScannerPage from '@/pages/Scanner'
import ChatPage from '@/pages/Chat'
import SettingsPage from '@/pages/Settings'
import AISetupPage from '@/pages/AISetup'
import TesesPage from '@/pages/Teses'
import SetupSimuladaPage from '@/pages/SetupSimulada'
import SugestoesAlocacaoPage from '@/pages/SugestoesAlocacao'
import PerfilInvestidorPage from '@/pages/PerfilInvestidor'

type AppStatus = 'loading' | 'offline' | 'ai_missing' | 'ready'

function BackendOfflineScreen({ onRetry }: { onRetry: () => void }) {
  const [retrying, setRetrying] = useState(false)

  const handleRetry = async () => {
    setRetrying(true)
    await new Promise(r => setTimeout(r, 600))
    onRetry()
    setRetrying(false)
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: '#0a0e17' }}
    >
      <div className="text-center max-w-sm space-y-6">
        {/* Icon */}
        <div
          className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
          style={{ background: 'rgba(255,82,82,0.1)', border: '1px solid rgba(255,82,82,0.25)' }}
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF5252" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>

        {/* Title */}
        <div>
          <h1 className="text-xl font-bold mb-2" style={{ color: '#f1f5f9' }}>
            Servidor APEX offline
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: '#64748b' }}>
            O backend não está respondendo. Verifique se o servidor foi iniciado antes de abrir o app.
          </p>
        </div>

        {/* Steps */}
        <div
          className="rounded-xl p-4 text-left space-y-2"
          style={{ background: '#0d1117', border: '1px solid #1e293b' }}
        >
          <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#475569' }}>
            Como iniciar o servidor:
          </p>
          {[
            'Abra o terminal na pasta do projeto',
            'cd backend',
            'python -m uvicorn app.main:app --reload',
            'Aguarde "Application startup complete"',
          ].map((step, i) => (
            <div key={i} className="flex items-start gap-3">
              <span
                className="text-[10px] font-mono font-bold w-5 h-5 rounded flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676' }}
              >
                {i + 1}
              </span>
              <span
                className="text-xs font-mono"
                style={{ color: i === 0 ? '#94a3b8' : '#00E676', fontFamily: i > 0 ? 'monospace' : undefined }}
              >
                {step}
              </span>
            </div>
          ))}
        </div>

        {/* Retry */}
        <button
          onClick={handleRetry}
          disabled={retrying}
          className="w-full py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all"
          style={{
            background: 'rgba(0,230,118,0.1)',
            border: '1px solid rgba(0,230,118,0.25)',
            color: '#00E676',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(0,230,118,0.16)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(0,230,118,0.1)')}
        >
          {retrying ? (
            <>
              <div className="w-4 h-4 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: '#00E676 transparent transparent transparent' }} />
              Verificando...
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
              Tentar Novamente
            </>
          )}
        </button>

        <p className="text-[11px]" style={{ color: '#334155' }}>
          O app tenta reconectar automaticamente a cada 10 segundos.
        </p>
      </div>
    </div>
  )
}

function App() {
  const { userId } = useStore()
  const isOnboarded = Boolean(userId)

  const [status, setStatus] = useState<AppStatus>('loading')

  const checkBackend = useCallback(async () => {
    setStatus('loading')
    try {
      const r = await api.get('/settings/ai')
      setStatus(r.data.configured === true ? 'ready' : 'ai_missing')
    } catch (err: any) {
      // Distingue erro de rede (servidor offline) de outros erros
      const isNetworkError =
        err?.code === 'ERR_NETWORK' ||
        err?.message === 'Network Error' ||
        err?.code === 'ECONNREFUSED' ||
        !err?.response
      setStatus(isNetworkError ? 'offline' : 'ai_missing')
    }
  }, [])

  useEffect(() => {
    checkBackend()
  }, [checkBackend])

  // Auto-retry a cada 10s quando offline
  useEffect(() => {
    if (status !== 'offline') return
    const interval = setInterval(checkBackend, 10_000)
    return () => clearInterval(interval)
  }, [status, checkBackend])

  // Refresh de preços 1x ao abrir o app (fire-and-forget)
  useEffect(() => {
    if (status === 'ready' && isOnboarded) {
      api.post('/portfolio/refresh-prices').catch(() => {})
    }
  }, [status, isOnboarded])

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0a0e17' }}>
        <div className="text-center space-y-4">
          <div
            className="w-10 h-10 rounded-xl mx-auto flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}
          >
            <span className="text-sm font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin mx-auto" style={{ borderColor: '#00E676 transparent transparent transparent' }} />
        </div>
      </div>
    )
  }

  if (status === 'offline') {
    return <BackendOfflineScreen onRetry={checkBackend} />
  }

  const aiConfigured = status !== 'ai_missing'

  return (
    <BrowserRouter>
      <Routes>
        {/* IA não configurada → sempre vai para setup */}
        {!aiConfigured ? (
          <>
            <Route path="/configurar-ia" element={<AISetupPage />} />
            <Route path="*" element={<Navigate to="/configurar-ia" replace />} />
          </>
        ) : !isOnboarded ? (
          <>
            <Route path="/selecionar" element={<UserPickerPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/perfil-investidor" element={<PerfilInvestidorPage />} />
            <Route path="/configurar-ia" element={<AISetupPage />} />
            <Route path="*" element={<Navigate to="/selecionar" replace />} />
          </>
        ) : (
          <>
            {/* Rotas sem sidebar — acessíveis mesmo logado */}
            <Route path="/configurar-ia" element={<AISetupPage />} />
            {/* Onboarding acessível mesmo logado (ex: usuário recarrega durante a tela de escolha) */}
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/perfil-investidor" element={<PerfilInvestidorPage />} />
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/briefing" element={<BriefingPage />} />
              <Route path="/positions" element={<PositionsPage />} />
              <Route path="/teses" element={<TesesPage />} />
              <Route path="/scanner" element={<ScannerPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/setup-simulada" element={<SetupSimuladaPage />} />
              <Route path="/sugestoes-alocacao" element={<SugestoesAlocacaoPage />} />
              <Route path="*" element={<Navigate to="/briefing" replace />} />
            </Route>
          </>
        )}
      </Routes>
    </BrowserRouter>
  )
}

export default App

