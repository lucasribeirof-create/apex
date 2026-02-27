import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, Activity, DollarSign, Calendar, BarChart2 } from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

const MODULE_LABELS: Record<string, { label: string; color: string }> = {
  etfs:       { label: 'ETFs',       color: '#00E676' },
  fiis:       { label: 'FIIs',       color: '#00BFA5' },
  renda_fixa: { label: 'Renda Fixa', color: '#1DE9B6' },
  momentum:   { label: 'Momentum',   color: '#64FFDA' },
  wheel:      { label: 'Wheel',      color: '#00B0FF' },
  alpha:      { label: 'Alpha',      color: '#AA00FF' },
  dividendos: { label: 'Dividendos', color: '#FFD740' },
  teses:      { label: 'Teses',      color: '#FF6D00' },
  caixa:      { label: 'Caixa',      color: '#475569' },
}

const REGIME_COLORS: Record<string, string> = {
  BULL: '#00E676',
  MISTO: '#FFD740',
  BEAR: '#FF5252',
}

function getDeviation(target: number, current: number) {
  const diff = current - target
  if (Math.abs(diff) <= 2) return { color: '#00E676', label: 'OK', bg: 'rgba(0, 230, 118, 0.08)' }
  if (Math.abs(diff) <= 5) return { color: '#FFD740', label: `${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`, bg: 'rgba(255, 215, 64, 0.08)' }
  return { color: '#FF5252', label: `${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`, bg: 'rgba(255, 82, 82, 0.08)' }
}

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtPct(v: number) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

