/**
 * Aportes Inteligentes — Drill-down por módulo.
 *
 * Landing: módulos com desvio do alvo (instantâneo, DB only).
 * Click módulo → analisa posições dentro do módulo → recomendações por ativo.
 */
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  PiggyBank, AlertTriangle, RefreshCw, Loader2,
  Shield, Target, DollarSign, Edit3, Check, X,
  ArrowLeft, BarChart3, ChevronRight, TrendingUp, TrendingDown,
  Activity, Ban,
} from 'lucide-react'
import api from '@/services/api'

/* ─── Types ──────────────────────────────────────────────────────────────── */

interface ModuloResumo {
  modulo: string
  alvo_pct: number
  real_pct: number
  desvio_pp: number
  valor_atual: number
  posicoes: number
}

interface ResumoData {
  aporte_mensal: number
  patrimonio_atual: number
  regime: string
  modulos: ModuloResumo[]
  alocacao_configurada: boolean
}

interface PosicaoAnalise {
  id: number
  ticker: string
  tipo: string
  quantidade: number
  preco_medio: number
  preco_atual: number
  valor_atual: number
  pl_reais: number
  pl_pct: number
  pct_do_modulo: number
  peso_ideal_pct: number
  peso_alvo: number | null
  sugestao: string
  prioridade: 'ALTA' | 'MEDIA' | 'BAIXA' | 'NEUTRA'
  // DCA Inteligente — timing
  rsi14: number | null
  ma50: number | null
  abaixo_ma50: boolean
  multiplicador: number
  sinal_timing: string
  valor_sugerido: number
  qtd_sugerida: number
}

interface ModuloAnalise {
  modulo: string
  modulo_label: string
  alvo_pct: number
  real_pct: number
  desvio_pp: number
  valor_atual_modulo: number
  patrimonio_total: number
  aporte_mensal: number
  valor_sugerido: number
  status: 'ABAIXO' | 'ACIMA' | 'ALINHADO' | 'BLOQUEADO'
  regime: string
  caixa_tatico: number
  analise: string
  posicoes: PosicaoAnalise[]
}

/* ─── Constants ──────────────────────────────────────────────────────────── */

const MODULO_LABELS: Record<string, string> = {
  etfs: 'ETFs', fiis: 'FIIs', renda_fixa: 'Renda Fixa',
  momentum: 'Momentum', wheel: 'Wheel', alpha: 'Alpha',
  dividendos: 'Dividendos', teses: 'Teses', caixa: 'Caixa',
}

const MODULO_DESC: Record<string, string> = {
  etfs: 'Índices diversificados', fiis: 'Fundos imobiliários',
  renda_fixa: 'Títulos e CDBs', momentum: 'Ações com tendência',
  wheel: 'Estratégia de opções', alpha: 'Ações de valor',
  dividendos: 'Pagadoras de proventos', teses: 'Convicções pessoais',
  caixa: 'Reserva e liquidez',
}

const REGIME_CONFIG: Record<string, { color: string; bg: string }> = {
  BULL: { color: '#00E676', bg: 'rgba(0,230,118,0.1)' },
  MISTO: { color: '#FFD740', bg: 'rgba(255,215,64,0.1)' },
  BEAR: { color: '#FF5252', bg: 'rgba(255,82,82,0.1)' },
}

const PRIO_CONFIG = {
  ALTA: { color: '#FF5252', bg: 'rgba(255,82,82,0.08)', border: 'rgba(255,82,82,0.2)', label: 'Prioridade Alta' },
  MEDIA: { color: '#FFD740', bg: 'rgba(255,215,64,0.08)', border: 'rgba(255,215,64,0.2)', label: 'Prioridade Média' },
  BAIXA: { color: '#64748b', bg: 'rgba(100,116,139,0.06)', border: 'rgba(100,116,139,0.15)', label: 'Prioridade Baixa' },
  NEUTRA: { color: '#475569', bg: '#0d1117', border: '#1e293b', label: 'Neutro' },
}

