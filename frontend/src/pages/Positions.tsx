import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Plus, X, TrendingUp, TrendingDown, Circle, Trash2, ChevronDown, ChevronUp, BrainCircuit, LayoutList, FlaskConical, Download, FileText, RefreshCw } from 'lucide-react'
import PosicaoDetalheModal from '@/components/PosicaoDetalheModal'
import CarteiraPanel from '@/components/CarteiraPanel'
import RebalanceWizard from '@/components/RebalanceWizard'
import PortfolioEvolutionChart from '@/components/PortfolioEvolutionChart'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import { useCostEstimates } from '@/hooks/useCostEstimates'

interface Position {
  id: number
  ticker: string
  nome: string
  tipo: string
  modulo: string
  quantidade: number
  preco_medio: number
  preco_atual: number
  valor_investido: number
  valor_atual: number
  pl_reais: number
  pl_percentual: number
  stop_loss: number | null
  alvo_1: number | null
  alvo_2: number | null
  apex_score: number | null
  data_entrada: string | null
  data_abertura: string | null
  tese?: string | null
  mercado?: string
  moeda?: string
  analise_ia?: string | null
  analise_ia_at?: string | null
  dividendos_12m?: number
}

interface FormData {
  ticker: string
  nome: string
  tipo: string
  modulo: string
  quantidade: string
  preco_medio: string
  stop_loss: string
  data_entrada: string
  tese: string
  mercado: string
  moeda: string
}

const MODULE_LABELS: Record<string, string> = {
  etfs: 'ETFs',
  fiis: 'FIIs',
  momentum: 'Momentum',
  wheel: 'Wheel',
  renda_fixa: 'Renda Fixa',
  alpha: 'Alpha',
  dividendos: 'Dividendos',
  teses: 'Teses',
  caixa: 'Caixa',
}

const TIPO_COLORS: Record<string, string> = {
  ETF: '#00E676', FII: '#00BFA5', ACAO: '#1DE9B6',
  RF: '#FFD740', OPCAO: '#FF9800', BDR: '#64FFDA', DIVIDENDO: '#FFD740', CAIXA: '#475569', FUNDO: '#AB47BC',
}

const emptyForm: FormData = { ticker: '', nome: '', tipo: 'ACAO', modulo: 'momentum', quantidade: '', preco_medio: '', stop_loss: '', data_entrada: new Date().toISOString().slice(0, 10), tese: '', mercado: 'B3', moeda: 'BRL' }

function AddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FormData>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const handleSubmit = async () => {
    if (!form.ticker || !form.quantidade || !form.preco_medio) {
      setErr('Preencha Ticker, Quantidade e Preço Médio')
      return
    }
    setSaving(true)
    try {
      await api.post('/portfolio/posicoes', {
        ticker: form.ticker.toUpperCase(),
        nome: form.nome || undefined,
        tipo: form.tipo,
        modulo: form.modulo,
        quantidade: parseFloat(form.quantidade),
        preco_medio: parseFloat(form.preco_medio),
        stop_loss: form.stop_loss ? parseFloat(form.stop_loss) : undefined,
        data_entrada: form.data_entrada || undefined,
        ...(form.modulo === 'teses' ? {
          tese: form.tese || undefined,
          mercado: form.mercado,
          moeda: form.moeda,
        } : {}),
      })
      onSaved()
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Erro ao salvar posição')
    }
    setSaving(false)
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        className="apex-card p-6 w-full max-w-md"
        style={{ background: '#0f1729' }}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold" style={{ color: '#f1f5f9' }}>Adicionar Posição</h3>
          <button onClick={onClose} className="p-1 rounded transition-colors" style={{ color: '#64748b' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Ticker *</label>
              <input className="apex-input" placeholder="PETR4" value={form.ticker}
                onChange={e => setForm(f => ({ ...f, ticker: e.target.value.toUpperCase() }))} />
            </div>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Nome</label>
              <input className="apex-input" placeholder="Petrobras PN" value={form.nome}
                onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Tipo *</label>
              <select className="apex-input" value={form.tipo}
                onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}
                style={{ cursor: 'pointer' }}>
                {['ACAO', 'ETF', 'FII', 'BDR', 'RF', 'OPCAO', 'CAIXA'].map(t => (
                  <option key={t} value={t} style={{ background: '#0f1729' }}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Módulo *</label>
              <select className="apex-input" value={form.modulo}
                onChange={e => setForm(f => ({ ...f, modulo: e.target.value }))}
                style={{ cursor: 'pointer' }}>
                {Object.entries(MODULE_LABELS).map(([k, v]) => (
                  <option key={k} value={k} style={{ background: '#0f1729' }}>{v}</option>
                ))}
              </select>
            </div>
          </div>

          {form.modulo === 'teses' && (
            <>
              <div>
                <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Tese de Convicção *</label>
                <textarea className="apex-input" rows={3} placeholder="Descreva sua tese de convicção..."
                  value={form.tese} onChange={e => setForm(f => ({ ...f, tese: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Mercado</label>
                  <select className="apex-input" value={form.mercado}
                    onChange={e => setForm(f => ({ ...f, mercado: e.target.value }))} style={{ cursor: 'pointer' }}>
                    {['B3', 'BDR', 'NYSE', 'NASDAQ', 'AMEX'].map(m => (
                      <option key={m} value={m} style={{ background: '#0f1729' }}>{m}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Moeda</label>
                  <select className="apex-input" value={form.moeda}
                    onChange={e => setForm(f => ({ ...f, moeda: e.target.value }))} style={{ cursor: 'pointer' }}>
                    {['BRL', 'USD'].map(m => (
                      <option key={m} value={m} style={{ background: '#0f1729' }}>{m}</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          )}

          <div className={`grid gap-3 ${form.modulo === 'teses' ? 'grid-cols-2' : 'grid-cols-3'}`}>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qtd *</label>
              <input className="apex-input" placeholder="100" type="number" value={form.quantidade}
                onChange={e => setForm(f => ({ ...f, quantidade: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Preço Médio *</label>
              <input className="apex-input" placeholder="35.50" type="number" value={form.preco_medio}
                onChange={e => setForm(f => ({ ...f, preco_medio: e.target.value }))} />
            </div>
            {form.modulo !== 'teses' && (
              <div>
                <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Stop Loss</label>
                <input className="apex-input" placeholder="31.00" type="number" value={form.stop_loss}
                  onChange={e => setForm(f => ({ ...f, stop_loss: e.target.value }))} />
              </div>
            )}
          </div>

          <div>
            <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Data de Entrada</label>
            <input className="apex-input" type="date" value={form.data_entrada}
              onChange={e => setForm(f => ({ ...f, data_entrada: e.target.value }))}
              style={{ colorScheme: 'dark' }} />
          </div>
        </div>

        {err && <p className="text-xs mt-3" style={{ color: '#FF5252' }}>{err}</p>}

        <div className="flex gap-3 mt-5">
          <button onClick={onClose} className="btn-secondary flex-1">Cancelar</button>
          <button onClick={handleSubmit} disabled={saving} className="btn-primary flex-1">
            {saving ? 'Salvando...' : 'Adicionar'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}

function PLBadge({ value }: { value: number }) {
  const color = value > 0 ? '#00E676' : value < 0 ? '#FF5252' : '#94a3b8'
  const bg = value > 0 ? 'rgba(0,230,118,0.08)' : value < 0 ? 'rgba(255,82,82,0.08)' : 'rgba(148,163,184,0.08)'
  const a11y = value > 0 ? 'pl-badge-positive' : value < 0 ? 'pl-badge-negative' : ''
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-bold ${a11y}`} style={{ color, background: bg }}>
      {value > 0 ? <TrendingUp size={10} /> : value < 0 ? <TrendingDown size={10} /> : null}
      {value > 0 ? '+' : ''}{value.toFixed(2)}%
    </span>
  )
}

function StopBadge({ preco_atual, stop_loss }: { preco_atual: number; stop_loss: number | null }) {
  if (!stop_loss || preco_atual <= 0) return null
  const distPct = ((preco_atual - stop_loss) / stop_loss) * 100
  if (preco_atual <= stop_loss) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold animate-pulse"
        style={{ background: 'rgba(255,82,82,0.18)', color: '#FF5252' }}>
        STOP
      </span>
    )
  }
  if (distPct <= 5) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold"
        style={{ background: 'rgba(255,152,0,0.15)', color: '#FF9800' }}>
        -{distPct.toFixed(1)}%
      </span>
    )
  }
  return null
}

function ModuleGroup({ modulo, positions, onDelete, onDetalhe }: { modulo: string; positions: Position[]; onDelete: (id: number) => void; onDetalhe: (p: Position) => void }) {
  const [open, setOpen] = useState(true)
  const totalVal = positions.reduce((a, p) => a + p.valor_atual, 0)
  const totalPL = positions.reduce((a, p) => a + p.pl_reais, 0)
  const totalDiv12m = positions.reduce((a, p) => a + (p.dividendos_12m || 0), 0)
  const totalInv = positions.reduce((a, p) => a + p.valor_investido, 0)
  const totalRetGroup = totalPL + totalDiv12m
  const totalRetPct = totalInv > 0 ? (totalRetGroup / totalInv) * 100 : 0

  return (
    <div className="apex-card overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-4 transition-colors"
        onClick={() => setOpen(!open)}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.01)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <div className="flex items-center gap-3">
          <Circle size={8} fill="#00E676" style={{ color: '#00E676' }} />
          <span className="font-medium text-sm" style={{ color: '#f1f5f9' }}>{MODULE_LABELS[modulo] || modulo}</span>
          <span className="text-xs px-2 py-0.5 rounded-full font-mono" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>
            {positions.length}
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm font-mono">
          <span style={{ color: '#f1f5f9' }}>
            R$ {totalVal.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
          <span style={{ color: totalPL >= 0 ? '#00E676' : '#FF5252' }}>
            R$ {totalPL.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: totalRetGroup >= 0 ? '#00E676' : '#FF5252', background: totalRetGroup >= 0 ? 'rgba(0,230,118,0.08)' : 'rgba(255,82,82,0.08)' }}>
            {totalRetPct >= 0 ? '+' : ''}{totalRetPct.toFixed(1)}%
          </span>
          {open ? <ChevronUp size={14} style={{ color: '#64748b' }} /> : <ChevronDown size={14} style={{ color: '#64748b' }} />}
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ borderTop: '1px solid #1e293b' }}>
              <div className="grid px-4 py-2 text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b', gridTemplateColumns: '1fr 60px 82px 82px 94px 100px 100px 100px 55px' }}>
                <span>Ativo</span>
                <span className="text-right">Qtd</span>
                <span className="text-right">PM</span>
                <span className="text-right">Atual</span>
                <span className="text-right">Valor</span>
                <span className="text-right">P&amp;L</span>
                <span className="text-right">Ret. Total</span>
                <span className="text-right">Stop</span>
                <span />
              </div>

              {positions.map(p => (
                <div
                  key={p.id}
                  className="grid items-center px-4 py-3 text-sm transition-colors"
                  style={{ gridTemplateColumns: '1fr 60px 82px 82px 94px 100px 100px 100px 55px', borderTop: '1px solid rgba(30,41,59,0.5)' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.01)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-1.5 py-0.5 rounded font-mono font-bold"
                      style={{ color: TIPO_COLORS[p.tipo] || '#94a3b8', background: `${TIPO_COLORS[p.tipo] || '#94a3b8'}15` }}>
                      {p.tipo}
                    </span>
                    <div>
                      <span className="font-mono font-bold" style={{ color: '#f1f5f9' }}>{p.ticker}</span>
                      {p.nome && p.nome !== p.ticker && (
                        <span className="ml-2 text-xs" style={{ color: '#64748b' }}>{p.nome}</span>
                      )}
                    </div>
                  </div>
                  <span className="text-right font-mono" style={{ color: '#94a3b8' }}>{p.quantidade}</span>
                  <span className="text-right font-mono" style={{ color: '#94a3b8' }}>R$ {p.preco_medio.toFixed(2)}</span>
                  <span className="text-right font-mono font-bold" style={{ color: '#f1f5f9' }}>R$ {p.preco_atual.toFixed(2)}</span>
                  <span className="text-right font-mono text-xs" style={{ color: '#f1f5f9' }}>
                    R$ {p.valor_atual.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </span>
                  <div className="flex justify-end">
                    <PLBadge value={p.pl_percentual} />
                  </div>
                  <div className="flex justify-end">
                    {(() => {
                      const dyPct = (p.dividendos_12m && p.valor_investido > 0) ? (p.dividendos_12m / p.valor_investido * 100) : 0
                      const retTotal = p.pl_percentual + dyPct
                      return <PLBadge value={retTotal} />
                    })()}
                  </div>
                  <div className="flex items-center justify-end gap-1">
                    <StopBadge preco_atual={p.preco_atual} stop_loss={p.stop_loss} />
                    <span className="font-mono text-xs" style={{ color: p.stop_loss ? '#FF5252' : '#475569' }}>
                      {p.stop_loss ? `R$ ${p.stop_loss.toFixed(2)}` : '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => onDetalhe(p)}
                      title="Ver detalhes e analisar posição"
                      className="flex items-center justify-center w-7 h-7 rounded transition-all"
                      style={{ color: '#a78bfa', opacity: 0.5 }}
                      onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'rgba(139,92,246,0.12)' }}
                      onMouseLeave={e => { e.currentTarget.style.opacity = '0.5'; e.currentTarget.style.background = 'transparent' }}
                    >
                      <BrainCircuit size={13} />
                    </button>
                    <button
                      onClick={() => onDelete(p.id)}
                      title="Encerrar posição"
                      className="flex items-center justify-center w-7 h-7 rounded transition-all"
                      style={{ color: '#FF5252', opacity: 0.35 }}
                      onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'rgba(255,82,82,0.1)' }}
                      onMouseLeave={e => { e.currentTarget.style.opacity = '0.35'; e.currentTarget.style.background = 'transparent' }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function PositionsPage() {
  const navigate = useNavigate()
  const { portfolioAtivo } = useStore()
  const { format: fmtCost } = useCostEstimates()
  const isSimulada = portfolioAtivo?.tipo === 'simulada'
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showCarteira, setShowCarteira] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [analisando, setAnalisando] = useState<Position | null>(null)

  const loadPositions = async () => {
    setLoading(true)
    try {
      const res = await api.get('/portfolio/posicoes')
      // Backend retorna { posicoes, capital_declarado, caixa_disponivel }
      const data = res.data
      const lista = Array.isArray(data) ? data : (data.posicoes || [])
      setPositions(lista)
      // Atualiza posição aberta no modal de detalhe (ex: após nova análise IA)
      setAnalisando(prev => prev ? lista.find((p: Position) => p.id === prev.id) ?? null : null)
    } catch { /* silent */ }
    setLoading(false)
  }

  const refreshPrices = async () => {
    setRefreshing(true)
    try {
      await api.post('/portfolio/refresh-prices')
      await loadPositions()  // recarrega com os preços atualizados do banco
    } catch { /* silent */ }
    setRefreshing(false)
  }

  const deletePosition = async (id: number) => {
    const pos = positions.find(x => x.id === id)
    const plInfo = pos
      ? `\n\nPM: R$ ${pos.preco_medio.toFixed(2)} | Atual: R$ ${pos.preco_atual.toFixed(2)}\nP&L: ${pos.pl_reais >= 0 ? '+' : ''}R$ ${pos.pl_reais.toFixed(2)} (${pos.pl_percentual >= 0 ? '+' : ''}${pos.pl_percentual.toFixed(2)}%)`
      : ''
    if (!confirm(`Encerrar posição ${pos?.ticker || ''}?${plInfo}`)) return
    try {
      await api.delete(`/portfolio/posicoes/${id}`)
      setPositions(p => p.filter(x => x.id !== id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erro ao encerrar posição')
    }
  }

  useEffect(() => { loadPositions() }, [])

  // Recarrega posições quando o usuário troca de carteira (sem reload completo da página)
  useEffect(() => {
    const handler = () => loadPositions()
    window.addEventListener('portfolio-changed', handler)
    return () => window.removeEventListener('portfolio-changed', handler)
  }, [])

  const grouped = positions.reduce<Record<string, Position[]>>((acc, p) => {
    const key = p.modulo || 'outros'
    if (!acc[key]) acc[key] = []
    acc[key].push(p)
    return acc
  }, {})

  const totalInvested = positions.reduce((a, p) => a + p.valor_investido, 0)
  const totalCurrent = positions.reduce((a, p) => a + p.valor_atual, 0)
  const totalPL = totalCurrent - totalInvested
  const totalPLPct = totalInvested > 0 ? (totalPL / totalInvested) * 100 : 0
  const totalDividendos = positions.reduce((a, p) => a + (p.dividendos_12m || 0), 0)
  const totalReturn = totalPL + totalDividendos
  const totalReturnPct = totalInvested > 0 ? (totalReturn / totalInvested) * 100 : 0

  const downloadCSV = () => {
    const header = 'Módulo,Ticker,Nome,Tipo,Qtd,Preço Médio,Preço Atual,Valor Investido,Valor Atual,P&L (R$),P&L (%),Data Entrada'
    const rows = positions.map(p => [
      p.modulo, p.ticker, `"${(p.nome || '').replace(/"/g, '""')}"`, p.tipo,
      p.quantidade, p.preco_medio.toFixed(2), p.preco_atual.toFixed(2),
      p.valor_investido.toFixed(2), p.valor_atual.toFixed(2),
      p.pl_reais.toFixed(2), p.pl_percentual.toFixed(2),
      p.data_entrada || '',
    ].join(','))
    const csv = [header, ...rows].join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `posicoes_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadHTML = () => {
    const date = new Date().toLocaleDateString('pt-BR')
    const portfolioName = portfolioAtivo?.nome || 'Portfólio'
    const fmt = (v: number) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

    const moduleOrder = ['momentum', 'dividendos', 'fiis', 'etfs', 'renda_fixa', 'alpha', 'teses', 'wheel', 'caixa', 'outros']
    const grouped = positions.reduce<Record<string, Position[]>>((acc, p) => {
      const key = p.modulo || 'outros'
      ;(acc[key] = acc[key] || []).push(p)
      return acc
    }, {})

    let tableRows = ''
    for (const mod of moduleOrder) {
      const items = grouped[mod]
      if (!items?.length) continue
      const modLabel = MODULE_LABELS[mod] || mod
      const modTotal = items.reduce((a, p) => a + p.valor_atual, 0)
      const modPL = items.reduce((a, p) => a + p.pl_reais, 0)
      tableRows += `<tr class="module-row"><td colspan="10">${modLabel} <span class="dim">(${items.length} ativos — R$ ${fmt(modTotal)})</span></td></tr>\n`
      for (const p of items) {
        const plClass = p.pl_reais > 0 ? 'green' : p.pl_reais < 0 ? 'red' : ''
        tableRows += `<tr>
          <td class="ticker">${p.ticker}</td>
          <td>${p.nome || ''}</td>
          <td class="tipo">${p.tipo}</td>
          <td class="num">${p.quantidade}</td>
          <td class="num">R$ ${fmt(p.preco_medio)}</td>
          <td class="num">R$ ${fmt(p.preco_atual)}</td>
          <td class="num">R$ ${fmt(p.valor_investido)}</td>
          <td class="num">R$ ${fmt(p.valor_atual)}</td>
          <td class="num ${plClass}">R$ ${fmt(p.pl_reais)}</td>
          <td class="num ${plClass}">${fmtPct(p.pl_percentual)}</td>
        </tr>\n`
      }
    }

    const plColor = totalPL >= 0 ? '#00E676' : '#FF5252'

    const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>APEX — ${portfolioName} — ${date}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0f1a; color: #e2e8f0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 40px; }
  .header { margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #1e293b; padding-bottom: 20px; }
  .header h1 { font-size: 22px; color: #f1f5f9; letter-spacing: -0.5px; }
  .header .accent { color: #00E676; }
  .header .sub { color: #64748b; font-size: 12px; margin-top: 4px; }
  .header .date { color: #475569; font-size: 11px; font-family: monospace; }
  .summary { display: flex; gap: 16px; margin-bottom: 28px; }
  .summary .card { background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 16px 20px; flex: 1; }
  .summary .card .label { color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-family: monospace; }
  .summary .card .value { color: #f1f5f9; font-size: 18px; font-weight: 700; margin-top: 4px; font-family: monospace; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-family: monospace; padding: 10px 12px; border-bottom: 1px solid #1e293b; }
  td { padding: 8px 12px; border-bottom: 1px solid rgba(30,41,59,0.5); }
  tr:hover { background: rgba(255,255,255,0.02); }
  .module-row { background: rgba(0,230,118,0.04); }
  .module-row td { color: #00E676; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 12px; border-bottom: 1px solid rgba(0,230,118,0.1); }
  .dim { color: #475569; font-weight: 400; font-size: 11px; }
  .ticker { color: #f1f5f9; font-weight: 600; font-family: monospace; }
  .tipo { color: #94a3b8; font-size: 10px; font-family: monospace; text-transform: uppercase; }
  .num { text-align: right; font-family: monospace; color: #cbd5e1; }
  .green { color: #00E676; }
  .red { color: #FF5252; }
  .footer { margin-top: 28px; text-align: center; color: #334155; font-size: 10px; font-family: monospace; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1><span class="accent">APEX</span> — ${portfolioName}</h1>
      <div class="sub">${positions.length} posições ativas</div>
    </div>
    <div class="date">${date}</div>
  </div>
  <div class="summary">
    <div class="card"><div class="label">Custo Total</div><div class="value">R$ ${fmt(totalInvested)}</div></div>
    <div class="card"><div class="label">Valor Atual</div><div class="value">R$ ${fmt(totalCurrent)}</div></div>
    <div class="card"><div class="label">P&amp;L Total</div><div class="value" style="color:${plColor}">${totalPL >= 0 ? '+' : ''}R$ ${fmt(totalPL)} (${fmtPct(totalPLPct)})</div></div>
  </div>
  <table>
    <thead>
      <tr><th>Ticker</th><th>Nome</th><th>Tipo</th><th>Qtd</th><th>PM</th><th>Atual</th><th>Investido</th><th>Valor</th><th>P&amp;L</th><th>P&amp;L %</th></tr>
    </thead>
    <tbody>
      ${tableRows}
    </tbody>
  </table>
  <div class="footer">Gerado por APEX Manager</div>
</body>
</html>`

    const blob = new Blob([html], { type: 'text/html;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `posicoes_${new Date().toISOString().slice(0, 10)}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-8 space-y-6">
      {/* Side panel análise de carteira */}
      {showCarteira && <CarteiraPanel onClose={() => setShowCarteira(false)} />}

      {/* Detalhe da posição modal */}
      {analisando && (
        <PosicaoDetalheModal
          position={analisando}
          onClose={() => setAnalisando(null)}
          onUpdate={() => loadPositions()}
        />
      )}

      {/* Banner: carteira simulada */}
      {portfolioAtivo?.tipo === 'simulada' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm"
          style={{ background: 'rgba(255,152,0,0.08)', border: '1px solid rgba(255,152,0,0.25)' }}
        >
          <FlaskConical size={16} style={{ color: '#FF9800', flexShrink: 0 }} />
          <span style={{ color: '#FF9800' }} className="font-medium">Carteira Simulada</span>
          <span style={{ color: '#94a3b8' }} className="text-xs">
            {'— Você está visualizando a carteira simulada. As posições não são executadas na corretora.'}
          </span>
        </motion.div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Posições</h1>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            {positions.length} ativo{positions.length !== 1 ? 's' : ''} no portfólio
            {refreshing && <span className="ml-2" style={{ color: '#00E676' }}>• atualizando preços...</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
              onClick={() => refreshPrices()}
              disabled={refreshing}
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all"
              style={{ background: refreshing ? 'rgba(0,230,118,0.08)' : 'rgba(255,255,255,0.03)', color: refreshing ? '#00E676' : '#64748b', border: `1px solid ${refreshing ? 'rgba(0,230,118,0.25)' : '#1e293b'}` }}
              onMouseEnter={e => { if (!refreshing) { e.currentTarget.style.color = '#00E676'; e.currentTarget.style.borderColor = 'rgba(0,230,118,0.25)' } }}
              onMouseLeave={e => { if (!refreshing) { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#1e293b' } }}
              title="Atualizar preços ao vivo"
            >
              <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
              {refreshing ? 'Atualizando...' : 'Atualizar Preços'}
            </button>
          {positions.length > 0 && (
            <>
            <button
              onClick={downloadHTML}
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all"
              style={{ background: 'rgba(255,255,255,0.03)', color: '#64748b', border: '1px solid #1e293b' }}
              onMouseEnter={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = '#334155' }}
              onMouseLeave={e => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#1e293b' }}
              title="Exportar posições como HTML"
            >
              <FileText size={15} />
              HTML
            </button>
            <button
              onClick={downloadCSV}
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all"
              style={{ background: 'rgba(255,255,255,0.03)', color: '#64748b', border: '1px solid #1e293b' }}
              onMouseEnter={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = '#334155' }}
              onMouseLeave={e => { e.currentTarget.style.color = '#64748b'; e.currentTarget.style.borderColor = '#1e293b' }}
              title="Exportar posições como CSV"
            >
              <Download size={15} />
              CSV
            </button>
            </>
          )}
          <button
            onClick={() => setShowCarteira(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
          >
            <LayoutList size={16} />
            Analisar Carteira
            {fmtCost('analise_carteira') && <span style={{ fontSize: 10, opacity: 0.6 }}>{fmtCost('analise_carteira')}</span>}
          </button>
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'rgba(255,152,0,0.1)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.25)' }}
          >
            <BrainCircuit size={16} />
            Rebalancear
            {fmtCost('sugerir_portfolio') && <span style={{ fontSize: 10, opacity: 0.6 }}>{fmtCost('sugerir_portfolio')}</span>}
          </button>
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} />
            Nova Posição
          </button>
        </div>
      </div>

      {positions.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          {[
            { label: 'Custo Total', value: `R$ ${totalInvested.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, color: '#94a3b8' },
            { label: 'Valor Atual', value: `R$ ${totalCurrent.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, color: '#f1f5f9' },
            { label: 'P&L Total', value: `${totalPL >= 0 ? '+' : ''}R$ ${totalPL.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} (${totalPLPct >= 0 ? '+' : ''}${totalPLPct.toFixed(2)}%)`, color: totalPL >= 0 ? '#00E676' : '#FF5252' },
            { label: 'Retorno c/ Dividendos', value: `${totalReturn >= 0 ? '+' : ''}R$ ${totalReturn.toLocaleString('pt-BR', { minimumFractionDigits: 2 })} (${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%)`, color: totalReturn >= 0 ? '#00E676' : '#FF5252' },
          ].map(s => (
            <div key={s.label} className="apex-card p-4">
              <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>{s.label}</p>
              <p className="text-lg font-bold font-mono mt-1" style={{ color: s.color }}>{s.value}</p>
            </div>
          ))}

        </motion.div>
      )}

      <PortfolioEvolutionChart />

      {(loading || refreshing) && positions.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="apex-card p-10 text-center"
        >
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 border-3 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#00E676', borderWidth: '3px' }} />
            <div>
              <p className="text-sm font-medium" style={{ color: '#f1f5f9' }}>
                {refreshing ? 'Atualizando cotações ao vivo...' : 'Carregando posições...'}
              </p>
              <p className="text-xs mt-1" style={{ color: '#64748b' }}>
                {refreshing ? 'Buscando preços atualizados para todas as posições' : 'Aguarde um momento'}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {!loading && !refreshing && positions.length === 0 && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-12 text-center">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'rgba(0,230,118,0.08)', border: '1px solid rgba(0,230,118,0.15)' }}>
            <TrendingUp size={22} style={{ color: '#00E676' }} />
          </div>
          <h3 className="font-semibold mb-2" style={{ color: '#f1f5f9' }}>Nenhuma posição cadastrada</h3>
          <p className="text-sm mb-6" style={{ color: '#64748b' }}>
            {isSimulada
              ? 'Deixe o APEX Manager alocar o capital automaticamente, ou adicione posições manualmente.'
              : 'Adicione suas posições para que o gestor APEX possa monitorar e analisar seu portfólio.'}
          </p>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => navigate('/sugestoes-alocacao', { state: { portfolioId: portfolioAtivo?.id, modo: 'inicial' } })}
              className="btn-primary inline-flex items-center gap-2"
              style={{
                background: isSimulada ? 'rgba(255,152,0,0.15)' : 'rgba(0,191,165,0.12)',
                borderColor: isSimulada ? 'rgba(255,152,0,0.4)' : 'rgba(0,191,165,0.35)',
                color: isSimulada ? '#FF9800' : '#00BFA5',
              }}
            >
              <BrainCircuit size={15} />
              {isSimulada ? 'Alocar via IA' : 'Deixar IA sugerir alocação'}
            </button>
            <button onClick={() => setShowAdd(true)} className="btn-primary inline-flex items-center gap-2">
              <Plus size={15} /> {isSimulada ? 'Adicionar Manualmente' : 'Adicionar Primeira Posição'}
            </button>
          </div>
        </motion.div>
      )}

      {!loading && Object.entries(grouped).map(([modulo, pos]) => (
        <motion.div key={modulo} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <ModuleGroup modulo={modulo} positions={pos} onDelete={deletePosition} onDetalhe={(p) => setAnalisando(p)} />
        </motion.div>
      ))}

      <AnimatePresence>
        {showAdd && (
          <AddModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); loadPositions() }} />
        )}
      </AnimatePresence>

      {showWizard && portfolioAtivo && (
        <RebalanceWizard
          onClose={() => setShowWizard(false)}
          positions={positions.map(p => ({ modulo: p.modulo, valor_atual: p.valor_atual }))}
          portfolioId={portfolioAtivo.id}
        />
      )}
    </div>
  )
}

