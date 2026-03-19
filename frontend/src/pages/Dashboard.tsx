import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  TrendingUp, DollarSign, Globe, Calendar,
  FileText, AlertTriangle, RefreshCw, Zap, ArrowUpRight,
  ArrowDownRight, Crosshair, Download
} from 'lucide-react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as ReTooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts'
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
  const [retornoPeriodo, setRetornoPeriodo] = useState<string>('total')
  const [retornoData, setRetornoData] = useState<any>(null)
  const [evolucaoData, setEvolucaoData] = useState<any[]>([])
  const [v3Loading, setV3Loading] = useState({ evolucao: true })
  const [moversPeriodo, setMoversPeriodo] = useState<string>('dia')
  const [moversApiData, setMoversApiData] = useState<any[]>([])
  const [moversApiLoading, setMoversApiLoading] = useState(false)

  async function loadDashboard() {
    setLoading(true)
    setError(null)
    setV2Loading({ macro: true, teses: true, perf: true, divs: true })
    setV3Loading({ evolucao: true })

    // Dispara TODAS as chamadas em paralelo — nenhuma bloqueia as outras
    const dashPromise = api.get('/dashboard/')
      .then(r => { setDash(r.data); return r.data })
      .catch((err: any) => {
        console.error('Dashboard load error:', err)
        setError(err?.response?.data?.detail || 'Erro ao carregar dashboard')
        return null
      })

    // Regime
    api.get('/market/regime').then(r => setRegime(r.data)).catch(e => console.warn('Regime:', e))

    // V2 endpoints — paralelos
    api.get('/dashboard/macro').then(r => setMacroData(r.data)).catch(e => console.warn('Dashboard macro:', e)).finally(() => setV2Loading(s => ({ ...s, macro: false })))
    api.get('/dashboard/teses').then(r => setTesesData(r.data)).catch(e => console.warn('Dashboard teses:', e)).finally(() => setV2Loading(s => ({ ...s, teses: false })))
    api.get('/dashboard/performance').then(r => setPerfData(r.data)).catch(e => console.warn('Dashboard perf:', e)).finally(() => setV2Loading(s => ({ ...s, perf: false })))
    api.get('/dashboard/dividendos').then(r => setDividendosData(r.data)).catch(e => console.warn('Dashboard divs:', e)).finally(() => setV2Loading(s => ({ ...s, divs: false })))

    // V3 endpoints — paralelos
    api.get('/portfolio/evolucao').then(r => { if (Array.isArray(r.data) && r.data.length >= 2) setEvolucaoData(r.data) }).catch(() => {}).finally(() => setV3Loading(s => ({ ...s, evolucao: false })))

    // O loading principal termina quando /dashboard/ retornar
    await dashPromise
    setLoading(false)
  }

  useEffect(() => { loadDashboard() }, [])

  // Recarrega ao trocar carteira
  useEffect(() => {
    const handler = () => loadDashboard()
    window.addEventListener('portfolio-changed', handler)
    return () => window.removeEventListener('portfolio-changed', handler)
  }, [])

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

  // Top Movers — usa variação diária, total, ou período via API
  const posicoes: any[] = dash?.posicoes ?? []
  const tradeable = posicoes.filter((p: any) => p.tipo !== 'CAIXA' && p.tipo !== 'RF')
  const hasVarDia = tradeable.some((p: any) => p.var_dia_pct != null && p.var_dia_pct !== 0)

  // Carrega movers de período via API
  useEffect(() => {
    if (moversPeriodo === 'dia' || moversPeriodo === 'total') return
    setMoversApiLoading(true)
    api.get(`/dashboard/movers?periodo=${moversPeriodo}`)
      .then(r => setMoversApiData(r.data?.movers ?? []))
      .catch(() => setMoversApiData([]))
      .finally(() => setMoversApiLoading(false))
  }, [moversPeriodo])

  const moversLabel = { dia: 'Dia', '1m': '1M', '3m': '3M', '6m': '6M', '1a': '1A', total: 'Total' }[moversPeriodo] ?? moversPeriodo

  // Compute gainers/losers based on active period
  const { topGainers, topLosers } = (() => {
    if (moversPeriodo === 'dia' || moversPeriodo === 'total') {
      const key = moversPeriodo === 'dia' ? 'var_dia_pct' : 'pl_percentual'
      const sorted = [...tradeable].sort((a: any, b: any) => (b[key] ?? 0) - (a[key] ?? 0))
      return {
        topGainers: sorted.slice(0, 3).filter((p: any) => (p[key] ?? 0) > 0).map((p: any) => ({ ticker: p.ticker, var_pct: p[key] ?? 0 })),
        topLosers: sorted.slice(-3).reverse().filter((p: any) => (p[key] ?? 0) < 0).map((p: any) => ({ ticker: p.ticker, var_pct: p[key] ?? 0 })),
      }
    }
    // API-based periods
    const sorted = [...moversApiData].sort((a: any, b: any) => (b.var_pct ?? 0) - (a.var_pct ?? 0))
    return {
      topGainers: sorted.slice(0, 3).filter((m: any) => (m.var_pct ?? 0) > 0),
      topLosers: sorted.slice(-3).reverse().filter((m: any) => (m.var_pct ?? 0) < 0),
    }
  })()

  // Alocação por tipo (ACAO, FII, ETF, BDR, RF, etc.)
  const TIPO_COLORS: Record<string, string> = {
    ACAO: '#1DE9B6', FII: '#00BFA5', ETF: '#00E676', BDR: '#64FFDA',
    RF: '#FFD740', OPCAO: '#FF9800', CAIXA: '#475569', FUNDO: '#AB47BC',
  }

  const tipoAllocation = (() => {
    const byTipo: Record<string, number> = {}
    for (const p of posicoes) {
      byTipo[p.tipo] = (byTipo[p.tipo] || 0) + (p.valor_atual || 0)
    }
    const total = Object.values(byTipo).reduce((a, b) => a + b, 0)
    if (total <= 0) return []
    return Object.entries(byTipo)
      .map(([tipo, val]) => ({ tipo, valor: val, pct: (val / total) * 100, color: TIPO_COLORS[tipo] || '#94a3b8' }))
      .sort((a, b) => b.valor - a.valor)
  })()

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
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const lines = [
                `Dashboard APEX — ${new Date().toLocaleDateString('pt-BR')}`,
                `Patrimônio: R$ ${patrimonio.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
                `Var Dia: ${varDia >= 0 ? '+' : ''}${varDia.toFixed(2)}%`,
                `Retorno Total: ${totalPct.toFixed(2)}%`,
                `P&L: R$ ${plTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`,
                '',
                'Ticker,Tipo,Módulo,Valor Atual,P&L %,Var Dia %',
                ...posicoes.map((p: any) => `${p.ticker},${p.tipo},${p.modulo},${(p.valor_atual || 0).toFixed(2)},${(p.pl_percentual || 0).toFixed(2)},${(p.var_dia_pct || 0).toFixed(2)}`),
              ]
              const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `dashboard_${new Date().toISOString().slice(0, 10)}.csv`
              a.click()
              URL.revokeObjectURL(url)
            }}
            className="p-2 rounded-lg transition-all hover:scale-105"
            style={{ background: 'rgba(100,116,139,0.1)' }}
            title="Exportar CSV"
          >
            <Download size={16} style={{ color: '#64748b' }} />
          </button>
          <button onClick={loadDashboard} className="p-2 rounded-lg transition-all hover:scale-105" style={{ background: 'rgba(100,116,139,0.1)' }} title="Atualizar">
            <RefreshCw size={16} style={{ color: '#64748b' }} />
          </button>
        </div>
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
          <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>{varMes != null ? `${varMes >= 0 ? '+' : ''}${varMes.toFixed(2)}%` : '–'}</p>
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

        {/* Retorno — com filtro de período */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="apex-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
              {strategyType === 'RENDA' ? 'Renda / Mês' : 'Retorno Total'}
            </span>
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
              <Zap size={15} style={{ color: '#00E676' }} />
            </div>
          </div>
          {strategyType !== 'RENDA' && (
            <div className="flex gap-1 mb-2">
              {[
                { k: 'total', l: 'Total' },
                { k: '1m', l: '1M' },
                { k: '3m', l: '3M' },
                { k: '6m', l: '6M' },
                { k: '1a', l: '1A' },
              ].map(({ k, l }) => (
                <button
                  key={k}
                  onClick={() => {
                    setRetornoPeriodo(k)
                    if (k !== 'total') {
                      api.get('/dashboard/retorno', { params: { periodo: k } })
                        .then(r => setRetornoData(r.data))
                        .catch(() => setRetornoData(null))
                    } else {
                      setRetornoData(null)
                    }
                  }}
                  className="px-2 py-0.5 rounded text-[10px] font-mono transition-all"
                  style={{
                    background: retornoPeriodo === k ? 'rgba(0,230,118,0.15)' : 'rgba(30,41,59,0.5)',
                    color: retornoPeriodo === k ? '#00E676' : '#64748b',
                    border: `1px solid ${retornoPeriodo === k ? 'rgba(0,230,118,0.3)' : '#1e293b'}`,
                  }}
                >
                  {l}
                </button>
              ))}
            </div>
          )}
          <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>
            {strategyType === 'RENDA'
              ? (rendaMes != null ? fmtR$(rendaMes) : '–')
              : retornoPeriodo !== 'total' && retornoData != null
                ? retornoData.retorno_pct != null
                  ? `${retornoData.retorno_pct >= 0 ? '+' : ''}${retornoData.retorno_pct.toFixed(2)}%`
                  : '–'
                : `${totalPct.toFixed(2)}%`
            }
          </p>
          <p className="text-xs mt-1" style={{ color: '#64748b' }}>
            {strategyType === 'RENDA'
              ? (yoc > 0 ? `YoC: ${yoc.toFixed(2)}%` : 'YoC: –')
              : retornoPeriodo !== 'total' && retornoData != null
                ? retornoData.retorno_pct != null
                  ? `vs CDI: ${retornoData.vs_cdi != null ? `${retornoData.vs_cdi >= 0 ? '+' : ''}${retornoData.vs_cdi.toFixed(2)}pp` : '–'}`
                  : (retornoData.msg || 'Sem snapshots para este período')
                : 'Desde o início'
            }
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
              <div className="flex items-center justify-between">
                <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#475569' }}>Top Movers ({moversLabel})</p>
              </div>
              <div className="flex gap-1 flex-wrap">
                {([['dia', 'Dia'], ['1m', '1M'], ['3m', '3M'], ['6m', '6M'], ['1a', '1A'], ['total', 'Total']] as const).map(([val, lbl]) => (
                  <button
                    key={val}
                    onClick={() => setMoversPeriodo(val)}
                    className="px-2 py-0.5 rounded text-xs font-mono transition-colors"
                    style={{
                      background: moversPeriodo === val ? 'rgba(0,230,118,0.15)' : 'rgba(15,23,42,0.6)',
                      color: moversPeriodo === val ? '#00E676' : '#64748b',
                      border: `1px solid ${moversPeriodo === val ? 'rgba(0,230,118,0.3)' : '#1e293b'}`,
                    }}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
              {moversApiLoading ? (
                <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} h="h-8" />)}</div>
              ) : topGainers.length > 0 || topLosers.length > 0 ? (
                <div className="space-y-2">
                  {topGainers.map((m: any) => (
                    <div key={m.ticker} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <div className="flex items-center gap-2">
                        <ArrowUpRight size={12} style={{ color: '#00E676' }} />
                        <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{m.ticker}</span>
                      </div>
                      <span className="text-xs font-bold font-data" style={{ color: '#00E676' }}>+{(m.var_pct ?? 0).toFixed(1)}%</span>
                    </div>
                  ))}
                  {topLosers.map((m: any) => (
                    <div key={m.ticker} className="flex items-center justify-between rounded-lg p-2.5" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <div className="flex items-center gap-2">
                        <ArrowDownRight size={12} style={{ color: '#FF5252' }} />
                        <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{m.ticker}</span>
                      </div>
                      <span className="text-xs font-bold font-data" style={{ color: '#FF5252' }}>{(m.var_pct ?? 0).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs" style={{ color: '#475569' }}>Nenhuma posição em carteira</p>
              )}
            </div>
          </div>
        </motion.div>

        {/* Allocation — Pie + Bars */}
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <h3 className="text-sm font-medium mb-4" style={{ color: '#94a3b8' }}>ALOCAÇÃO</h3>
          {allocationData.length > 0 && (
            <div className="flex justify-center mb-4">
              <ResponsiveContainer width={160} height={160}>
                <PieChart>
                  <Pie
                    data={allocationData.filter(a => a.current > 0)}
                    dataKey="current"
                    nameKey="module"
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={68}
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {allocationData.filter(a => a.current > 0).map((entry, idx) => (
                      <Cell key={idx} fill={entry.color} />
                    ))}
                  </Pie>
                  <ReTooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
                    formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="space-y-2">
            {allocationData.map((item) => {
              const dev = getDeviation(item.target, item.current)
              const barMax = Math.max(...allocationData.map(a => Math.max(a.current, a.target)), 5)
              return (
                <div key={item.module}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: item.color }} />
                      <span className="text-xs" style={{ color: '#94a3b8' }}>{item.module}</span>
                    </div>
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

      {/* Evolução Patrimonial — Carteira vs CDI */}
      {!v3Loading.evolucao && evolucaoData.length >= 2 && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.36 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={16} style={{ color: '#00E676' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>EVOLUÇÃO PATRIMONIAL</h3>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={evolucaoData} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tickFormatter={(d: string) => { const [, m, day] = d.split('-'); return `${day}/${m}` }} tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
              <ReTooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: '#94a3b8' }}
                labelFormatter={(d: string) => { const [, m, day] = d.split('-'); return `${day}/${m}` }}
                formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
              <Line type="monotone" dataKey="pl_pct" name="Carteira" stroke="#00E676" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="cdi_pct" name="CDI" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 5" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      )}

      {/* Alocação por Tipo */}
      {tipoAllocation.length > 0 && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.39 }}
        >
          <h3 className="text-sm font-medium mb-4" style={{ color: '#94a3b8' }}>ALOCAÇÃO POR TIPO</h3>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width={140} height={140}>
              <PieChart>
                <Pie
                  data={tipoAllocation}
                  dataKey="pct"
                  nameKey="tipo"
                  cx="50%"
                  cy="50%"
                  innerRadius={36}
                  outerRadius={60}
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  {tipoAllocation.map((entry, idx) => (
                    <Cell key={idx} fill={entry.color} />
                  ))}
                </Pie>
                <ReTooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
                  formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-2">
              {tipoAllocation.map(t => (
                <div key={t.tipo} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ background: t.color }} />
                    <span className="text-xs" style={{ color: '#94a3b8' }}>{t.tipo}</span>
                  </div>
                  <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{t.pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* Estimativa de IR */}
      {plTotal !== 0 && (
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.395 }}
        >
          <div className="flex items-center gap-2 mb-3">
            <DollarSign size={16} style={{ color: '#FFD740' }} />
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>ESTIMATIVA DE IR</h3>
            <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(255,215,64,0.08)', color: '#FFD740' }}>Simulação</span>
          </div>
          <p className="text-xs mb-3" style={{ color: '#475569' }}>
            Estimativa simplificada sobre ganho de capital realizado. Não constitui declaração fiscal.
          </p>
          <div className="grid grid-cols-3 gap-3">
            {(() => {
              // Ações/ETFs: 15% sobre lucro se vendas > R$20k/mês (isenção swing trade)
              const plAcoes = posicoes.filter((p: any) => ['ACAO', 'ETF', 'BDR'].includes(p.tipo)).reduce((a: number, p: any) => a + (p.pl_reais || 0), 0)
              const plFIIs = posicoes.filter((p: any) => p.tipo === 'FII').reduce((a: number, p: any) => a + (p.pl_reais || 0), 0)
              const irAcoes = plAcoes > 0 ? plAcoes * 0.15 : 0
              const irFIIs = plFIIs > 0 ? plFIIs * 0.20 : 0
              const irTotal = irAcoes + irFIIs
              return [
                { label: 'Ações/ETFs (15%)', value: irAcoes, sub: plAcoes > 0 ? `Sobre R$ ${plAcoes.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} de lucro` : 'Sem lucro realizado' },
                { label: 'FIIs (20%)', value: irFIIs, sub: plFIIs > 0 ? `Sobre R$ ${plFIIs.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} de lucro` : 'Sem lucro realizado' },
                { label: 'IR Total Estimado', value: irTotal, sub: 'Sobre posições em aberto' },
              ].map(item => (
                <div key={item.label} className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                  <p className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: '#475569' }}>{item.label}</p>
                  <p className="text-sm font-bold font-data" style={{ color: item.value > 0 ? '#FFD740' : '#64748b' }}>
                    R$ {item.value.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </p>
                  <p className="text-[10px] mt-1" style={{ color: '#475569' }}>{item.sub}</p>
                </div>
              ))
            })()}
          </div>
        </motion.div>
      )}

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
      ) : dividendosData && (
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
          {dividendosData.proximos?.length > 0 ? (
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
          ) : (
            <p className="text-xs" style={{ color: '#475569' }}>Sem dividendos projetados no momento</p>
          )}
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
