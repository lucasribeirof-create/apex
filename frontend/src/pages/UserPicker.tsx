import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, TrendingUp, ChevronRight, Loader2 } from 'lucide-react'
import { useStore, StrategyType } from '@/store/useStore'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

interface UserRecord {
  id: number
  name: string
  nome_carteira?: string
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
  const { setUser, setStrategy, userId: activeUserId } = useStore()
  const navigate = useNavigate()
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)

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

  const selectUser = (user: UserRecord) => {
    setUser(String(user.id), user.name)
    if (user.estrategia) setStrategy(user.estrategia)
    navigate('/briefing')
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
                  <motion.button
                    key={u.id}
                    type="button"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.06 }}
                    onClick={() => selectUser(u)}
                    className="w-full text-left p-4 rounded-xl flex items-center gap-4 transition-all group"
                    style={{ background: 'rgba(15,23,42,0.7)', border: `1px solid ${activeUserId === String(u.id) ? 'rgba(0,230,118,0.3)' : '#1e293b'}` }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(0,230,118,0.2)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = activeUserId === String(u.id) ? 'rgba(0,230,118,0.3)' : '#1e293b' }}
                  >
                    {/* Avatar */}
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{ background: meta.bg, border: `1px solid ${meta.color}22` }}>
                      <TrendingUp size={16} style={{ color: meta.color }} />
                    </div>

                    {/* Info: nome da carteira (portfólio); nome do usuário fica implícito */}
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate" style={{ color: '#f1f5f9' }}>{u.nome_carteira ?? u.name}</p>
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
                  </motion.button>
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
    </div>
  )
}
