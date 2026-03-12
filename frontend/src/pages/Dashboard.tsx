import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  TrendingUp, DollarSign, Globe, Calendar,
  FileText, AlertTriangle, RefreshCw, Zap, ArrowUpRight,
  ArrowDownRight, Crosshair
} from 'lucide-react'
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

function fmtR$(v: number) {
  return `R$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Skeleton({ className = '', h = 'h-24' }: { className?: string; h?: string }) {
  return (
    <div className={`apex-card ${h} ${className} animate-pulse`} style={{ background: 'rgba(30,41,59,0.5)' }}>
      <div className="p-5 space-y-3">
        <div className="h-3 w-24 rounded" style={{ background: '#1e293b' }} />
        <div className="h-6 w-32 rounded" style={{ background: '#1e293b' }} />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { strategyType } = useStore()

  const [dash, setDash] = useState<any>(null)
  const [regime, setRegime] = useState<any>(null)
  const [macroData, setMacroData] = useState<any>(null)
  const [tesesData, setTesesData] = useState<any>(null)
  const [perfData, setPerfData] = useState<any>(null)
  const [dividendosData, setDividendosData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [v2Loading, setV2Loading] = useState({ macro: true, teses: true, perf: true, divs: true })

  async function loadDashboard() {
    setLoading(true)
    setError(null)
    setV2Loading({ macro: true, teses: true, perf: true, divs: true })
    try {
      const dashRes = await api.get('/dashboard/')
      setDash(dashRes.data)

      // Regime — não bloqueia o dashboard se falhar
      api.get('/market/regime').then(r => setRegime(r.data)).catch(e => console.warn('Regime:', e))

      // V2 endpoints — load in background
      api.get('/dashboard/macro').then(r => setMacroData(r.data)).catch(e => console.warn('Dashboard macro:', e)).finally(() => setV2Loading(s => ({ ...s, macro: false })))
      api.get('/dashboard/teses').then(r => setTesesData(r.data)).catch(e => console.warn('Dashboard teses:', e)).finally(() => setV2Loading(s => ({ ...s, teses: false })))
      api.get('/dashboard/performance').then(r => setPerfData(r.data)).catch(e => console.warn('Dashboard perf:', e)).finally(() => setV2Loading(s => ({ ...s, perf: false })))
      api.get('/dashboard/dividendos').then(r => setDividendosData(r.data)).catch(e => console.warn('Dashboard divs:', e)).finally(() => setV2Loading(s => ({ ...s, divs: false })))
    } catch (err: any) {
      console.error('Dashboard load error:', err)
      setError(err?.response?.data?.detail || 'Erro ao carregar dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadDashboard() }, [])

  // Dados derivados
  const patrimonio = dash?.patrimonio?.atual ?? 0
  const varDia = dash?.patrimonio?.var_dia_pct ?? 0
  const varDiaReais = dash?.patrimonio?.var_dia_reais ?? 0
  const varMes = dash?.patrimonio?.var_mes_pct ?? null
  const totalPct = dash?.patrimonio?.total_pct ?? 0
  const rendaMes = dash?.renda?.renda_mes ?? null
  const rendaAnual = dash?.renda?.renda_anual_projetada ?? null
  const yoc = dash?.renda?.yoc ?? null
  const selic = dash?.macro?.selic
  const ibov = dash?.macro?.ibov
  const valorInvestido = dash?.patrimonio?.valor_investido_total ?? 0
  const plTotal = patrimonio - valorInvestido

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

  // Top Movers — gainers & losers
  const posicoes: any[] = dash?.posicoes ?? []
  const tradeable = posicoes.filter((p: any) => p.tipo !== 'CAIXA' && p.tipo !== 'RF')
  const sorted = [...tradeable].sort((a: any, b: any) => b.pl_percentual - a.pl_percentual)
  const topGainers = sorted.slice(0, 3).filter((p: any) => p.pl_percentual > 0)
  const topLosers = sorted.slice(-3).reverse().filter((p: any) => p.pl_percentual < 0)

  // Alertas consolidados
  const alertas: { tipo: 'danger' | 'warning' | 'info'; texto: string }[] = []
  const desvios = dash?.alocacao?.desvios ?? {}
  for (const [mod, dev] of Object.entries(desvios) as any) {
    if (dev.semaforo === 'vermelho') {
      const lbl = MODULE_LABELS[mod]?.label ?? mod
      alertas.push({ tipo: 'danger', texto: `${lbl}: desvio de ${dev.desvio > 0 ? '+' : ''}${dev.desvio.toFixed(1)}% da meta` })
    }
  }
  for (const p of posicoes) {
    if (p.stop_loss && p.preco_atual) {
      const dist = ((p.preco_atual - p.stop_loss) / p.preco_atual) * 100
      if (dist > 0 && dist < 5) {
        alertas.push({ tipo: 'warning', texto: `${p.ticker}: apenas ${dist.toFixed(1)}% acima do stop (R$${p.stop_loss.toFixed(2)})` })
      } else if (dist <= 0) {
        alertas.push({ tipo: 'danger', texto: `${p.ticker}: ABAIXO do stop loss (R$${p.stop_loss.toFixed(2)})` })
      }
    }
  }
  if (tesesData?.alertas?.length > 0) {
    for (const a of tesesData.alertas.slice(0, 3)) {
      alertas.push({ tipo: 'warning', texto: a })
    }
  }

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

  if (error) {
    return (
      <div className="p-8 flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <AlertTriangle size={32} style={{ color: '#FF5252' }} />
          <p className="text-sm" style={{ color: '#94a3b8' }}>{error}</p>
          <button
            onClick={loadDashboard}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}
          >
            <RefreshCw size={14} /> Tentar novamente
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Dashboard</h1>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <button onClick={loadDashboard} className="p-2 rounded-lg transition-all hover:scale-105" style={{ background: 'rgba(100,116,139,0.1)' }} title="Atualizar">
          <RefreshCw size={16} style={{ color: '#64748b' }} />
        </button>
      </div>

      {/* RENDA Strategy: yield metrics */}
      {strategyType === 'RENDA' && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl p-5 space-y-4"
          style={{ background: 'rgba(0,191,165,0.04)', border: '1px solid rgba(0,191,165,0.15)' }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#00BFA5' }}>APEX RENDA — Métricas de Renda</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Renda Mensal Projetada', value: rendaMes != null ? fmtR$(rendaMes) : '–', sub: 'Dividendos + JCP + FIIs', color: '#00BFA5' },
              { label: 'Yield on Cost', value: yoc != null && yoc > 0 ? `${yoc.toFixed(2)}%` : '–', sub: 'Sobre preço médio', color: '#00BFA5' },
              { label: 'Renda Anual Projetada', value: rendaAnual != null ? fmtR$(rendaAnual) : '–', sub: 'Projeção 12 meses', color: '#00BFA5' },
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
        {/* Patrimônio */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="apex-card p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Patrimônio</span>
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
              <DollarSign size={15} style={{ color: '#00E676' }} />
            </div>
          </div>
          <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>R$ {fmt(patrimonio)}</p>
          <p className="text-xs mt-1" style={{ color: varDiaReais >= 0 ? '#00E676' : '#FF5252' }}>
            {varDiaReais >= 0 ? '+' : ''}{fmtR$(varDiaReais)} hoje ({varDia >= 0 ? '+' : ''}{varDia.toFixed(2)}%)
          </p>
        </motion.div>

        {/* Retorno Mês */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="apex-card p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Retorno Mês</span>
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
              <TrendingUp size={15} style={{ color: '#00E676' }} />
            </div>
          </div>
          <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>{(varMes ?? 0) >= 0 ? '+' : ''}{(varMes ?? 0).toFixed(2)}%</p>
          <p className="text-xs mt-1" style={{ color: '#64748b' }}>
            vs CDI: {dash?.patrimonio?.vs_cdi != null
              ? <span style={{ color: dash.patrimonio.vs_cdi >= 0 ? '#00E676' : '#FF5252' }}>{dash.patrimonio.vs_cdi >= 0 ? '+' : ''}{dash.patrimonio.vs_cdi.toFixed(2)}pp</span>
              : '–'}
            {dash?.patrimonio?.cdi_mes_pct != null && <span> (CDI mês: {dash.patrimonio.cdi_mes_pct.toFixed(2)}%)</span>}
          </p>
        </motion.div>

        {/* P&L Total */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="apex-card p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>P&L Total</span>
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: plTotal >= 0 ? 'rgba(0,230,118,0.08)' : 'rgba(255,82,82,0.08)' }}>
              {plTotal >= 0 ? <ArrowUpRight size={15} style={{ color: '#00E676' }} /> : <ArrowDownRight size={15} style={{ color: '#FF5252' }} />}
            </div>
          </div>
          <p className="text-xl font-bold font-data" style={{ color: plTotal >= 0 ? '#00E676' : '#FF5252' }}>
            {plTotal >= 0 ? '+' : ''}{fmtR$(plTotal)}
          </p>
          <p className="text-xs mt-1" style={{ color: '#64748b' }}>
            Investido: R$ {fmt(valorInvestido)}
          </p>
        </motion.div>

        {/* Renda Projetada (ou Retorno Acumulado para CRESCIMENTO) */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="apex-card p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              {strategyType === 'RENDA' ? 'Renda / Mês' : 'Retorno Total'}
            </span>
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
              <Zap size={15} style={{ color: '#00E676' }} />
            </div>
          </div>
          <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>
            {strategyType === 'RENDA' ? (rendaMes != null ? fmtR$(rendaMes) : '–') : `${totalPct.toFixed(2)}%`}
          </p>
          <p className="text-xs mt-1" style={{ color: '#64748b' }}>
            {strategyType === 'RENDA' ? (yoc > 0 ? `YoC: ${yoc.toFixed(2)}%` : 'YoC: –') : 'Desde o início'}
          </p>
        </motion.div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Performance & Top Movers */}
        <motion.div
          className="apex-card p-5 col-span-2"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PERFORMANCE & TOP MOVERS</h3>
          </div>
          <div className="grid grid-cols-2 gap-6">
            {/* Trading Stats */}
            <div className="space-y-3">
              <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#475569' }}>Estatísticas de Trading</p>
              {perfData ? (
                <div className="space-y-2">
                  {[
                    { label: 'Win Rate', value: `${(perfData.win_rate ?? 0).toFixed(1)}%`, color: (perfData.win_rate ?? 0) >= 50 ? '#00E676' : '#FF5252' },
                    { label: 'Trades Totais', value: `${perfData.total_operacoes ?? 0}`, color: '#f1f5f9' },
                    { label: 'Resultado Líquido', value: fmtR$(perfData.resultado_liquido ?? 0), color: (perfData.resultado_liquido ?? 0) >= 0 ? '#00E676' : '#FF5252' },
                    { label: 'Risk/Reward', value: `${(perfData.risk_reward ?? 0).toFixed(2)}`, color: (perfData.risk_reward ?? 0) >= 1.5 ? '#00E676' : '#FFD740' },
                  ].map(s => (
                    <div key={s.label} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <span className="text-xs" style={{ color: '#94a3b8' }}>{s.label}</span>
                      <span className="text-sm font-bold font-data" style={{ color: s.color }}>{s.value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-2">{[1,2,3,4].map(i => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>
              )}
            </div>

            {/* Top Movers */}
            <div className="space-y-3">
              <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#475569' }}>Top Movers</p>
              {topGainers.length > 0 || topLosers.length > 0 ? (
                <div className="space-y-2">
                  {topGainers.map((p: any) => (
                    <div key={p.ticker} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <div className="flex items-center gap-2">
                        <ArrowUpRight size={12} style={{ color: '#00E676' }} />
                        <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{p.ticker}</span>
                      </div>
                      <span className="text-xs font-bold font-data" style={{ color: '#00E676' }}>+{p.pl_percentual?.toFixed(1)}%</span>
                    </div>
                  ))}
                  {topLosers.map((p: any) => (
                    <div key={p.ticker} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <div className="flex items-center gap-2">
                        <ArrowDownRight size={12} style={{ color: '#FF5252' }} />
                        <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{p.ticker}</span>
                      </div>
                      <span className="text-xs font-bold font-data" style={{ color: '#FF5252' }}>{p.pl_percentual?.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs" style={{ color: '#475569' }}>Nenhuma posição em carteira</p>
              )}
            </div>
          </div>
        </motion.div>

        {/* Allocation */}
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
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
        transition={{ delay: 0.35 }}
      >
        <div className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ background: regimeColor }} />
        <span className="text-sm font-mono" style={{ color: regimeColor }}>{regimeNome}</span>
        <span className="text-sm" style={{ color: '#64748b' }}>{regimeMotivo}</span>
      </motion.div>

      {/* Alertas Consolidados */}
      {alertas.length > 0 && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Crosshair size={16} style={{ color: '#FF5252' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>ALERTAS</h3>
            <span className="text-xs px-2 py-0.5 rounded-full font-mono" style={{ background: 'rgba(255,82,82,0.1)', color: '#FF5252' }}>{alertas.length}</span>
          </div>
          <div className="space-y-2">
            {alertas.slice(0, 8).map((a, i) => (
              <div key={i} className="flex items-start gap-2 text-xs rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <AlertTriangle size={12} className="mt-0.5 shrink-0" style={{ color: a.tipo === 'danger' ? '#FF5252' : '#FFD740' }} />
                <span style={{ color: a.tipo === 'danger' ? '#FF5252' : '#FFD740' }}>{a.texto}</span>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Próximos Dividendos */}
      {v2Loading.divs ? (
        <motion.div className="apex-card p-5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.42 }}>
          <div className="flex items-center gap-2 mb-4">
            <Calendar size={16} style={{ color: '#00BFA5' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PRÓXIMOS DIVIDENDOS</h3>
          </div>
          <div className="space-y-2">
            {[1,2,3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
          </div>
        </motion.div>
      ) : dividendosData && dividendosData.proximos?.length > 0 && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.42 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Calendar size={16} style={{ color: '#00BFA5' }} />
              <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PRÓXIMOS DIVIDENDOS</h3>
            </div>
            {dividendosData.total_projetado_mes > 0 && (
              <span className="text-xs font-mono px-2 py-1 rounded" style={{ background: 'rgba(0,191,165,0.1)', color: '#00BFA5' }}>
                Este mês: {fmtR$(dividendosData.total_projetado_mes)}
              </span>
            )}
          </div>
          <div className="space-y-2">
            {dividendosData.proximos.slice(0, 8).map((d: any) => (
              <div key={d.ticker} className="flex items-center justify-between rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono font-bold" style={{ color: '#f1f5f9' }}>{d.ticker}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(100,116,139,0.15)', color: '#94a3b8' }}>{d.frequencia}</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-xs" style={{ color: '#64748b' }}>
                      ~{new Date(d.data_estimada + 'T00:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                      <span style={{ color: '#475569' }}> ({d.dias_restantes}d)</span>
                    </p>
                  </div>
                  <div className="text-right min-w-[80px]">
                    <p className="text-sm font-bold font-data" style={{ color: '#00BFA5' }}>{fmtR$(d.valor_estimado)}</p>
                    <p className="text-xs" style={{ color: '#475569' }}>DY {d.dy_12m}%</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Painel Macro */}
      {v2Loading.macro ? (
        <motion.div className="apex-card p-5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45 }}>
          <div className="flex items-center gap-2 mb-4">
            <Globe size={16} style={{ color: '#00B0FF' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PAINEL MACRO</h3>
          </div>
          <div className="grid grid-cols-5 gap-3">
            {[1,2,3,4,5].map(i => <Skeleton key={i} className="h-16 rounded-lg" />)}
          </div>
        </motion.div>
      ) : macroData && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <Globe size={16} style={{ color: '#00B0FF' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PAINEL MACRO</h3>
          </div>

          <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>GLOBAL</p>
          <div className="grid grid-cols-4 lg:grid-cols-7 gap-3 mb-4">
            {[
              { label: 'VIX', value: macroData.global?.vix, fmt: (v: number) => v?.toFixed(1), warn: (v: number) => v > 25 },
              { label: 'Treasury 10Y', value: macroData.global?.treasury_10y, fmt: (v: number) => `${v?.toFixed(2)}%` },
              { label: 'DXY', value: macroData.global?.dxy, fmt: (v: number) => v?.toFixed(2) },
              { label: 'S&P 500', value: macroData.global?.sp500, fmt: (v: number) => fmt(v ?? 0), sub: macroData.global?.sp500_var_pct },
              { label: 'Dow Jones', value: macroData.global?.dow_jones, fmt: (v: number) => fmt(v ?? 0), sub: macroData.global?.dow_jones_var_pct },
              { label: 'Petróleo WTI', value: macroData.global?.petroleo_wti, fmt: (v: number) => `$${v?.toFixed(0)}` },
              { label: 'Ouro', value: macroData.global?.ouro, fmt: (v: number) => `$${fmt(v ?? 0)}` },
            ].map(item => (
              <div key={item.label} className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <p className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: '#475569' }}>{item.label}</p>
                <p className="text-base font-bold font-data" style={{ color: (item as any).warn?.(item.value) ? '#FF5252' : '#f1f5f9' }}>
                  {item.value != null ? item.fmt(item.value) : '–'}
                </p>
                {(item as any).sub != null && (
                  <p className="text-[10px] font-mono mt-0.5" style={{ color: (item as any).sub >= 0 ? '#00E676' : '#FF5252' }}>
                    {(item as any).sub >= 0 ? '+' : ''}{((item as any).sub as number).toFixed(2)}%
                  </p>
                )}
              </div>
            ))}
          </div>

          <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>BRASIL</p>
          <div className="grid grid-cols-5 gap-3">
            {[
              { label: 'Selic', value: macroData.brasil?.selic, fmt: (v: number) => `${v?.toFixed(2)}%` },
              { label: 'IPCA 12m', value: macroData.brasil?.ipca_12m, fmt: (v: number) => `${v?.toFixed(2)}%` },
              { label: 'Juro Real', value: macroData.brasil?.juro_real, fmt: (v: number) => `${v?.toFixed(1)}%`, warn: (v: number) => v > 6 },
              { label: 'Dólar', value: macroData.brasil?.dolar_brl, fmt: (v: number) => `R$${v?.toFixed(2)}` },
              { label: 'IBOV', value: macroData.brasil?.ibov, fmt: (v: number) => fmt(v ?? 0) },
            ].map(item => (
              <div key={item.label} className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <p className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: '#475569' }}>{item.label}</p>
                <p className="text-base font-bold font-data" style={{ color: item.warn?.(item.value) ? '#FFD740' : '#f1f5f9' }}>
                  {item.value != null ? item.fmt(item.value) : '–'}
                </p>
              </div>
            ))}
          </div>

          {macroData.flags?.length > 0 && (
            <div className="mt-3 space-y-1">
              {macroData.flags.map((flag: string, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs" style={{ color: '#FFD740' }}>
                  <AlertTriangle size={12} />
                  <span>{flag}</span>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      <div>
        {/* Teses de Investimento */}
        {v2Loading.teses ? (
          <motion.div className="apex-card p-5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} style={{ color: '#AA00FF' }} />
              <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>TESES DE INVESTIMENTO</h3>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[1,2,3].map(i => <Skeleton key={i} className="h-20 rounded-lg" />)}
            </div>
          </motion.div>
        ) : tesesData && tesesData.total > 0 && (
          <motion.div
            className="apex-card p-5"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} style={{ color: '#AA00FF' }} />
              <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>TESES DE INVESTIMENTO</h3>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="rounded-lg p-3 text-center" style={{ background: 'rgba(0,230,118,0.06)', border: '1px solid rgba(0,230,118,0.15)' }}>
                <p className="text-2xl font-bold font-data" style={{ color: '#00E676' }}>{tesesData.ativas ?? 0}</p>
                <p className="text-xs mt-1" style={{ color: '#475569' }}>Ativas</p>
              </div>
              <div className="rounded-lg p-3 text-center" style={{ background: 'rgba(255,215,64,0.06)', border: '1px solid rgba(255,215,64,0.15)' }}>
                <p className="text-2xl font-bold font-data" style={{ color: '#FFD740' }}>{tesesData.enfraquecidas ?? 0}</p>
                <p className="text-xs mt-1" style={{ color: '#475569' }}>Enfraquecidas</p>
              </div>
              <div className="rounded-lg p-3 text-center" style={{ background: 'rgba(255,82,82,0.06)', border: '1px solid rgba(255,82,82,0.15)' }}>
                <p className="text-2xl font-bold font-data" style={{ color: '#FF5252' }}>{tesesData.invalidadas ?? 0}</p>
                <p className="text-xs mt-1" style={{ color: '#475569' }}>Invalidadas</p>
              </div>
            </div>

            {tesesData.alertas?.length > 0 && (
              <div className="space-y-1">
                {tesesData.alertas.slice(0, 3).map((alerta: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs" style={{ color: '#FFD740' }}>
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    <span>{alerta}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  )
}
