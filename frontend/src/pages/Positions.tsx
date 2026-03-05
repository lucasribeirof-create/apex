import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Plus, X, TrendingUp, TrendingDown, Circle, Trash2, ChevronDown, ChevronUp, BrainCircuit, LayoutList, FlaskConical, Pencil, Check, Wallet } from 'lucide-react'
import PosicaoDetalheModal from '@/components/PosicaoDetalheModal'
import EncerrarPosicaoModal from '@/components/EncerrarPosicaoModal'
import CarteiraPanel from '@/components/CarteiraPanel'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

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
  apex_score: number | null
  data_entrada: string | null
  tese?: string | null
}

interface FormData {
  ticker: string
  nome: string
  tipo: string
  modulo: string
  quantidade: string
  preco_medio: string
  stop_loss: string
  justificativa: string
}

const MODULE_LABELS: Record<string, string> = {
  etfs: 'ETFs',
  fiis: 'FIIs',
  momentum: 'Momentum · Trade Técnico',
  wheel: 'Wheel · Opções',
  renda_fixa: 'Renda Fixa',
  alpha: 'Alpha · Valor com Stop',
  dividendos: 'Dividendos',
  teses: 'Teses · Convicção DCA',
  caixa: 'Caixa',
}

const TIPO_COLORS: Record<string, string> = {
  ETF: '#00E676', FII: '#00BFA5', ACAO: '#1DE9B6',
  RF: '#FFD740', OPCAO: '#FF9800', BDR: '#64FFDA', DIVIDENDO: '#FFD740', CAIXA: '#475569',
}

const emptyForm: FormData = { ticker: '', nome: '', tipo: 'ACAO', modulo: 'momentum', quantidade: '', preco_medio: '', stop_loss: '', justificativa: '' }

function AddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FormData>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [searchTimer, setSearchTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  const searchTicker = (query: string) => {
    if (searchTimer) clearTimeout(searchTimer)
    if (query.length < 2) { setSuggestions([]); setShowSuggestions(false); return }
    const t = setTimeout(async () => {
      try {
        const res = await api.get('/market/search', { params: { q: query } })
        const items = (res.data || []).map((s: any) => typeof s === 'string' ? s : s.stock || s.ticker || '')
          .filter(Boolean).slice(0, 8)
        setSuggestions(items)
        setShowSuggestions(items.length > 0)
      } catch { setSuggestions([]); setShowSuggestions(false) }
    }, 350)
    setSearchTimer(t)
  }

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
        justificativa_entrada: form.justificativa || undefined,
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
              <div className="relative">
                <input className="apex-input" placeholder="PETR4" value={form.ticker}
                  onChange={e => { const v = e.target.value.toUpperCase(); setForm(f => ({ ...f, ticker: v })); searchTicker(v) }}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                  autoComplete="off" />
                {showSuggestions && (
                  <div className="absolute z-50 w-full mt-1 rounded-xl overflow-hidden border"
                    style={{ background: '#0f172a', borderColor: '#1e293b', maxHeight: 200, overflowY: 'auto' as const }}>
                    {suggestions.map(s => (
                      <button key={s} type="button"
                        className="w-full text-left px-3 py-2 text-sm hover:bg-white/5 transition-colors"
                        style={{ color: '#f1f5f9' }}
                        onMouseDown={() => { setForm(f => ({ ...f, ticker: s })); setShowSuggestions(false) }}>
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
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

          <div className="grid grid-cols-3 gap-3">
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
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Stop Loss</label>
              <input className="apex-input" placeholder="31.00" type="number" value={form.stop_loss}
                onChange={e => setForm(f => ({ ...f, stop_loss: e.target.value }))} />
            </div>
          </div>

          <div>
            <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Por que está na carteira?</label>
            <input className="apex-input" placeholder="Ex: ETF diversificado para exposição ao IBOV" value={form.justificativa}
              onChange={e => setForm(f => ({ ...f, justificativa: e.target.value }))} />
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
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-bold" style={{ color, background: bg }}>
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

function ModuleGroup({ modulo, positions, onDelete, onDetalhe, portfolioTotal, onEditCaixa, onDeleteCaixa }: { modulo: string; positions: Position[]; onDelete: (id: number) => void; onDetalhe: (p: Position) => void; portfolioTotal: number; onEditCaixa?: (p: Position) => void; onDeleteCaixa?: (p: Position) => void }) {
  const [open, setOpen] = useState(true)
  const totalVal = positions.reduce((a, p) => a + p.valor_atual, 0)
  const totalPL = positions.reduce((a, p) => a + p.pl_reais, 0)
  const pctPortfolio = portfolioTotal > 0 ? (totalVal / portfolioTotal) * 100 : 0

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
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(148,163,184,0.08)', color: '#94a3b8' }}>
            {pctPortfolio.toFixed(1)}%
          </span>
          <span style={{ color: '#f1f5f9' }}>
            R$ {totalVal.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
          <span style={{ color: totalPL >= 0 ? '#00E676' : '#FF5252' }}>
            {totalPL >= 0 ? '+' : ''}R$ {totalPL.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
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
              <div className="grid px-4 py-2 text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b', gridTemplateColumns: '1fr 70px 90px 90px 90px 90px 80px 72px' }}>
                <span>Ativo</span>
                <span className="text-right">Qtd</span>
                <span className="text-right">PM</span>
                <span className="text-right">Atual</span>
                <span className="text-right">Valor</span>
                <span className="text-right">P&amp;L</span>
                <span className="text-right">Stop</span>
                <span />
              </div>

              {positions.map(p => (
                <div
                  key={p.id}
                  className="grid items-center px-4 py-3 text-sm transition-colors"
                  style={{ gridTemplateColumns: '1fr 70px 90px 90px 90px 90px 80px 72px', borderTop: '1px solid rgba(30,41,59,0.5)' }}
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
                  <div className="flex items-center justify-end gap-1">
                    <StopBadge preco_atual={p.preco_atual} stop_loss={p.stop_loss} />
                    <span className="font-mono text-xs" style={{ color: p.stop_loss ? '#FF5252' : '#475569' }}>
                      {p.stop_loss ? `R$ ${p.stop_loss.toFixed(2)}` : '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-end gap-1">
                    {p.ticker === 'CAIXA' ? (
                      <>
                        <button
                          onClick={() => onEditCaixa?.(p)}
                          title="Editar saldo do caixa"
                          className="flex items-center justify-center w-7 h-7 rounded transition-all"
                          style={{ color: '#FFD740', opacity: 0.5 }}
                          onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'rgba(255,215,64,0.12)' }}
                          onMouseLeave={e => { e.currentTarget.style.opacity = '0.5'; e.currentTarget.style.background = 'transparent' }}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => onDeleteCaixa?.(p)}
                          title="Remover caixa"
                          className="flex items-center justify-center w-7 h-7 rounded transition-all"
                          style={{ color: '#FF5252', opacity: 0.35 }}
                          onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.background = 'rgba(255,82,82,0.1)' }}
                          onMouseLeave={e => { e.currentTarget.style.opacity = '0.35'; e.currentTarget.style.background = 'transparent' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    ) : (
                      <>
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
                      </>
                    )}
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
  const isSimulada = portfolioAtivo?.tipo === 'simulada'
  const [positions, setPositions] = useState<Position[]>([])
  const [capitalDeclarado, setCapitalDeclarado] = useState<number | null>(null)
  const [editandoCapital, setEditandoCapital] = useState(false)
  const [capitalInput, setCapitalInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showCarteira, setShowCarteira] = useState(false)
  const [analisando, setAnalisando] = useState<Position | null>(null)
  const [encerrando, setEncerrando] = useState<Position | null>(null)
  const [editandoCaixa, setEditandoCaixa] = useState<Position | null>(null)
  const [caixaInput, setCaixaInput] = useState('')

  const loadPositions = async () => {
    setLoading(true)
    try {
      const res = await api.get('/portfolio/posicoes')
      // Backend retorna { posicoes, capital_declarado, caixa_disponivel }
      const data = res.data
      if (Array.isArray(data)) {
        setPositions(data) // fallback para resposta antiga
      } else {
        setPositions(data.posicoes || [])
        setCapitalDeclarado(data.capital_declarado ?? null)
      }
    } catch { /* silent */ }
    setLoading(false)
  }

  const formatCapitalInput = (raw: string) => {
    // Strip everything except digits and comma
    const digits = raw.replace(/[^\d]/g, '')
    if (!digits) return ''
    const num = parseInt(digits, 10)
    // Format as pt-BR integer (dots as thousand separators, no decimals while typing)
    return num.toLocaleString('pt-BR')
  }

  const parseCapitalInput = (formatted: string) =>
    parseFloat(formatted.replace(/\./g, '').replace(',', '.'))

  const salvarCapital = async () => {
    const val = parseCapitalInput(capitalInput)
    if (isNaN(val) || val <= 0) return
    try {
      await api.patch('/portfolio/capital', { capital_declarado: val })
      setCapitalDeclarado(val)
    } catch { /* silent */ }
    setEditandoCapital(false)
  }

  const refreshPrices = async () => {
    setRefreshing(true)
    try {
      await api.post('/portfolio/refresh-prices')
      await loadPositions()  // recarrega com os preços atualizados do banco
    } catch { /* silent */ }
    setRefreshing(false)
  }

  const deletePosition = (id: number) => {
    const pos = positions.find(p => p.id === id)
    if (pos) setEncerrando(pos)
  }

  const onEncerrarSuccess = (result: { venda_total: boolean; ticker: string }) => {
    setEncerrando(null)
    if (result.venda_total) {
      setPositions(p => p.filter(x => x.ticker !== result.ticker))
    }
    loadPositions() // recarrega para pegar CAIXA atualizado
  }

  const editarCaixa = (p: Position) => {
    setCaixaInput(p.quantidade.toLocaleString('pt-BR', { minimumFractionDigits: 2 }))
    setEditandoCaixa(p)
  }

  const salvarCaixa = async () => {
    const val = parseFloat(caixaInput.replace(/\./g, '').replace(',', '.'))
    if (isNaN(val) || val < 0) return
    try {
      await api.patch('/portfolio/caixa', { quantidade: val })
      setEditandoCaixa(null)
      loadPositions()
    } catch { /* silent */ }
  }

  const excluirCaixa = async (p: Position) => {
    if (!confirm(`Remover CAIXA (R$ ${p.quantidade.toLocaleString('pt-BR', { minimumFractionDigits: 2 })})?`)) return
    try {
      await api.delete('/portfolio/caixa')
      loadPositions()
    } catch { /* silent */ }
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
  const caixaDisponivel = capitalDeclarado !== null ? capitalDeclarado - totalCurrent : null
  const caixaPct = capitalDeclarado && capitalDeclarado > 0 ? (caixaDisponivel! / capitalDeclarado) * 100 : null

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
            onClick={() => setShowCarteira(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
          >
            <LayoutList size={16} />
            Analisar Carteira
          </button>
          <button
            onClick={async () => {
              try {
                const r = await api.get('/onboarding/perfil-status')
                if (!r.data.perfil_completo) {
                  navigate('/perfil-investidor', { state: { returnTo: 'rebalanceamento' } })
                  return
                }
              } catch { /* ignora erro e tenta rebalancear */ }
              navigate('/sugestoes-alocacao', { state: { portfolioId: portfolioAtivo?.id, modo: 'rebalanceamento', forceRefresh: true } })
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: 'rgba(255,152,0,0.1)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.25)' }}
          >
            <BrainCircuit size={16} />
            Rebalancear
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
          ].map(s => (
            <div key={s.label} className="apex-card p-4">
              <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>{s.label}</p>
              <p className="text-lg font-bold font-mono mt-1" style={{ color: s.color }}>{s.value}</p>
            </div>
          ))}
          {/* Card de caixa disponível — clicável para declarar/editar capital */}
          <div className="apex-card p-4" style={{ border: caixaDisponivel !== null && caixaDisponivel < 0 ? '1px solid rgba(255,82,82,0.35)' : '1px solid rgba(0,230,118,0.15)' }}>
            <div className="flex items-center justify-between">
              <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Caixa Disponível</p>
              {!editandoCapital && (
                <button onClick={() => { setCapitalInput(capitalDeclarado !== null ? capitalDeclarado.toLocaleString('pt-BR') : ''); setEditandoCapital(true) }} title="Definir capital total">
                  <Pencil size={11} style={{ color: '#475569' }} />
                </button>
              )}
            </div>
            {editandoCapital ? (
              <div className="flex items-center gap-1 mt-2">
                <span className="text-xs font-mono" style={{ color: '#64748b' }}>R$</span>
                <input
                  autoFocus
                  type="text"
                  value={capitalInput}
                  onChange={e => setCapitalInput(formatCapitalInput(e.target.value))}
                  onKeyDown={e => { if (e.key === 'Enter') salvarCapital(); if (e.key === 'Escape') setEditandoCapital(false) }}
                  placeholder="1.000.000"
                  className="bg-transparent border-b text-sm font-mono outline-none flex-1 min-w-0"
                  style={{ borderColor: '#00E676', color: '#f1f5f9' }}
                />
                <button onClick={salvarCapital} style={{ color: '#00E676' }}><Check size={13} /></button>
                <button onClick={() => setEditandoCapital(false)} style={{ color: '#64748b' }}><X size={13} /></button>
              </div>
            ) : capitalDeclarado !== null ? (
              <>
                <p className="text-lg font-bold font-mono mt-1" style={{ color: caixaDisponivel !== null && caixaDisponivel < 0 ? '#FF5252' : '#00E676' }}>
                  R$ {caixaDisponivel !== null ? caixaDisponivel.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                  {caixaPct !== null && <span className="text-xs font-normal ml-1" style={{ color: '#64748b' }}>{caixaPct.toFixed(1)}%</span>}
                </p>
                <p className="text-xs font-mono mt-0.5" style={{ color: '#475569' }}>
                  de R$ {capitalDeclarado.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </p>
              </>
            ) : (
              <p className="text-xs mt-2 cursor-pointer" style={{ color: '#475569' }} onClick={() => { setCapitalInput(''); setEditandoCapital(true) }}>
                Clique no lápis para declarar o capital total
              </p>
            )}
          </div>
        </motion.div>
      )}

      {loading && (
        <div className="flex items-center gap-3" style={{ color: '#64748b' }}>
          <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#00E676' }} />
          <span className="text-sm">Carregando posições...</span>
        </div>
      )}

      {!loading && positions.length === 0 && (
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
              onClick={async () => {
                try {
                  const r = await api.get('/onboarding/perfil-status')
                  if (!r.data.perfil_completo) {
                    navigate('/perfil-investidor', { state: { returnTo: 'rebalanceamento' } })
                    return
                  }
                } catch { /* ignora */ }
                navigate('/sugestoes-alocacao', { state: { portfolioId: portfolioAtivo?.id, modo: 'inicial' } })
              }}
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
          <ModuleGroup modulo={modulo} positions={pos} onDelete={deletePosition} onDetalhe={(p) => setAnalisando(p)} portfolioTotal={totalCurrent} onEditCaixa={editarCaixa} onDeleteCaixa={excluirCaixa} />
        </motion.div>
      ))}

      <AnimatePresence>
        {showAdd && (
          <AddModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); loadPositions() }} />
        )}
      </AnimatePresence>

      {/* Modal de encerramento inteligente */}
      <AnimatePresence>
        {encerrando && (
          <EncerrarPosicaoModal
            position={encerrando}
            onClose={() => setEncerrando(null)}
            onSuccess={onEncerrarSuccess}
          />
        )}
      </AnimatePresence>

      {/* Modal editar CAIXA */}
      <AnimatePresence>
        {editandoCaixa && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
            onClick={() => setEditandoCaixa(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="apex-card p-6 w-full max-w-sm space-y-4"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold" style={{ color: '#f1f5f9' }}>Editar Caixa</h3>
                <button onClick={() => setEditandoCaixa(null)}><X size={18} style={{ color: '#64748b' }} /></button>
              </div>
              <p className="text-xs" style={{ color: '#64748b' }}>Defina o saldo da Reserva de Liquidez:</p>
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono" style={{ color: '#64748b' }}>R$</span>
                <input
                  autoFocus
                  type="text"
                  value={caixaInput}
                  onChange={e => setCaixaInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') salvarCaixa(); if (e.key === 'Escape') setEditandoCaixa(null) }}
                  className="bg-transparent border-b text-lg font-mono outline-none flex-1"
                  style={{ borderColor: '#00E676', color: '#f1f5f9' }}
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setEditandoCaixa(null)}
                  className="px-4 py-2 rounded-xl text-sm"
                  style={{ color: '#64748b' }}
                >Cancelar</button>
                <button
                  onClick={salvarCaixa}
                  className="px-4 py-2 rounded-xl text-sm font-semibold"
                  style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}
                >Salvar</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

