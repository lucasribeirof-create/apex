import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw, Sun, TrendingUp, TrendingDown } from 'lucide-react'
import api from '@/services/api'

interface BriefingData {
  id: number
  data: string
  conteudo: string
  regime: string
  macro: {
    dolar: number | null
    ibov: number | null
    ibov_variacao: number | null
  }
}

interface MacroData {
  sp500: number | null
  sp500_variacao: number | null
  ibov: number | null
  ibov_variacao: number | null
  dolar: number | null
  dolar_variacao: number | null
}

function RegimeBadge({ regime }: { regime: string }) {
  const map: Record<string, { color: string; bg: string; dot: string; label: string }> = {
    BULL: { color: '#00E676', bg: 'rgba(0,230,118,0.08)', dot: '#00E676', label: 'BULL' },
    MISTO: { color: '#FFD740', bg: 'rgba(255,215,64,0.08)', dot: '#FFD740', label: 'MISTO' },
    BEAR: { color: '#FF5252', bg: 'rgba(255,82,82,0.08)', dot: '#FF5252', label: 'BEAR' },
  }
  const s = map[regime] || map.MISTO
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-mono" style={{ background: s.bg, border: `1px solid ${s.color}30`, color: s.color }}>
      <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: s.dot }} />
      {s.label}
    </div>
  )
}

export default function BriefingPage() {
  const [briefing, setBriefing] = useState<BriefingData | null>(null)
  const [macro, setMacro] = useState<MacroData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)

  const loadBriefing = async (force = false) => {
    setLoading(true)
    setError(null)
    if (force) { setBriefing(null); setElapsed(null) }
    const t0 = Date.now()
    try {
      const [briefingRes, macroRes] = await Promise.all([
        api.get('/briefing/hoje', { params: force ? { force: true } : {} }),
        api.get('/market/macro').catch(() => ({ data: null })),
      ])
      setBriefing(briefingRes.data)
      if (macroRes.data) setMacro(macroRes.data)
      if (force) setElapsed((Date.now() - t0) / 1000)
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Erro ao carregar briefing'
      setError(msg)
    }
    setLoading(false)
  }

  useEffect(() => { loadBriefing() }, [])

  return (
    <div className="p-8 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sun size={18} style={{ color: '#00E676' }} />
            <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Morning Briefing</h1>
          </div>
          <p className="text-sm" style={{ color: '#64748b' }}>
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>

        <button
          onClick={() => loadBriefing(true)}
          disabled={loading}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Carregando...' : 'Atualizar'}
        </button>
      </div>

      {/* Loading */}
      {loading && !briefing && (
        <div className="apex-card p-8 flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <span className="text-xl font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <div className="text-center">
            <p className="font-medium mb-1" style={{ color: '#f1f5f9' }}>Analisando o mercado...</p>
            <p className="text-sm" style={{ color: '#64748b' }}>Gerando seu briefing personalizado</p>
          </div>
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#00E676', animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-6 text-center">
          <p className="text-sm mb-4" style={{ color: '#FF5252' }}>{error}</p>
          <button onClick={() => loadBriefing()} className="btn-primary">Tentar Novamente</button>
        </motion.div>
      )}

      {/* Briefing content */}
      {briefing && !loading && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">

          {/* Macro bar */}
          <div className="grid grid-cols-4 gap-3">
            {/* Dólar */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
                <span className="text-xs font-bold" style={{ color: '#00E676' }}>BRL</span>
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>Dólar</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {(macro?.dolar || briefing.macro?.dolar) ? `R$ ${Number(macro?.dolar || briefing.macro?.dolar).toFixed(2)}` : '--'}
                </p>
                {macro?.dolar_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.dolar_variacao >= 0 ? '#FF5252' : '#00E676' }}>
                    {macro.dolar_variacao >= 0 ? '+' : ''}{macro.dolar_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* IBOVESPA */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
                {(macro?.ibov_variacao ?? 0) >= 0
                  ? <TrendingUp size={14} style={{ color: '#00E676' }} />
                  : <TrendingDown size={14} style={{ color: '#FF5252' }} />}
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>IBOVESPA</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {(macro?.ibov || briefing.macro?.ibov) ? Number(macro?.ibov || briefing.macro?.ibov).toLocaleString('pt-BR', { maximumFractionDigits: 0 }) : '--'}
                </p>
                {macro?.ibov_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.ibov_variacao >= 0 ? '#00E676' : '#FF5252' }}>
                    {macro.ibov_variacao >= 0 ? '+' : ''}{macro.ibov_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* S&P 500 */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,188,212,0.08)' }}>
                {(macro?.sp500_variacao ?? 0) >= 0
                  ? <TrendingUp size={14} style={{ color: '#00BCD4' }} />
                  : <TrendingDown size={14} style={{ color: '#FF5252' }} />}
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>S&P 500</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {macro?.sp500 ? Number(macro.sp500).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '--'}
                </p>
                {macro?.sp500_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.sp500_variacao >= 0 ? '#00E676' : '#FF5252' }}>
                    {macro.sp500_variacao >= 0 ? '+' : ''}{macro.sp500_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* Regime */}
            <div className="apex-card p-4 flex items-center justify-between">
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>Regime</p>
                <div className="mt-1">
                  <RegimeBadge regime={briefing.regime || 'MISTO'} />
                </div>
              </div>
            </div>
          </div>

          {/* Briefing text */}
          <div className="apex-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
              </div>
              <span className="text-sm font-medium" style={{ color: '#94a3b8' }}>Gestor APEX</span>
              <div className="ml-auto flex items-center gap-3">
                {elapsed != null && (
                  <span className="text-xs font-mono px-2 py-0.5 rounded-full" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                    gerado em {elapsed.toFixed(1)}s
                  </span>
                )}
                <span className="text-xs font-mono" style={{ color: '#64748b' }}>
                  {briefing.data ? new Date(briefing.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''}
                </span>
              </div>
            </div>
            <div className="text-sm leading-relaxed" style={{ color: '#f1f5f9' }}>
              {briefing.conteudo.split('\n').map((line, i) => {
                // Bold: **text**
                const parts = line.split(/\*\*(.*?)\*\*/g)
                return (
                  <p key={i} className={line === '' ? 'mb-3' : 'mb-1'}>
                    {parts.map((part, j) =>
                      j % 2 === 1 ? <strong key={j} style={{ color: '#e2e8f0' }}>{part}</strong> : part
                    )}
                  </p>
                )
              })}
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}
