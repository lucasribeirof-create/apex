/**
 * Modal de detalhes completos de uma posição.
 * Abas: Resumo | Transações | Análise AI
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, TrendingUp, TrendingDown, BrainCircuit, Plus, Trash2,
  CalendarDays, ArrowDownCircle, ArrowUpCircle, RotateCcw,
  Target, ShieldAlert, BarChart2, Pencil, Check, Save,
} from 'lucide-react'
import api from '@/services/api'
import AnaliseModal from '@/components/AnaliseModal'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface PositionDetalhe {
  id: number
  ticker: string
  nome?: string
  tipo: string
  modulo: string
  quantidade: number
  preco_medio: number
  preco_atual: number
  valor_investido: number
  valor_atual: number
  pl_reais: number
  pl_percentual: number
  stop_loss?: number | null
  alvo_1?: number | null
  alvo_2?: number | null
  apex_score?: number | null
  data_abertura?: string | null
  data_entrada?: string | null
  tese?: string | null
  justificativa_entrada?: string | null
  moeda?: string
  mercado?: string
}

interface Transacao {
  id: number
  tipo: string
  data: string
  quantidade: number
  preco: number
  valor_total: number
  taxas: number
  observacao?: string | null
}

interface Props {
  position: PositionDetalhe
  onClose: () => void
  onUpdate?: () => void
}

const TIPO_TX_LABELS: Record<string, string> = {
  compra: 'Compra',
  dca: 'DCA / Aporte',
  venda_parcial: 'Venda Parcial',
  venda_total: 'Venda Total',
  bonificacao: 'Bonificação',
  split: 'Desdobramento',
  amortizacao: 'Amortização',
}

const TIPO_TX_COLORS: Record<string, string> = {
  compra: '#00E676',
  dca: '#00BCD4',
  venda_parcial: '#FF9800',
  venda_total: '#FF5252',
  bonificacao: '#B2FF59',
  split: '#80DEEA',
  amortizacao: '#FFCA28',
}

const TIPO_TX_ICONS: Record<string, React.ReactNode> = {
  compra: <ArrowDownCircle size={13} />,
  dca: <RotateCcw size={13} />,
  venda_parcial: <ArrowUpCircle size={13} />,
  venda_total: <ArrowUpCircle size={13} />,
  bonificacao: <Plus size={13} />,
  split: <BarChart2 size={13} />,
  amortizacao: <ArrowUpCircle size={13} />,
}

const MODULO_LABEL: Record<string, string> = {
  etfs: 'ETFs', fiis: 'FIIs', momentum: 'Momentum', wheel: 'Wheel',
  renda_fixa: 'Renda Fixa', alpha: 'Alpha', dividendos: 'Dividendos',
  teses: 'Teses', caixa: 'Caixa',
}

function formatDate(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR')
}

function formatMoney(v: number, decimals = 2) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── Nova Transação Form ──────────────────────────────────────────────────────

function NovaTransacaoForm({
  positionId,
  onSaved,
  onCancel,
}: {
  positionId: number
  onSaved: () => void
  onCancel: () => void
}) {
  const [tipo, setTipo] = useState('compra')
  const [data, setData] = useState(new Date().toISOString().slice(0, 10))
  const [quantidade, setQuantidade] = useState('')
  const [preco, setPreco] = useState('')
  const [taxas, setTaxas] = useState('')
  const [observacao, setObservacao] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const handleSave = async () => {
    if (!quantidade || !preco) { setErr('Preencha Quantidade e Preço'); return }
    setSaving(true)
    try {
      await api.post(`/portfolio/posicoes/${positionId}/transacoes`, {
        tipo,
        data: new Date(data).toISOString(),
        quantidade: parseFloat(quantidade),
        preco: parseFloat(preco),
        taxas: taxas ? parseFloat(taxas) : 0,
        observacao: observacao || null,
      })
      onSaved()
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Erro ao salvar')
    }
    setSaving(false)
  }

  return (
    <div
      className="rounded-xl p-4 space-y-3"
      style={{ background: 'rgba(0,230,118,0.04)', border: '1px solid rgba(0,230,118,0.15)' }}
    >
      <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#00E676' }}>Nova Transação</p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Tipo</label>
          <select
            value={tipo}
            onChange={e => setTipo(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-xs outline-none"
            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9', cursor: 'pointer' }}
          >
            {Object.entries(TIPO_TX_LABELS).map(([k, v]) => (
              <option key={k} value={k} style={{ background: '#0a0e17' }}>{v}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Data</label>
          <input
            type="date"
            value={data}
            onChange={e => setData(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-xs outline-none"
            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9', colorScheme: 'dark' }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Quantidade</label>
          <input
            type="number" min={0} step="any"
            value={quantidade}
            onChange={e => setQuantidade(e.target.value)}
            placeholder="100"
            className="w-full px-3 py-2 rounded-lg text-xs outline-none"
            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Preço (R$)</label>
          <input
            type="number" min={0} step="any"
            value={preco}
            onChange={e => setPreco(e.target.value)}
            placeholder="35.50"
            className="w-full px-3 py-2 rounded-lg text-xs outline-none"
            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Taxas (R$)</label>
          <input
            type="number" min={0} step="any"
            value={taxas}
            onChange={e => setTaxas(e.target.value)}
            placeholder="0.00"
            className="w-full px-3 py-2 rounded-lg text-xs outline-none"
            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
          />
        </div>
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: '#64748b' }}>Observação</label>
        <input
          value={observacao}
          onChange={e => setObservacao(e.target.value)}
          placeholder="ex: Aporte mensal planejado"
          className="w-full px-3 py-2 rounded-lg text-xs outline-none"
          style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
        />
      </div>

      {err && <p className="text-xs" style={{ color: '#FF5252' }}>{err}</p>}

      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="flex-1 py-2 rounded-lg text-xs transition-all"
          style={{ color: '#475569', border: '1px solid #1e293b' }}
        >
          Cancelar
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-[2] py-2 rounded-lg text-xs font-medium transition-all"
          style={{ background: 'rgba(0,230,118,0.12)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
        >
          {saving ? 'Salvando...' : 'Registrar Transação'}
        </button>
      </div>
    </div>
  )
}

// ─── Main Modal ───────────────────────────────────────────────────────────────

export default function PosicaoDetalheModal({ position, onClose, onUpdate }: Props) {
  const [tab, setTab] = useState<'resumo' | 'transacoes' | 'ai'>('resumo')
  const [transacoes, setTransacoes] = useState<Transacao[]>([])
  const [loadingTx, setLoadingTx] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [showAnalise, setShowAnalise] = useState(false)
  const [fundamentos, setFundamentos] = useState<Record<string, any> | null>(null)
  const [loadingFund, setLoadingFund] = useState(false)
  const fundLoadedRef = useRef<number | null>(null)

  // ── Edição inline ──
  const [editMode, setEditMode] = useState(false)
  const [editValues, setEditValues] = useState({
    quantidade: '',
    preco_medio: '',
    stop_loss: '',
    alvo_1: '',
    alvo_2: '',
    tese: '',
    modulo: '',
  })
  const [saving, setSaving] = useState(false)

  const enterEditMode = useCallback(() => {
    setEditValues({
      quantidade: position.quantidade.toString(),
      preco_medio: position.preco_medio.toString(),
      stop_loss: position.stop_loss?.toString() ?? '',
      alvo_1: position.alvo_1?.toString() ?? '',
      alvo_2: position.alvo_2?.toString() ?? '',
      tese: position.tese ?? '',
      modulo: position.modulo || '',
    })
    setEditMode(true)
  }, [position])

  const cancelEdit = useCallback(() => setEditMode(false), [])

  const saveEdit = useCallback(async () => {
    setSaving(true)
    try {
      const payload: Record<string, any> = {}
      const qty = parseFloat(editValues.quantidade)
      const pm = parseFloat(editValues.preco_medio)
      const sl = parseFloat(editValues.stop_loss)
      const a1 = parseFloat(editValues.alvo_1)
      const a2 = parseFloat(editValues.alvo_2)

      if (!isNaN(qty) && qty !== position.quantidade) payload.quantidade = qty
      if (!isNaN(pm) && pm !== position.preco_medio) payload.preco_medio = pm
      payload.stop_loss = !isNaN(sl) && sl > 0 ? sl : 0
      payload.alvo_1 = !isNaN(a1) && a1 > 0 ? a1 : 0
      payload.alvo_2 = !isNaN(a2) && a2 > 0 ? a2 : 0
      if (editValues.tese !== (position.tese ?? '')) payload.tese = editValues.tese || ''
      if (editValues.modulo !== position.modulo) payload.modulo = editValues.modulo

      await api.patch(`/portfolio/posicoes/${position.id}`, payload)
      setEditMode(false)
      onUpdate?.()
    } catch { /* silent */ }
    setSaving(false)
  }, [editValues, position, onUpdate])

  const plColor = position.pl_percentual > 0 ? '#00E676' : position.pl_percentual < 0 ? '#FF5252' : '#94a3b8'
  const plBg = position.pl_percentual > 0 ? 'rgba(0,230,118,0.08)' : position.pl_percentual < 0 ? 'rgba(255,82,82,0.08)' : 'rgba(148,163,184,0.08)'

  // Reset fundamentos quando posição muda
  useEffect(() => {
    setFundamentos(null)
    setLoadingFund(false)
    fundLoadedRef.current = null
  }, [position.id])

  const loadTransacoes = async () => {
    setLoadingTx(true)
    try {
      const res = await api.get(`/portfolio/posicoes/${position.id}/transacoes`)
      setTransacoes(res.data)
    } catch { /* silent */ }
    setLoadingTx(false)
  }

  useEffect(() => {
    if (tab === 'transacoes') loadTransacoes()
  }, [tab])

  // Carrega dados fundamentalistas ao abrir Resumo (lazy, 1x por posição)
  useEffect(() => {
    const tiposFund = ['ACAO', 'FII', 'ETF', 'BDR']
    if (tab === 'resumo' && tiposFund.includes(position.tipo) && fundLoadedRef.current !== position.id && !loadingFund) {
      setLoadingFund(true)
      fundLoadedRef.current = position.id
      api.get(`/portfolio/posicoes/${position.id}/fundamentals`)
        .then(res => setFundamentos(res.data?.dados ?? null))
        .catch(() => setFundamentos(null))
        .finally(() => setLoadingFund(false))
    }
  }, [tab, position.id])

  const deletarTransacao = async (id: number) => {
    if (!confirm('Remover esta transação? O P&L será recalculado.')) return
    try {
      await api.delete(`/portfolio/transacoes/${id}`)
      await loadTransacoes()
      onUpdate?.()
    } catch { /* silent */ }
  }

  const onTransacaoSaved = async () => {
    setShowForm(false)
    await loadTransacoes()
    onUpdate?.()
  }

  const tabs = [
    { id: 'resumo' as const, label: 'Resumo' },
    { id: 'transacoes' as const, label: 'Transações' },
    { id: 'ai' as const, label: 'Análise AI' },
  ]

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          className="relative flex flex-col w-full rounded-xl shadow-2xl"
          style={{
            maxWidth: '700px',
            height: 'min(84vh, 780px)',
            background: '#0d1117',
            border: '1px solid #1e293b',
          }}
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-5 py-4 flex-shrink-0"
            style={{ borderBottom: '1px solid #1e293b' }}
          >
            <div className="flex items-center gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-lg" style={{ color: '#f1f5f9' }}>{position.ticker}</span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold"
                    style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}
                  >
                    {position.tipo}
                  </span>
                  {position.moeda && position.moeda !== 'BRL' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono" style={{ background: 'rgba(41,121,255,0.1)', color: '#2979FF', border: '1px solid rgba(41,121,255,0.2)' }}>
                      {position.moeda}
                    </span>
                  )}
                </div>
                {position.nome && position.nome !== position.ticker && (
                  <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{position.nome}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-sm font-mono font-bold px-2.5 py-1 rounded-lg flex items-center gap-1"
                style={{ background: plBg, color: plColor }}
              >
                {position.pl_percentual > 0 ? <TrendingUp size={13} /> : position.pl_percentual < 0 ? <TrendingDown size={13} /> : null}
                {position.pl_percentual > 0 ? '+' : ''}{position.pl_percentual.toFixed(2)}%
              </span>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: '#64748b' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex px-5 flex-shrink-0" style={{ borderBottom: '1px solid #1e293b' }}>
            {tabs.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className="py-3 px-4 text-xs font-medium transition-all"
                style={{
                  color: tab === t.id ? '#f1f5f9' : '#64748b',
                  borderBottom: tab === t.id ? '2px solid #00E676' : '2px solid transparent',
                  marginBottom: '-1px',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            <AnimatePresence mode="wait">

              {/* ── Aba Resumo ── */}
              {tab === 'resumo' && (
                <motion.div
                  key="resumo"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="p-5 space-y-4"
                >
                  {/* P&L cards */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid #1e293b' }}>
                      <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#64748b' }}>Valor Atual</p>
                      <p className="text-xl font-bold font-mono" style={{ color: '#f1f5f9' }}>
                        R$ {formatMoney(position.valor_atual, 0)}
                      </p>
                    </div>
                    <div className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid #1e293b' }}>
                      <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#64748b' }}>P&L Total</p>
                      <p className="text-xl font-bold font-mono" style={{ color: plColor }}>
                        {position.pl_reais > 0 ? '+' : ''}R$ {formatMoney(position.pl_reais, 2)}
                      </p>
                    </div>
                  </div>

                  {/* Detalhes da posição */}
                  <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #1e293b' }}>
                    {/* Header com botão editar */}
                    <div className="flex items-center justify-between px-4 py-2" style={{ background: 'rgba(30,41,59,0.3)' }}>
                      <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Dados da Posição</span>
                      {!editMode ? (
                        <button onClick={enterEditMode} className="flex items-center gap-1 text-[10px] transition-all" style={{ color: '#a78bfa' }}
                          onMouseEnter={e => (e.currentTarget.style.color = '#c4b5fd')}
                          onMouseLeave={e => (e.currentTarget.style.color = '#a78bfa')}
                        >
                          <Pencil size={10} /> Editar
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <button onClick={cancelEdit} className="text-[10px]" style={{ color: '#64748b' }}>Cancelar</button>
                          <button
                            onClick={saveEdit}
                            disabled={saving}
                            className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md transition-all"
                            style={{ background: 'rgba(0,230,118,0.12)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
                          >
                            <Save size={10} /> {saving ? 'Salvando...' : 'Salvar'}
                          </button>
                        </div>
                      )}
                    </div>
                    {/* Módulo */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Módulo</span>
                      {editMode ? (
                        <select
                          value={editValues.modulo}
                          onChange={e => setEditValues(v => ({ ...v, modulo: e.target.value }))}
                          className="text-xs font-mono px-2 py-1 rounded outline-none"
                          style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9', cursor: 'pointer' }}
                        >
                          {Object.entries(MODULO_LABEL).map(([k, v]) => (
                            <option key={k} value={k} style={{ background: '#0a0e17' }}>{v}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>{MODULO_LABEL[position.modulo] || position.modulo}</span>
                      )}
                    </div>
                    {/* Mercado (read-only) */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Mercado</span>
                      <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>{position.mercado || '—'}</span>
                    </div>
                    {/* Quantidade */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Quantidade</span>
                      {editMode ? (
                        <input
                          type="number" min={0} step="any"
                          value={editValues.quantidade}
                          onChange={e => setEditValues(v => ({ ...v, quantidade: e.target.value }))}
                          className="text-xs font-mono text-right px-2 py-1 rounded outline-none w-28"
                          style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
                        />
                      ) : (
                        <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>{position.quantidade.toLocaleString('pt-BR')}</span>
                      )}
                    </div>
                    {/* Preço Médio */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Preço Médio</span>
                      {editMode ? (
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] font-mono" style={{ color: '#64748b' }}>R$</span>
                          <input
                            type="number" min={0} step="any"
                            value={editValues.preco_medio}
                            onChange={e => setEditValues(v => ({ ...v, preco_medio: e.target.value }))}
                            className="text-xs font-mono text-right px-2 py-1 rounded outline-none w-24"
                            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
                          />
                        </div>
                      ) : (
                        <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>R$ {formatMoney(position.preco_medio)}</span>
                      )}
                    </div>
                    {/* Preço Atual (read-only) */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Preço Atual</span>
                      <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>R$ {formatMoney(position.preco_atual)}</span>
                    </div>
                    {/* Valor Investido (read-only, calculated) */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span style={{ color: '#64748b' }}>Valor Investido</span>
                      <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>R$ {formatMoney(position.valor_investido, 0)}</span>
                    </div>
                    {/* Data de Abertura (read-only) */}
                    <div className="flex items-center justify-between px-4 py-2.5 text-sm" style={{ borderTop: '1px solid rgba(30,41,59,0.6)' }}>
                      <span className="flex items-center gap-1.5" style={{ color: '#64748b' }}>
                        <CalendarDays size={12} />
                        Data de Abertura
                      </span>
                      <span className="font-mono text-xs" style={{ color: '#f1f5f9' }}>
                        {position.data_abertura
                          ? formatDate(position.data_abertura)
                          : position.data_entrada
                          ? formatDate(position.data_entrada)
                          : '—'}
                      </span>
                    </div>
                  </div>

                  {/* Gestão de risco */}
                  <div className="rounded-xl p-4 space-y-2" style={{ background: '#111827', border: '1px solid #1e293b' }}>
                    <p className="text-[10px] font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>Gestão de Risco</p>
                    <div className="grid grid-cols-3 gap-3">
                      {/* Stop Loss */}
                      <div className="text-center">
                        <p className="text-[10px] mb-1 flex items-center justify-center gap-1" style={{ color: '#FF5252' }}>
                          <ShieldAlert size={10} /> Stop Loss
                        </p>
                        {editMode ? (
                          <input
                            type="number" min={0} step="any"
                            value={editValues.stop_loss}
                            onChange={e => setEditValues(v => ({ ...v, stop_loss: e.target.value }))}
                            placeholder="—"
                            className="w-full text-center text-xs font-mono px-1 py-1 rounded outline-none"
                            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#FF5252' }}
                          />
                        ) : (
                          <>
                            <p className="font-mono text-sm font-bold" style={{ color: position.stop_loss ? '#FF5252' : '#475569' }}>
                              {position.stop_loss ? `R$ ${formatMoney(position.stop_loss)}` : '—'}
                            </p>
                            {position.stop_loss && position.preco_atual > 0 && (
                              <p className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
                                {(((position.stop_loss / position.preco_atual) - 1) * 100).toFixed(1)}%
                              </p>
                            )}
                          </>
                        )}
                      </div>
                      {/* Alvo 1 */}
                      <div className="text-center">
                        <p className="text-[10px] mb-1 flex items-center justify-center gap-1" style={{ color: '#00E676' }}>
                          <Target size={10} /> Alvo 1
                        </p>
                        {editMode ? (
                          <input
                            type="number" min={0} step="any"
                            value={editValues.alvo_1}
                            onChange={e => setEditValues(v => ({ ...v, alvo_1: e.target.value }))}
                            placeholder="—"
                            className="w-full text-center text-xs font-mono px-1 py-1 rounded outline-none"
                            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#00E676' }}
                          />
                        ) : (
                          <>
                            <p className="font-mono text-sm font-bold" style={{ color: position.alvo_1 ? '#00E676' : '#475569' }}>
                              {position.alvo_1 ? `R$ ${formatMoney(position.alvo_1)}` : '—'}
                            </p>
                            {position.alvo_1 && position.preco_atual > 0 && (
                              <p className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
                                {(((position.alvo_1 / position.preco_atual) - 1) * 100).toFixed(1)}%
                              </p>
                            )}
                          </>
                        )}
                      </div>
                      {/* Alvo 2 */}
                      <div className="text-center">
                        <p className="text-[10px] mb-1 flex items-center justify-center gap-1" style={{ color: '#00BCD4' }}>
                          <Target size={10} /> Alvo 2
                        </p>
                        {editMode ? (
                          <input
                            type="number" min={0} step="any"
                            value={editValues.alvo_2}
                            onChange={e => setEditValues(v => ({ ...v, alvo_2: e.target.value }))}
                            placeholder="—"
                            className="w-full text-center text-xs font-mono px-1 py-1 rounded outline-none"
                            style={{ background: '#0a0e17', border: '1px solid #334155', color: '#00BCD4' }}
                          />
                        ) : (
                          <>
                            <p className="font-mono text-sm font-bold" style={{ color: position.alvo_2 ? '#00BCD4' : '#475569' }}>
                              {position.alvo_2 ? `R$ ${formatMoney(position.alvo_2)}` : '—'}
                            </p>
                            {position.alvo_2 && position.preco_atual > 0 && (
                              <p className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
                                {(((position.alvo_2 / position.preco_atual) - 1) * 100).toFixed(1)}%
                              </p>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Indicadores Fundamentalistas */}
                  {['ACAO', 'FII', 'ETF', 'BDR'].includes(position.tipo) && (
                    <div className="rounded-xl p-4 space-y-2" style={{ background: '#111827', border: '1px solid #1e293b' }}>
                      <p className="text-[10px] font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
                        📊 Indicadores Fundamentalistas
                      </p>
                      {loadingFund ? (
                        <div className="flex items-center justify-center py-4">
                          <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: '#334155', borderTopColor: '#818cf8' }} />
                          <span className="ml-2 text-xs" style={{ color: '#64748b' }}>Carregando...</span>
                        </div>
                      ) : fundamentos ? (
                        <div className="grid grid-cols-3 gap-3">
                          {(() => {
                            const items: { label: string; value: string; color: string }[] = []
                            const fmt = (v: number | undefined, suffix = '', dec = 2) =>
                              v != null ? v.toFixed(dec) + suffix : '—'
                            const colorRange = (v: number | undefined, green: number, yellow: number, invert = false) => {
                              if (v == null) return '#94a3b8'
                              if (invert) return v <= green ? '#00E676' : v <= yellow ? '#FFCA28' : '#FF5252'
                              return v >= green ? '#00E676' : v >= yellow ? '#FFCA28' : '#FF5252'
                            }

                            if (fundamentos.priceEarnings != null)
                              items.push({ label: 'P/L', value: fmt(fundamentos.priceEarnings, 'x', 1), color: colorRange(fundamentos.priceEarnings, 15, 25, true) })
                            if (fundamentos.priceToBookRatio != null)
                              items.push({ label: 'P/VP', value: fmt(fundamentos.priceToBookRatio, 'x', 2), color: colorRange(fundamentos.priceToBookRatio, 1.5, 3, true) })
                            if (fundamentos.dividendYield != null)
                              items.push({ label: 'Div. Yield', value: fmt(fundamentos.dividendYield * 100, '%', 1), color: colorRange(fundamentos.dividendYield * 100, 5, 3, false) })
                            if (fundamentos.returnOnEquity != null)
                              items.push({ label: 'ROE', value: fmt(fundamentos.returnOnEquity * 100, '%', 1), color: colorRange(fundamentos.returnOnEquity * 100, 15, 8, false) })
                            if (fundamentos.returnOnAssets != null)
                              items.push({ label: 'ROA', value: fmt(fundamentos.returnOnAssets * 100, '%', 1), color: colorRange(fundamentos.returnOnAssets * 100, 8, 4, false) })
                            if (fundamentos.netMargin != null)
                              items.push({ label: 'Margem Líq.', value: fmt(fundamentos.netMargin * 100, '%', 1), color: colorRange(fundamentos.netMargin * 100, 10, 5, false) })
                            if (fundamentos.grossMargin != null)
                              items.push({ label: 'Margem Bruta', value: fmt(fundamentos.grossMargin * 100, '%', 1), color: colorRange(fundamentos.grossMargin * 100, 30, 15, false) })
                            if (fundamentos.ebitdaMargin != null)
                              items.push({ label: 'Margem EBITDA', value: fmt(fundamentos.ebitdaMargin * 100, '%', 1), color: colorRange(fundamentos.ebitdaMargin * 100, 20, 10, false) })
                            if (fundamentos.debtToEquity != null)
                              items.push({ label: 'Dív/PL', value: fmt(fundamentos.debtToEquity, 'x', 2), color: colorRange(fundamentos.debtToEquity, 1, 2, true) })
                            if (fundamentos.currentLiquidity != null)
                              items.push({ label: 'Liq. Corrente', value: fmt(fundamentos.currentLiquidity, 'x', 2), color: colorRange(fundamentos.currentLiquidity, 1.5, 1, false) })
                            if (fundamentos.earningsPerShare != null)
                              items.push({ label: 'LPA', value: `R$ ${fmt(fundamentos.earningsPerShare, '', 2)}`, color: fundamentos.earningsPerShare > 0 ? '#00E676' : '#FF5252' })

                            if (items.length === 0)
                              return <p className="text-xs col-span-3 text-center" style={{ color: '#64748b' }}>Sem dados disponíveis</p>

                            return items.map((item, i) => (
                              <div key={i} className="text-center">
                                <p className="text-[10px] mb-1" style={{ color: '#64748b' }}>{item.label}</p>
                                <p className="font-mono text-sm font-bold" style={{ color: item.color }}>{item.value}</p>
                              </div>
                            ))
                          })()}
                        </div>
                      ) : (
                        <p className="text-xs text-center py-2" style={{ color: '#475569' }}>Dados fundamentalistas indisponíveis</p>
                      )}
                    </div>
                  )}

                  {/* APEX Score */}
                  {position.apex_score != null && (
                    <div className="rounded-xl px-4 py-3 flex items-center justify-between" style={{ background: '#111827', border: '1px solid #1e293b' }}>
                      <span className="text-xs" style={{ color: '#64748b' }}>APEX Score no momento da entrada</span>
                      <span className="font-mono font-bold" style={{ color: position.apex_score >= 70 ? '#00E676' : position.apex_score >= 40 ? '#FFCA28' : '#FF5252' }}>
                        {position.apex_score}/100
                      </span>
                    </div>
                  )}

                  {/* Justificativa de entrada */}
                  {position.justificativa_entrada && (
                    <div className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid rgba(0,230,118,0.15)' }}>
                      <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#00E676' }}>Por que está na carteira</p>
                      <p className="text-sm leading-relaxed" style={{ color: '#cbd5e1' }}>{position.justificativa_entrada}</p>
                    </div>
                  )}

                  {/* Tese */}
                  {(position.tese || editMode) && (
                    <div className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid rgba(167,139,250,0.2)' }}>
                      <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#a78bfa' }}>Tese de Investimento</p>
                      {editMode ? (
                        <textarea
                          value={editValues.tese}
                          onChange={e => setEditValues(v => ({ ...v, tese: e.target.value }))}
                          placeholder="Descreva sua tese de investimento..."
                          rows={3}
                          className="w-full text-sm leading-relaxed px-3 py-2 rounded-lg outline-none resize-none"
                          style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
                        />
                      ) : (
                        <p className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>{position.tese}</p>
                      )}
                    </div>
                  )}
                </motion.div>
              )}

              {/* ── Aba Transações ── */}
              {tab === 'transacoes' && (
                <motion.div
                  key="transacoes"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="p-5 space-y-4"
                >
                  {/* Resumo de estatísticas */}
                  {transacoes.length > 0 && (() => {
                    const compras = transacoes.filter(t => ['compra', 'dca', 'bonificacao', 'split', 'aporte'].includes(t.tipo))
                    const vendas = transacoes.filter(t => ['venda_parcial', 'venda_total'].includes(t.tipo))
                    const totalComprado = compras.reduce((s, t) => s + t.valor_total, 0)
                    const totalVendido = vendas.reduce((s, t) => s + t.valor_total, 0)
                    return (
                      <div className="grid grid-cols-3 gap-2">
                        <div className="rounded-lg px-3 py-2 text-center" style={{ background: 'rgba(0,230,118,0.05)', border: '1px solid rgba(0,230,118,0.1)' }}>
                          <p className="text-[9px] font-mono uppercase" style={{ color: '#64748b' }}>Compras</p>
                          <p className="text-xs font-mono font-bold mt-0.5" style={{ color: '#00E676' }}>{compras.length}x · R$ {formatMoney(totalComprado, 0)}</p>
                        </div>
                        <div className="rounded-lg px-3 py-2 text-center" style={{ background: 'rgba(255,82,82,0.05)', border: '1px solid rgba(255,82,82,0.1)' }}>
                          <p className="text-[9px] font-mono uppercase" style={{ color: '#64748b' }}>Vendas</p>
                          <p className="text-xs font-mono font-bold mt-0.5" style={{ color: '#FF9800' }}>{vendas.length}x · R$ {formatMoney(totalVendido, 0)}</p>
                        </div>
                        <div className="rounded-lg px-3 py-2 text-center" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid #1e293b' }}>
                          <p className="text-[9px] font-mono uppercase" style={{ color: '#64748b' }}>PM Atual</p>
                          <p className="text-xs font-mono font-bold mt-0.5" style={{ color: '#f1f5f9' }}>R$ {formatMoney(position.preco_medio)}</p>
                        </div>
                      </div>
                    )
                  })()}

                  {/* Botão adicionar */}
                  {!showForm && (
                    <button
                      onClick={() => setShowForm(true)}
                      className="w-full py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-2 transition-all"
                      style={{ background: 'rgba(0,230,118,0.06)', border: '1px dashed rgba(0,230,118,0.2)', color: '#00E676' }}
                      onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(0,230,118,0.5)')}
                      onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(0,230,118,0.2)')}
                    >
                      <Plus size={13} /> Registrar Transação
                    </button>
                  )}

                  {/* Form nova transação */}
                  {showForm && (
                    <NovaTransacaoForm
                      positionId={position.id}
                      onSaved={onTransacaoSaved}
                      onCancel={() => setShowForm(false)}
                    />
                  )}

                  {/* Lista de transações */}
                  {loadingTx ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#00E676 transparent transparent transparent' }} />
                    </div>
                  ) : transacoes.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 space-y-2">
                      <BarChart2 size={28} style={{ color: '#1e293b' }} />
                      <p className="text-sm" style={{ color: '#475569' }}>Nenhuma transação registrada</p>
                      <p className="text-xs text-center" style={{ color: '#334155' }}>
                        Registre compras, DCAs e vendas parciais para controle completo.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {/* Header */}
                      <div
                        className="grid text-[10px] font-mono uppercase tracking-wider px-3 py-1.5"
                        style={{ color: '#475569', gridTemplateColumns: '90px 1fr 70px 80px 80px 70px 32px' }}
                      >
                        <span>Data</span>
                        <span>Tipo</span>
                        <span className="text-right">Qtd</span>
                        <span className="text-right">Preço</span>
                        <span className="text-right">Total</span>
                        <span className="text-right">Taxas</span>
                        <span />
                      </div>
                      {transacoes.map(t => {
                        const cor = TIPO_TX_COLORS[t.tipo] || '#94a3b8'
                        return (
                          <div
                            key={t.id}
                            className="grid items-center px-3 py-2.5 rounded-lg text-xs"
                            style={{ background: 'rgba(255,255,255,0.015)', gridTemplateColumns: '90px 1fr 70px 80px 80px 70px 32px', border: '1px solid rgba(30,41,59,0.6)' }}
                          >
                            <span className="font-mono" style={{ color: '#64748b' }}>{formatDate(t.data)}</span>
                            <span className="flex items-center gap-1.5 font-medium" style={{ color: cor }}>
                              {TIPO_TX_ICONS[t.tipo]}
                              {TIPO_TX_LABELS[t.tipo] || t.tipo}
                              {t.observacao && (
                                <span className="text-[10px]" style={{ color: '#475569' }}>· {t.observacao}</span>
                              )}
                            </span>
                            <span className="text-right font-mono" style={{ color: '#f1f5f9' }}>{t.quantidade.toLocaleString('pt-BR')}</span>
                            <span className="text-right font-mono" style={{ color: '#f1f5f9' }}>R$ {formatMoney(t.preco)}</span>
                            <span className="text-right font-mono font-bold" style={{ color: cor }}>R$ {formatMoney(t.valor_total, 0)}</span>
                            <span className="text-right font-mono" style={{ color: '#475569' }}>
                              {t.taxas > 0 ? `R$ ${formatMoney(t.taxas, 2)}` : '—'}
                            </span>
                            <button
                              onClick={() => deletarTransacao(t.id)}
                              className="flex items-center justify-center w-6 h-6 rounded transition-all ml-auto"
                              style={{ color: '#FF5252', opacity: 0.3 }}
                              onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'rgba(255,82,82,0.1)' }}
                              onMouseLeave={e => { e.currentTarget.style.opacity = '0.3'; e.currentTarget.style.background = 'transparent' }}
                            >
                              <Trash2 size={11} />
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </motion.div>
              )}

              {/* ── Aba Análise AI ── */}
              {tab === 'ai' && (
                <motion.div
                  key="ai"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="p-5 flex flex-col items-center justify-center h-full min-h-[300px] space-y-4"
                >
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{ background: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.2)' }}
                  >
                    <BrainCircuit size={24} style={{ color: '#a78bfa' }} />
                  </div>
                  <div className="text-center">
                    <p className="font-medium" style={{ color: '#f1f5f9' }}>Análise com APEX Manager</p>
                    <p className="text-sm mt-1.5" style={{ color: '#64748b' }}>
                      O gestor vai analisar {position.ticker} em tempo real usando dados técnicos e de mercado.
                    </p>
                  </div>
                  <button
                    onClick={() => setShowAnalise(true)}
                    className="px-6 py-3 rounded-xl text-sm font-medium flex items-center gap-2 transition-all"
                    style={{ background: 'rgba(167,139,250,0.12)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.3)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(167,139,250,0.18)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'rgba(167,139,250,0.12)')}
                  >
                    <BrainCircuit size={15} /> Abrir Análise AI
                  </button>
                  <p className="text-xs text-center" style={{ color: '#334155' }}>
                    Analisa RSI, MACD, médias móveis, suporte/resistência e tese de investimento.
                  </p>
                </motion.div>
              )}

            </AnimatePresence>
          </div>
        </motion.div>
      </div>

      {/* AnaliseModal sobreposto (z-index maior) */}
      <AnimatePresence>
        {showAnalise && (
          <div style={{ position: 'fixed', inset: 0, zIndex: 60 }}>
            <AnaliseModal
              positionId={position.id}
              ticker={position.ticker}
              modulo={position.modulo}
              tese={position.tese}
              onClose={() => setShowAnalise(false)}
              onTeseSalva={t => {
                setShowAnalise(false)
                onUpdate?.()
              }}
            />
          </div>
        )}
      </AnimatePresence>
    </>
  )
}
