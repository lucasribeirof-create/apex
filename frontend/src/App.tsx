import { useState, useEffect } from 'react'
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

function App() {
  const { userId } = useStore()
  const isOnboarded = Boolean(userId)

  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null)

  useEffect(() => {
    api.get('/settings/ai')
      .then((r) => setAiConfigured(r.data.configured === true))
      .catch(() => setAiConfigured(false))
  }, [])

  // Aguarda a verificação inicial
  if (aiConfigured === null) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0a0e17' }}>
        <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#00E676 transparent transparent transparent' }} />
      </div>
    )
  }

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
            <Route path="*" element={<Navigate to="/selecionar" replace />} />
          </>
        ) : (
          <>
            {/* Rota de seleção de IA acessível mesmo estando logado (sem sidebar) */}
            <Route path="/configurar-ia" element={<AISetupPage />} />
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/briefing" element={<BriefingPage />} />
              <Route path="/positions" element={<PositionsPage />} />
              <Route path="/teses" element={<TesesPage />} />
              <Route path="/scanner" element={<ScannerPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/briefing" replace />} />
            </Route>
          </>
        )}
      </Routes>
    </BrowserRouter>
  )
}

export default App
