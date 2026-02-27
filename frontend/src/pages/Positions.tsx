import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, X, TrendingUp, TrendingDown, Circle, Trash2, ChevronDown, ChevronUp, BrainCircuit, LayoutList } from 'lucide-react'
import AnaliseModal from '@/components/AnaliseModal'
import CarteiraPanel from '@/components/CarteiraPanel'
import api from '@/services/api'

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
  RF: '#FFD740', OPCAO: '#FF9800', BDR: '#64FFDA', DIVIDENDO: '#FFD740', CAIXA: '#475569',
}

const emptyForm: FormData = { ticker: '', nome: '', tipo: 'ACAO', modulo: 'momentum', quantidade: '', preco_medio: '', stop_loss: '' }

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

function ModuleGroup({ modulo, positions, onDelete, onAnalise }: { modulo: string; positions: Position[]; onDelete: (id: number) => void; onAnalise: (id: number, ticker: string, modulo: string, tese?: string | null) => void }) {
  const [open, setOpen] = useState(true)
  const totalVal = positions.reduce((a, p) => a + p.valor_atual, 0)
  const totalPL = positions.reduce((a, p) => a + p.pl_reais, 0)

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
                    <button
                      onClick={() => onAnalise(p.id, p.ticker, p.modulo || 'outros', p.tese)}
                      title="Analisar posição"
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
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showCarteira, setShowCarteira] = useState(false)
  const [analisando, setAnalisando] = useState<{ id: number; ticker: string; modulo: string; tese?: string | null } | null>(null)

  const loadPositions = async () => {
    setLoading(true)
    try {
      const res = await api.get('/portfolio/posicoes')
      setPositions(res.data)
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
    if (!confirm('Encerrar esta posição?')) return
    try {
      await api.delete(`/portfolio/posicoes/${id}`)
      setPositions(p => p.filter(x => x.id !== id))
    } catch { /* silent */ }
  }

  useEffect(() => { refreshPrices() }, [])

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

  return (
    <div className="p-8 space-y-6">
      {/* Side panel análise de carteira */}
      {showCarteira && <CarteiraPanel onClose={() => setShowCarteira(false)} />}

      {/* Análise IA modal */}
      {analisando && (
        <AnaliseModal
          positionId={analisando.id}
          ticker={analisando.ticker}
          modulo={analisando.modulo}
          tese={analisando.tese}
          onClose={() => setAnalisando(null)}
          onTeseSalva={(novaTese) => {
            setPositions(prev => prev.map(p =>
              p.id === analisando.id ? { ...p, tese: novaTese } : p
            ))
          }}
        />
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
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} />
            Nova Posição
          </button>
        </div>
      </div>

      {positions.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-3 gap-4">
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
            Adicione suas posições para que o gestor APEX possa monitorar e analisar seu portfólio.
          </p>
          <button onClick={() => setShowAdd(true)} className="btn-primary inline-flex items-center gap-2">
            <Plus size={15} /> Adicionar Primeira Posição
          </button>
        </motion.div>
      )}

      {!loading && Object.entries(grouped).map(([modulo, pos]) => (
        <motion.div key={modulo} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <ModuleGroup modulo={modulo} positions={pos} onDelete={deletePosition} onAnalise={(id, ticker, mod, tese) => setAnalisando({ id, ticker, modulo: mod, tese })} />
        </motion.div>
      ))}

      <AnimatePresence>
        {showAdd && (
          <AddModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); loadPositions() }} />
        )}
      </AnimatePresence>
    </div>
  )
}

