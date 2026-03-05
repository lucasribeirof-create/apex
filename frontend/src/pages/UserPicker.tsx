import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, TrendingUp, ChevronRight, Loader2, Trash2, BrainCircuit, Settings } from 'lucide-react'
import { useStore, StrategyType } from '@/store/useStore'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

interface UserRecord {
  id: number
  name: string
  estrategia: StrategyType | null
  patrimonio: number | null
  created_at: string
}

const STRATEGY_META: Record<string, { color: string; bg: string; label: string }> = {
  CORE:   { color: '#94a3b8', bg: 'rgba(148,163,184,0.08)',  label: 'APEX CORE' },
  ALPHA:  { color: '#00E676', bg: 'rgba(0,230,118,0.08)',    label: 'APEX ALPHA' },
  RENDA:  { color: '#00BFA5', bg: 'rgba(0,191,165,0.08)',    label: 'APEX RENDA' },
  CUSTOM: { color: '#FF9800', bg: 'rgba(255,152,0,0.08)',    label: 'APEX CUSTOM' },
}

const fmt = (n: number | null) =>
  n == null ? '—' : `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

export default function UserPickerPage() {
  const { setUser, setStrategy, setPortfolioAtivo, setPortfolioId, setPortfolios, userId: activeUserId } = useStore()
  const navigate = useNavigate()
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [aiInfo, setAiInfo] = useState<{ provider: string; model: string; configured: boolean } | null>(null)

  const load = () => {
    setLoading(true)
    api.get('/onboarding/usuarios')
      .then((r) => {
        setUsers(r.data)
        if (r.data.length === 0) navigate('/onboarding', { replace: true })
      })
      .catch(() => setUsers([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [navigate])

  // Busca info da IA configurada
  useEffect(() => {
    api.get('/settings/ai')
      .then(r => setAiInfo(r.data))
      .catch(() => setAiInfo(null))
  }, [])

  const selectUser = async (user: UserRecord) => {
    setUser(String(user.id), user.name)
    if (user.estrategia) setStrategy(user.estrategia)
    // Busca portfolio ativo para que o store tenha os dados corretos
    try {
      const rl = await api.get('/portfolio/listar', { headers: { 'x-user-id': String(user.id) } })
      setPortfolios(rl.data)
      const ativo = rl.data.find((p: any) => p.ativo) ?? rl.data[0]
      if (ativo) {
        setPortfolioAtivo(ativo)
        setPortfolioId(String(ativo.id))
      }
    } catch { /* silently proceed — portfolio will be loaded later */ }
    navigate('/briefing')
  }

  const handleDelete = async (e: React.MouseEvent, user: UserRecord) => {
    e.stopPropagation()
    if (!confirm(`Apagar a carteira "${user.name}"? Esta ação não pode ser desfeita.`)) return
    setDeletingId(user.id)
    try {
      await api.delete(`/onboarding/usuarios/${user.id}`)
    } catch (err: any) {
      if (err?.response?.status !== 404) {
        alert('Erro ao apagar. Tente novamente.')
        setDeletingId(null)
        return
      }
    }
    // Se era o usuário ativo, limpa o store
    if (activeUserId === String(user.id)) {
      useStore.getState().reset()
    }
    setDeletingId(null)
    load()
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#0a0e17' }}>
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <span className="text-lg font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <div>
            <h1 className="font-bold text-xl tracking-tight" style={{ color: '#f1f5f9' }}>APEX</h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>Manager</p>
          </div>
        </div>

        <div className="mb-6">
          <h2 className="text-lg font-bold mb-1" style={{ color: '#f1f5f9' }}>Selecionar carteira</h2>
          <p className="text-sm" style={{ color: '#64748b' }}>Escolha uma carteira existente ou crie uma nova.</p>
        </div>

        {loading ? (
          <div className="flex justify-center py-10">
            <Loader2 size={24} className="animate-spin" style={{ color: '#00E676' }} />
          </div>
        ) : (
          <AnimatePresence>
            <div className="space-y-3">
              {users.map((u, i) => {
                const meta = STRATEGY_META[u.estrategia ?? 'CORE'] ?? STRATEGY_META.CORE
                return (
                  <motion.div
                    key={u.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.06 }}
                    className="flex items-center gap-2"
                  >
                    <button
                      onClick={() => selectUser(u)}
                      className="flex-1 text-left p-4 rounded-xl flex items-center gap-4 transition-all group"
                      style={{ background: 'rgba(15,23,42,0.7)', border: `1px solid ${activeUserId === String(u.id) ? 'rgba(0,230,118,0.3)' : '#1e293b'}` }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(0,230,118,0.2)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = activeUserId === String(u.id) ? 'rgba(0,230,118,0.3)' : '#1e293b' }}
                    >
                      {/* Avatar */}
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                        style={{ background: meta.bg, border: `1px solid ${meta.color}22` }}>
                        <TrendingUp size={16} style={{ color: meta.color }} />
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm truncate" style={{ color: '#f1f5f9' }}>{u.name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs font-mono px-1.5 py-0.5 rounded"
                            style={{ background: meta.bg, color: meta.color }}>
                            {meta.label}
                          </span>
                          <span className="text-xs" style={{ color: '#475569' }}>{fmt(u.patrimonio)}</span>
                        </div>
                      </div>

                      <ChevronRight size={15} style={{ color: '#475569' }}
                        className="group-hover:text-green-400 transition-colors flex-shrink-0" />
                    </button>

                    {/* Delete button */}
                    <button
                      onClick={(e) => handleDelete(e, u)}
                      disabled={deletingId === u.id}
                      className="p-2.5 rounded-xl flex-shrink-0 transition-all"
                      style={{ background: 'rgba(255,82,82,0.08)', border: '1px solid rgba(255,82,82,0.15)', color: '#FF5252' }}
                      title="Apagar carteira"
                    >
                      {deletingId === u.id
                        ? <Loader2 size={14} className="animate-spin" />
                        : <Trash2 size={14} />}
                    </button>
                  </motion.div>
                )
              })}

              {/* New portfolio button */}
              <motion.button
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: users.length * 0.06 + 0.05 }}
                onClick={() => navigate('/onboarding')}
                className="w-full text-left p-4 rounded-xl flex items-center gap-4 transition-all"
                style={{ border: '1px dashed #1e293b', color: '#64748b' }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(0,230,118,0.25)'; e.currentTarget.style.color = '#00E676' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#1e293b'; e.currentTarget.style.color = '#64748b' }}
              >
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(0,230,118,0.04)', border: '1px dashed #1e293b' }}>
                  <Plus size={16} />
                </div>
                <span className="text-sm font-medium">Nova carteira</span>
              </motion.button>
            </div>
          </AnimatePresence>
        )}
      </div>

      {/* AI provider badge — bottom of screen */}
      {aiInfo && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2"
        >
          <button
            onClick={() => navigate('/configurar-ia')}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-full transition-all hover:scale-[1.02]"
            style={{
              background: 'rgba(15,23,42,0.85)',
              border: `1px solid ${aiInfo.configured ? 'rgba(170,0,255,0.25)' : 'rgba(255,82,82,0.3)'}`,
              backdropFilter: 'blur(12px)',
            }}
            title="Trocar provedor de IA"
          >
            <BrainCircuit size={14} style={{ color: aiInfo.configured ? '#AA00FF' : '#FF5252' }} />
            <span className="text-[11px] font-mono" style={{ color: aiInfo.configured ? '#c4b5fd' : '#fca5a5' }}>
              {aiInfo.configured
                ? `${aiInfo.provider.toUpperCase()} · ${aiInfo.model}`
                : 'IA não configurada'}
            </span>
            <Settings size={12} style={{ color: '#475569' }} />
          </button>
        </motion.div>
      )}
    </div>
  )
}