export default function DashboardPage() {
  const { strategyType } = useStore()

  const [dash, setDash] = useState<any>(null)
  const [regime, setRegime] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [dashRes, regimeRes] = await Promise.all([
          api.get('/dashboard/'),
          api.get('/market/regime'),
        ])
        setDash(dashRes.data)
        setRegime(regimeRes.data)
      } catch (err) {
        console.error('Dashboard load error:', err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Dados derivados
  const patrimonio = dash?.patrimonio?.atual ?? 0
  const varDia = dash?.patrimonio?.var_dia_pct ?? 0
  const varMes = dash?.patrimonio?.var_mes_pct ?? null
  const totalPct = dash?.patrimonio?.total_pct ?? 0
  const rendaMes = dash?.macro?.renda_mes ?? null
  const selic = dash?.macro?.selic
  const ibov = dash?.macro?.ibov

  const alocacaoAtual: Record<string, number> = dash?.alocacao?.atual ?? {}
  const alocacaoAlvo: Record<string, number> = dash?.alocacao?.alvo ?? {}

  const allocationData = Object.entries(MODULE_LABELS)
    .filter(([key]) => alocacaoAlvo[key] != null)
    .map(([key, { label, color }]) => ({
      module: label,
      color,
      current: alocacaoAtual[key] ?? 0,
      target: alocacaoAlvo[key] ?? 0,
    }))

  const regimeNome: string = regime?.regime ?? dash?.regime ?? 'MISTO'
  const regimeColor = REGIME_COLORS[regimeNome] ?? '#FFD740'
  const regimeMotivo: string = regime?.motivo ?? '–'

  const metrics = [
    {
      label: 'Patrimônio Total',
      value: loading ? '–' : `R$ ${fmt(patrimonio)}`,
      change: loading ? '' : `${fmtPct(varDia)} hoje`,
      positive: varDia >= 0,
      icon: DollarSign,
    },
    {
      label: 'Retorno no Mês',
      value: loading ? '–' : (varMes != null ? fmtPct(varMes) : '–'),
      change: selic != null ? `Selic ${selic.toFixed(2)}% a.a.` : 'Selic –',
      positive: (varMes ?? 0) >= 0,
      icon: TrendingUp,
    },
    {
      label: 'Retorno Total',
      value: loading ? '–' : fmtPct(totalPct),
      change: ibov != null ? `IBOV ${fmtPct(ibov)}` : 'vs IBOV –',
      positive: totalPct >= 0,
      icon: Activity,
    },
    {
      label: 'Renda do Mês',
      value: rendaMes != null ? `R$ ${fmt(rendaMes)}` : '–',
      change: 'Dividendos + FIIs',
      positive: true,
      icon: Calendar,
    },
  ]

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#00E676', borderTopColor: 'transparent' }} />
          <span className="text-sm font-mono" style={{ color: '#64748b' }}>Carregando dashboard…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Dashboard</h1>
        <p className="text-sm mt-1" style={{ color: '#64748b' }}>
          {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
      </div>

      {/* RENDA Strategy: yield metrics */}
      {strategyType === 'RENDA' && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl p-5 space-y-4"
          style={{ background: 'rgba(0,191,165,0.04)', border: '1px solid rgba(0,191,165,0.15)' }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#00BFA5' }}>APEX RENDA — Métricas de Renda</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Renda Mensal Projetada', value: rendaMes != null ? `R$ ${fmt(rendaMes)}` : '–', sub: 'Dividendos + JCP + FIIs', color: '#00BFA5' },
              { label: 'Yield on Cost', value: '–', sub: 'Sobre preço médio', color: '#00BFA5' },
              { label: 'Cobertura da Meta', value: '–', sub: 'Aguardando meta configurada', color: '#FFD740' },
            ].map((item) => (
              <div key={item.label} className="rounded-lg p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <p className="text-xs font-mono uppercase tracking-wider mb-2" style={{ color: '#64748b' }}>{item.label}</p>
                <p className="text-xl font-bold font-data" style={{ color: item.color }}>{item.value}</p>
                <p className="text-xs mt-1" style={{ color: '#475569' }}>{item.sub}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        {metrics.map((m, i) => (
          <motion.div
            key={m.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="apex-card p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>{m.label}</span>
              <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 230, 118, 0.08)' }}>
                <m.icon size={15} style={{ color: '#00E676' }} />
              </div>
            </div>
            <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>{m.value}</p>
            <p className="text-xs mt-1" style={{ color: m.positive ? '#00E676' : '#FF5252' }}>{m.change}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Performance Chart */}
        <motion.div
          className="apex-card p-5 col-span-2"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PERFORMANCE DESDE O INÍCIO</h3>
          </div>
          <div className="flex flex-col items-center justify-center h-[200px] gap-3" style={{ color: '#475569' }}>
            <BarChart2 size={36} style={{ color: '#1e293b' }} />
            <p className="text-xs font-mono text-center" style={{ color: '#475569' }}>
              Histórico de performance em construção
              <br />
              <span style={{ color: '#334155' }}>Dados disponíveis após 1º mês de operação</span>
            </p>
          </div>
        </motion.div>

        {/* Allocation */}
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <h3 className="text-sm font-medium mb-5" style={{ color: '#94a3b8' }}>ALOCAÇÃO</h3>
          <div className="space-y-3">
            {allocationData.map((item) => {
              const dev = getDeviation(item.target, item.current)
              const barMax = Math.max(...allocationData.map(a => Math.max(a.current, a.target)), 5)
              return (
                <div key={item.module}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs" style={{ color: '#94a3b8' }}>{item.module}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{item.current}%</span>
                      <span
                        className="text-xs font-mono px-1.5 py-0.5 rounded"
                        style={{ color: dev.color, background: dev.bg }}
                      >
                        {dev.label}
                      </span>
                    </div>
                  </div>
                  <div className="allocation-bar">
                    <div className="allocation-fill" style={{ width: `${Math.min((item.current / barMax) * 100, 100)}%`, background: item.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </motion.div>
      </div>

      {/* Regime */}
      <motion.div
        className="apex-card p-4 flex items-center gap-3"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        <div className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ background: regimeColor }} />
        <span className="text-sm font-mono" style={{ color: regimeColor }}>{regimeNome}</span>
        <span className="text-sm" style={{ color: '#64748b' }}>{regimeMotivo}</span>
      </motion.div>
    </div>
  )
}
