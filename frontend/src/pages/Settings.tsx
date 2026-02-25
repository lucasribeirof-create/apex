import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Trash2, AlertTriangle, X, Bot } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

export default function SettingsPage() {
  const { userId, userName, reset } = useStore()
  const navigate = useNavigate()

  // AI provider info
  const [aiInfo, setAiInfo] = useState<{ provider: string; model: string; key_hint: string } | null>(null)

  useEffect(() => {
    api.get('/settings/ai').then((r) => setAiInfo(r.data)).catch(() => null)
  }, [])

  const handleChangeAI = () => {
    window.location.replace('/configurar-ia')
  }

  // Step 0 = idle, 1 = first confirm, 2 = type name confirm
  const [deleteStep, setDeleteStep] = useState<0 | 1 | 2>(0)
  const [nameInput, setNameInput] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const handleDeleteStart = () => {
    setDeleteStep(1)
    setNameInput('')
    setError('')
  }

  const handleDeleteConfirm1 = () => {
    setDeleteStep(2)
  }

  const handleDeleteFinal = async () => {
    if (nameInput.trim().toLowerCase() !== (userName ?? '').toLowerCase()) {
      setError('Nome não confere. Digite exatamente como aparece acima.')
      return
    }
    setDeleting(true)
    setError('')
    try {
      await api.delete(`/onboarding/usuarios/${userId}`)
      reset()
      navigate('/selecionar', { replace: true })
    } catch {
      setError('Erro ao apagar carteira. Tente novamente.')
      setDeleting(false)
    }
  }

  const handleCancel = () => {
    setDeleteStep(0)
    setNameInput('')
    setError('')
  }

  return (
    <div className="p-8 max-w-xl">
      {/* Header */}
      <div className="flex items-center gap-2 mb-8">
        <Settings size={18} style={{ color: '#00E676' }} />
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Configurações</h1>
      </div>

      {/* Current portfolio info */}
      <div className="apex-card p-5 mb-8">
        <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
          Carteira ativa
        </p>
        <p className="text-base font-semibold" style={{ color: '#f1f5f9' }}>{userName}</p>
        <p className="text-sm mt-0.5" style={{ color: '#475569' }}>ID #{userId}</p>
      </div>

      {/* AI provider */}
      <div className="apex-card p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Bot size={15} style={{ color: '#64748b' }} />
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Motor de IA</p>
        </div>
        {aiInfo ? (
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold capitalize" style={{ color: '#f1f5f9' }}>
                {aiInfo.provider === 'gemini' ? 'Google Gemini' : aiInfo.provider === 'anthropic' ? 'Claude (Anthropic)' : 'GPT-4o Mini'}
              </p>
              <p className="text-xs font-mono mt-0.5" style={{ color: '#475569' }}>
                {aiInfo.model} · chave {aiInfo.key_hint}
              </p>
            </div>
            <button
              onClick={handleChangeAI}
              className="px-3 py-1.5 rounded-lg text-xs font-medium flex-shrink-0 transition-all"
              style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#334155' }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#1e293b' }}
            >
              Trocar IA
            </button>
          </div>
        ) : (
          <p className="text-sm" style={{ color: '#475569' }}>Carregando...</p>
        )}
      </div>

      {/* Danger zone */}
      <div className="rounded-xl p-5" style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.15)' }}>
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle size={15} style={{ color: '#ef4444' }} />
          <p className="text-sm font-semibold uppercase tracking-wider" style={{ color: '#ef4444' }}>Zona de perigo</p>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: '#f1f5f9' }}>Apagar esta carteira</p>
            <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
              Remove permanentemente o usuário, portfólio, todas as posições e o histórico de briefings.
              Esta ação não pode ser desfeita.
            </p>
          </div>
          {deleteStep === 0 && (
            <button
              onClick={handleDeleteStart}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium flex-shrink-0 transition-all"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.15)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
            >
              <Trash2 size={14} />
              Apagar
            </button>
          )}
        </div>

        {/* Step 1 — first confirmation */}
        <AnimatePresence>
          {deleteStep === 1 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                <p className="text-sm" style={{ color: '#f1f5f9' }}>
                  Tem certeza? Todos os dados de <span className="font-semibold" style={{ color: '#ef4444' }}>{userName}</span> serão apagados para sempre.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteConfirm1}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                    style={{ background: '#ef4444', color: '#fff' }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = '#dc2626' }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = '#ef4444' }}
                  >
                    Sim, continuar
                  </button>
                  <button
                    onClick={handleCancel}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                </div>
              </div>
            </motion.div>
          )}

          {/* Step 2 — type name to confirm */}
          {deleteStep === 2 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
                <p className="text-sm" style={{ color: '#f1f5f9' }}>
                  Para confirmar, digite o nome da carteira:{' '}
                  <span className="font-mono font-semibold" style={{ color: '#ef4444' }}>{userName}</span>
                </p>
                <input
                  autoFocus
                  value={nameInput}
                  onChange={(e) => { setNameInput(e.target.value); setError('') }}
                  onKeyDown={(e) => e.key === 'Enter' && handleDeleteFinal()}
                  placeholder={`Digite "${userName}"`}
                  className="apex-input w-full text-sm"
                  style={{ borderColor: error ? 'rgba(239,68,68,0.5)' : undefined }}
                />
                {error && (
                  <p className="text-xs" style={{ color: '#ef4444' }}>{error}</p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteFinal}
                    disabled={deleting || !nameInput.trim()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                    style={{
                      background: deleting || !nameInput.trim() ? '#1e293b' : '#ef4444',
                      color: deleting || !nameInput.trim() ? '#475569' : '#fff',
                      cursor: deleting || !nameInput.trim() ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <Trash2 size={13} />
                    {deleting ? 'Apagando...' : 'Apagar definitivamente'}
                  </button>
                  <button
                    onClick={handleCancel}
                    disabled={deleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