const STATUS_CONFIG = {
  ABAIXO: { color: '#FF5252', icon: TrendingDown, label: 'Abaixo do alvo' },
  ACIMA: { color: '#00E676', icon: TrendingUp, label: 'Acima do alvo' },
  ALINHADO: { color: '#FFD740', icon: Target, label: 'Alinhado' },
  BLOQUEADO: { color: '#64748b', icon: Ban, label: 'Bloqueado pelo regime' },
}

function fmt(v: number): string {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
}

/* ─── Module Card (landing) ──────────────────────────────────────────────── */

function ModuloCard({ m, onClick }: { m: ModuloResumo; onClick: () => void }) {
  const abaixo = m.desvio_pp < -2
  const acima = m.desvio_pp > 2

  return (
    <motion.button
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 transition-all duration-200 group"
      style={{
        background: abaixo ? 'rgba(255,82,82,0.04)' : '#0d1117',
        border: `1px solid ${abaixo ? 'rgba(255,82,82,0.15)' : '#1e293b'}`,
      }}
      whileHover={{ scale: 1.01 }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = '#00E67660' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = abaixo ? 'rgba(255,82,82,0.15)' : '#1e293b' }}
    >
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="text-sm font-semibold" style={{ color: '#f1f5f9' }}>
            {MODULO_LABELS[m.modulo] || m.modulo}
          </span>
          <span className="text-xs ml-2" style={{ color: '#475569' }}>
            {MODULO_DESC[m.modulo] || ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: '#475569' }}>
            {m.posicoes} {m.posicoes === 1 ? 'pos' : 'pos'}
          </span>
          <ChevronRight size={16} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: '#00E676' }} />
        </div>
      </div>

      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#1e293b' }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(m.alvo_pct > 0 ? (m.real_pct / m.alvo_pct) * 100 : 0, 100)}%`,
              background: abaixo ? '#FF5252' : acima ? '#FFD740' : '#00E676',
            }}
          />
        </div>
        <span className="text-xs font-mono w-16 text-right" style={{
          color: abaixo ? '#FF5252' : acima ? '#00E676' : '#475569',
        }}>
          {m.desvio_pp > 0 ? '+' : ''}{m.desvio_pp.toFixed(1)}pp
        </span>
      </div>

      <div className="flex items-center justify-between text-xs" style={{ color: '#64748b' }}>
        <span>
          Real <strong style={{ color: '#94a3b8' }}>{m.real_pct.toFixed(1)}%</strong>
          {' / '}
          Alvo <strong style={{ color: '#94a3b8' }}>{m.alvo_pct.toFixed(1)}%</strong>
        </span>
        <span>{fmt(m.valor_atual)}</span>
      </div>
    </motion.button>
  )
}

/* ─── Position Row (module detail) ───────────────────────────────────────── */

function PosicaoRow({ p, onPesoSaved }: { p: PosicaoAnalise; onPesoSaved: () => void }) {
  const prio = PRIO_CONFIG[p.prioridade] || PRIO_CONFIG.NEUTRA
  const plColor = p.pl_pct >= 0 ? '#00E676' : '#FF5252'
  const [editingPeso, setEditingPeso] = useState(false)
  const [pesoValue, setPesoValue] = useState('')
  const [savingPeso, setSavingPeso] = useState(false)

  const handleSavePeso = async () => {
    const val = parseFloat(pesoValue.replace(',', '.'))
    if (isNaN(val) || val < 0 || val > 100) return
    setSavingPeso(true)
    try {
      await api.patch(`/portfolio/posicoes/${p.id}`, { peso_alvo: val })
      setEditingPeso(false)
      onPesoSaved()
    } catch { /* ignore */ }
    finally { setSavingPeso(false) }
  }

  // RSI color
  const rsiColor = p.rsi14 == null ? '#475569'
    : p.rsi14 < 30 ? '#00E676'
    : p.rsi14 < 45 ? '#00BFA5'
    : p.rsi14 < 65 ? '#FFD740'
    : p.rsi14 < 75 ? '#FF9800'
    : '#FF5252'

  // Multiplicador badge
  const multColor = p.multiplicador >= 1.5 ? '#00E676'
    : p.multiplicador > 1.0 ? '#00BFA5'
    : p.multiplicador === 1.0 ? '#FFD740'
    : p.multiplicador > 0 ? '#FF9800'
    : '#FF5252'

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: prio.bg, border: `1px solid ${prio.border}` }}
    >
      {/* Header: ticker + priority + PL */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold font-mono" style={{ color: '#f1f5f9' }}>
            {p.ticker}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
            background: prio.bg, border: `1px solid ${prio.border}`, color: prio.color,
          }}>
            {prio.label}
          </span>
          {/* Multiplicador badge */}
          {p.multiplicador !== 1.0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-medium" style={{
              background: `${multColor}10`, border: `1px solid ${multColor}30`, color: multColor,
            }}>
              {p.multiplicador.toFixed(2)}x
            </span>
          )}
        </div>
        <span className="text-sm font-mono font-semibold" style={{ color: plColor }}>
          {p.pl_pct >= 0 ? '+' : ''}{p.pl_pct.toFixed(1)}%
        </span>
      </div>

      {/* Barra: peso real vs alvo no módulo */}
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 h-1.5 rounded-full" style={{ background: '#1e293b' }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(p.pct_do_modulo, 100)}%`,
              background: p.pct_do_modulo < p.peso_ideal_pct * 0.60 ? '#FF5252'
                : p.pct_do_modulo < p.peso_ideal_pct * 0.85 ? '#FFD740' : '#00BFA5',
            }}
          />
        </div>
        <span className="text-[10px] font-mono" style={{ color: '#64748b' }}>
          {p.pct_do_modulo.toFixed(0)}%
        </span>

        {/* Peso alvo inline editor */}
        {editingPeso ? (
          <div className="flex items-center gap-1">
            <span className="text-[10px]" style={{ color: '#475569' }}>alvo</span>
            <input
              type="text"
              value={pesoValue}
              onChange={e => setPesoValue(e.target.value)}
              className="w-12 text-[11px] font-mono rounded px-1 py-0.5 text-center"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
              autoFocus
              onKeyDown={e => {
                if (e.key === 'Enter') handleSavePeso()
                if (e.key === 'Escape') setEditingPeso(false)
              }}
            />
            <span className="text-[10px]" style={{ color: '#475569' }}>%</span>
            <button onClick={handleSavePeso} disabled={savingPeso} className="p-0.5" style={{ color: '#00E676' }}>
              <Check size={12} />
            </button>
            <button onClick={() => setEditingPeso(false)} className="p-0.5" style={{ color: '#64748b' }}>
              <X size={12} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => { setPesoValue(p.peso_alvo != null ? String(p.peso_alvo) : ''); setEditingPeso(true) }}
            className="flex items-center gap-1 text-[10px] font-mono transition-colors"
            style={{ color: p.peso_alvo != null ? '#00BFA5' : '#334155' }}
            onMouseEnter={e => (e.currentTarget.style.color = '#00E676')}
            onMouseLeave={e => (e.currentTarget.style.color = p.peso_alvo != null ? '#00BFA5' : '#334155')}
            title="Definir peso alvo neste módulo"
          >
            <Target size={10} />
            {p.peso_alvo != null ? `${p.peso_alvo}%` : 'def. alvo'}
          </button>
        )}
      </div>

      {/* Dados: Qtd, PM, Atual, Valor + R$ sugerido */}
      <div className="grid grid-cols-5 gap-2 text-xs mb-2" style={{ color: '#64748b' }}>
        <div>
          <span className="block text-[10px]" style={{ color: '#475569' }}>Qtd</span>
          <span style={{ color: '#94a3b8' }}>{p.quantidade}</span>
        </div>
        <div>
          <span className="block text-[10px]" style={{ color: '#475569' }}>PM</span>
          <span style={{ color: '#94a3b8' }}>R${p.preco_medio.toFixed(2)}</span>
        </div>
        <div>
          <span className="block text-[10px]" style={{ color: '#475569' }}>Atual</span>
          <span style={{ color: '#94a3b8' }}>R${p.preco_atual.toFixed(2)}</span>
        </div>
        <div>
          <span className="block text-[10px]" style={{ color: '#475569' }}>Valor</span>
          <span style={{ color: '#94a3b8' }}>{fmt(p.valor_atual)}</span>
        </div>
        {p.valor_sugerido > 0 && (
          <div>
            <span className="block text-[10px]" style={{ color: '#00E676' }}>Aportar</span>
            <span className="font-semibold" style={{ color: '#00E676' }}>{fmt(p.valor_sugerido)}</span>
            {p.qtd_sugerida > 0 && (
              <span className="block text-[9px]" style={{ color: '#475569' }}>
                ≈ {p.qtd_sugerida} un
              </span>
            )}
          </div>
        )}
      </div>

      {/* RSI + MA50 timing row */}
      {p.rsi14 != null && (
        <div className="flex items-center gap-3 mb-2 py-1.5 px-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
          <Activity size={12} style={{ color: rsiColor }} />
          {/* RSI gauge */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px]" style={{ color: '#475569' }}>RSI</span>
            <div className="w-16 h-1.5 rounded-full" style={{ background: '#1e293b' }}>
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.min(p.rsi14, 100)}%`, background: rsiColor }}
              />
            </div>
            <span className="text-[10px] font-mono font-semibold" style={{ color: rsiColor }}>
              {p.rsi14.toFixed(0)}
            </span>
          </div>
          {/* MA50 */}
          {p.ma50 != null && (
            <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
              background: p.abaixo_ma50 ? 'rgba(0,230,118,0.08)' : 'rgba(255,215,64,0.08)',
              color: p.abaixo_ma50 ? '#00E676' : '#FFD740',
            }}>
              {p.abaixo_ma50 ? '↓' : '↑'} MA50
            </span>
          )}
          {/* Sinal */}
          <span className="text-[10px] ml-auto" style={{ color: '#64748b' }}>
            {p.sinal_timing.split(' — ')[0]}
          </span>
        </div>
      )}

      {/* Sugestão */}
      <p className="text-xs leading-relaxed" style={{ color: prio.color }}>
        {p.sugestao}
      </p>
    </div>
  )
}

/* ─── Module Detail View ─────────────────────────────────────────────────── */

function ModuloDetailView({
  analise, loading, onBack, onPesoSaved,
}: {
  analise: ModuloAnalise | null
  loading: boolean
  onBack: () => void
  onPesoSaved: () => void
}) {
  if (loading) {
    return (
      <div className="space-y-5">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: '#64748b' }}
        >
          <ArrowLeft size={16} /> Voltar
        </button>
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin" style={{ color: '#00E676' }} />
          <span className="ml-3 text-sm" style={{ color: '#64748b' }}>Analisando posições...</span>
        </div>
      </div>
    )
  }

  if (!analise) return null

  const statusCfg = STATUS_CONFIG[analise.status] || STATUS_CONFIG.ALINHADO
  const StatusIcon = statusCfg.icon
  const altaPrio = analise.posicoes.filter(p => p.prioridade === 'ALTA')
  const mediaPrio = analise.posicoes.filter(p => p.prioridade === 'MEDIA')
  const outrasPrio = analise.posicoes.filter(p => p.prioridade !== 'ALTA' && p.prioridade !== 'MEDIA')
  const regimeCfg = REGIME_CONFIG[analise.regime] || REGIME_CONFIG.MISTO

  return (
    <div className="space-y-5">
      {/* Back */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-sm transition-colors"
        style={{ color: '#64748b' }}
        onMouseEnter={e => (e.currentTarget.style.color = '#00E676')}
        onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
      >
        <ArrowLeft size={16} /> Voltar aos módulos
      </button>

      {/* Header */}
      <div className="rounded-xl p-5" style={{ background: '#0d1117', border: '1px solid #1e293b' }}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold" style={{ color: '#f1f5f9' }}>
            {analise.modulo_label}
          </h2>
          <div className="flex items-center gap-3">
            {/* Regime badge */}
            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
              background: regimeCfg.bg, border: `1px solid ${regimeCfg.color}40`, color: regimeCfg.color,
            }}>
              {analise.regime}
            </span>
            <div className="flex items-center gap-2">
              <StatusIcon size={16} style={{ color: statusCfg.color }} />
              <span className="text-sm font-medium" style={{ color: statusCfg.color }}>
                {statusCfg.label}
              </span>
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Valor no módulo</p>
            <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>{fmt(analise.valor_atual_modulo)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Desvio</p>
            <p className="text-sm font-mono font-bold" style={{ color: statusCfg.color }}>
              {analise.desvio_pp > 0 ? '+' : ''}{analise.desvio_pp.toFixed(1)}pp
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Aporte sugerido</p>
            <p className="text-sm font-mono font-bold" style={{ color: '#00E676' }}>
              {fmt(analise.valor_sugerido)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Posições</p>
            <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
              {analise.posicoes.length}
            </p>
          </div>
        </div>

        {/* Caixa tático */}
        {analise.caixa_tatico > 0 && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg" style={{
            background: 'rgba(255,215,64,0.05)', border: '1px solid rgba(255,215,64,0.15)',
          }}>
            <PiggyBank size={14} style={{ color: '#FFD740' }} />
            <span className="text-xs" style={{ color: '#FFD740' }}>
              Caixa tático: <strong className="font-mono">{fmt(analise.caixa_tatico)}</strong>
            </span>
            <span className="text-[10px] ml-auto" style={{ color: '#64748b' }}>
              Timing desfavorável — acumular e usar em oportunidades
            </span>
          </div>
        )}

        {/* Bar: real vs alvo */}
        <div className="flex items-center gap-3">
          <span className="text-xs" style={{ color: '#475569' }}>Real {analise.real_pct.toFixed(1)}%</span>
          <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: '#1e293b' }}>
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(analise.alvo_pct > 0 ? (analise.real_pct / analise.alvo_pct) * 100 : 0, 100)}%`,
                background: statusCfg.color,
              }}
            />
          </div>
          <span className="text-xs" style={{ color: '#475569' }}>Alvo {analise.alvo_pct.toFixed(1)}%</span>
        </div>
      </div>

      {/* Análise */}
      <div className="rounded-xl p-4" style={{ background: '#0d1117', border: '1px solid #1e293b' }}>
        <p className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>{analise.analise}</p>
      </div>

      {/* Posições por prioridade */}
      {analise.posicoes.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-sm" style={{ color: '#475569' }}>
            Nenhuma posição ativa neste módulo. Adicione posições para receber recomendações.
          </p>
        </div>
      ) : (
        <>
          {altaPrio.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: '#FF5252' }}>
                <Target size={14} /> Prioridade Alta — aportar aqui
              </h3>
              <div className="space-y-2">
                {altaPrio.map(p => <PosicaoRow key={p.ticker} p={p} onPesoSaved={onPesoSaved} />)}
              </div>
            </div>
          )}

          {mediaPrio.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: '#FFD740' }}>
                <DollarSign size={14} /> Prioridade Média — considerar
              </h3>
              <div className="space-y-2">
                {mediaPrio.map(p => <PosicaoRow key={p.ticker} p={p} onPesoSaved={onPesoSaved} />)}
              </div>
            </div>
          )}

          {outrasPrio.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: '#475569' }}>
                Demais posições
              </h3>
              <div className="space-y-2">
                {outrasPrio.map(p => <PosicaoRow key={p.ticker} p={p} onPesoSaved={onPesoSaved} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ─── Main Page ──────────────────────────────────────────────────────────── */

export default function AportesPage() {
  const [resumo, setResumo] = useState<ResumoData | null>(null)
  const [loadingResumo, setLoadingResumo] = useState(true)

  const [analise, setAnalise] = useState<ModuloAnalise | null>(null)
  const [loadingAnalise, setLoadingAnalise] = useState(false)
  const [moduloAtual, setModuloAtual] = useState<string | null>(null)
  const [view, setView] = useState<'modulos' | 'detalhe'>('modulos')

  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchResumo = useCallback(async () => {
    setLoadingResumo(true)
    try {
      const r = await api.get('/portfolio/aporte-resumo')
      setResumo(r.data)
    } catch { /* silent */ }
    finally { setLoadingResumo(false) }
  }, [])

  useEffect(() => { fetchResumo() }, [fetchResumo])

  const handleModuloClick = async (modulo: string) => {
    setLoadingAnalise(true)
    setView('detalhe')
    setModuloAtual(modulo)
    setAnalise(null)
    try {
      const r = await api.post('/portfolio/analisar-modulo', { modulo })
      setAnalise(r.data)
    } catch { /* silent */ }
    finally { setLoadingAnalise(false) }
  }

  const handleRefreshModulo = async () => {
    if (!moduloAtual) return
    try {
      const r = await api.post('/portfolio/analisar-modulo', { modulo: moduloAtual })
      setAnalise(r.data)
    } catch { /* silent */ }
  }

  const handleBack = () => {
    setView('modulos')
    setAnalise(null)
    setModuloAtual(null)
  }

  const handleSaveAporte = async () => {
    const valor = parseFloat(editValue.replace(/[^\d.,]/g, '').replace(',', '.'))
    if (isNaN(valor) || valor < 0) return
    setSaving(true)
    try {
      await api.patch('/portfolio/aporte-mensal', { aporte_mensal: valor })
      setEditing(false)
      await fetchResumo()
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  /* ── Loading ──────────────────────────────────────────────────────── */
  if (loadingResumo) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0a0e17' }}>
        <div className="text-center space-y-3">
          <Loader2 className="w-8 h-8 animate-spin mx-auto" style={{ color: '#00E676' }} />
          <p className="text-sm" style={{ color: '#64748b' }}>Carregando módulos...</p>
        </div>
      </div>
    )
  }

  if (!resumo) return null

  const regime = REGIME_CONFIG[resumo.regime] || REGIME_CONFIG.MISTO
  const modulosAtivos = resumo.modulos
    .filter(m => m.alvo_pct > 0)
    .sort((a, b) => a.desvio_pp - b.desvio_pp)
  const modulosAbaixo = modulosAtivos.filter(m => m.desvio_pp < -2)

  return (
    <div className="min-h-screen p-6 md:p-8 max-w-4xl mx-auto space-y-6" style={{ background: '#0a0e17' }}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Aportes Inteligentes</h1>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            Clique em um módulo para analisar os ativos
          </p>
        </div>
        <button
          onClick={fetchResumo}
          className="p-2 rounded-lg transition-colors"
          style={{ color: '#64748b' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#00E676')}
          onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
          title="Atualizar"
        >
          <RefreshCw size={18} />
        </button>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Aporte mensal */}
        <div className="rounded-xl p-4" style={{ background: '#0d1117', border: '1px solid #1e293b' }}>
          <div className="flex items-center gap-2 mb-2">
            <PiggyBank size={14} style={{ color: '#00E676' }} />
            <span className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Aporte/mês</span>
          </div>
          {editing ? (
            <div className="flex items-center gap-1">
              <input
                type="text"
                value={editValue}
                onChange={e => setEditValue(e.target.value)}
                className="w-full text-sm font-mono font-bold rounded px-2 py-1"
                style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
                autoFocus
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSaveAporte()
                  if (e.key === 'Escape') setEditing(false)
                }}
              />
              <button onClick={handleSaveAporte} disabled={saving} className="p-1" style={{ color: '#00E676' }}>
                <Check size={14} />
              </button>
              <button onClick={() => setEditing(false)} className="p-1" style={{ color: '#64748b' }}>
                <X size={14} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-lg font-mono font-bold" style={{ color: '#f1f5f9' }}>
                {fmt(resumo.aporte_mensal)}
              </p>
              <button
                onClick={() => { setEditValue(String(resumo.aporte_mensal)); setEditing(true) }}
                className="p-1 rounded"
                style={{ color: '#475569' }}
                onMouseEnter={e => (e.currentTarget.style.color = '#00E676')}
                onMouseLeave={e => (e.currentTarget.style.color = '#475569')}
              >
                <Edit3 size={12} />
              </button>
            </div>
          )}
        </div>

        {/* Patrimônio */}
        <div className="rounded-xl p-4" style={{ background: '#0d1117', border: '1px solid #1e293b' }}>
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 size={14} style={{ color: '#00BFA5' }} />
            <span className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Patrimônio</span>
          </div>
          <p className="text-lg font-mono font-bold" style={{ color: '#f1f5f9' }}>
            {fmt(resumo.patrimonio_atual)}
          </p>
        </div>

        {/* Regime */}
        <div className="rounded-xl p-4" style={{ background: regime.bg, border: `1px solid ${regime.color}33` }}>
          <div className="flex items-center gap-2 mb-2">
            <Shield size={14} style={{ color: regime.color }} />
            <span className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Regime</span>
          </div>
          <p className="text-lg font-mono font-bold" style={{ color: regime.color }}>{resumo.regime}</p>
        </div>

        {/* Módulos abaixo */}
        <div className="rounded-xl p-4" style={{
          background: modulosAbaixo.length > 0 ? 'rgba(255,82,82,0.06)' : '#0d1117',
          border: `1px solid ${modulosAbaixo.length > 0 ? 'rgba(255,82,82,0.2)' : '#1e293b'}`,
        }}>
          <div className="flex items-center gap-2 mb-2">
            <Target size={14} style={{ color: modulosAbaixo.length > 0 ? '#FF5252' : '#475569' }} />
            <span className="text-[10px] uppercase tracking-wider" style={{ color: '#475569' }}>Precisam aporte</span>
          </div>
          <p className="text-lg font-mono font-bold" style={{ color: modulosAbaixo.length > 0 ? '#FF5252' : '#475569' }}>
            {modulosAbaixo.length} {modulosAbaixo.length === 1 ? 'módulo' : 'módulos'}
          </p>
        </div>
      </div>

      {/* Content: modules or detail */}
      <AnimatePresence mode="wait">
        {view === 'modulos' ? (
          <motion.div
            key="modulos"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-5"
          >
            {/* Warning if no allocation */}
            {!resumo.alocacao_configurada && (
              <div className="rounded-xl p-4 flex items-start gap-3" style={{ background: 'rgba(255,215,64,0.06)', border: '1px solid rgba(255,215,64,0.15)' }}>
                <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" style={{ color: '#FFD740' }} />
                <div>
                  <p className="text-sm font-medium" style={{ color: '#FFD740' }}>Alocação não configurada</p>
                  <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
                    Defina os alvos de alocação por módulo nas Configurações.
                  </p>
                </div>
              </div>
            )}

            {/* Modules below target */}
            {modulosAbaixo.length > 0 && (
              <div>
                <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: '#FF5252' }}>
                  <AlertTriangle size={14} />
                  Abaixo do alvo — clique para analisar
                </h2>
                <div className="grid gap-2">
                  {modulosAbaixo.map(m => (
                    <ModuloCard key={m.modulo} m={m} onClick={() => handleModuloClick(m.modulo)} />
                  ))}
                </div>
              </div>
            )}

            {/* All modules */}
            <div>
              <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: '#f1f5f9' }}>
                <DollarSign size={14} style={{ color: '#00E676' }} />
                Todos os Módulos
              </h2>
              <div className="grid gap-2">
                {modulosAtivos.map(m => (
                  <ModuloCard key={m.modulo} m={m} onClick={() => handleModuloClick(m.modulo)} />
                ))}
              </div>
              {modulosAtivos.length === 0 && (
                <p className="text-sm text-center py-8" style={{ color: '#475569' }}>
                  Nenhum módulo configurado com alvo &gt; 0%.
                </p>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="detalhe"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <ModuloDetailView
              analise={analise}
              loading={loadingAnalise}
              onBack={handleBack}
              onPesoSaved={handleRefreshModulo}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
