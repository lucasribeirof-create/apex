/**
 * Página de histórico — posições encerradas separadas em Trades vs Carteira.
 * Com busca, filtro por período/módulo e ordenação por coluna.
 */
import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { History, Trash2, ArrowLeft, Zap, Briefcase, Search, ChevronUp, ChevronDown, Calendar } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

const MODULE_LABELS: Record<string, string> = {
  etfs: 'ETFs', fiis: 'FIIs', momentum: 'Momentum', wheel: 'Wheel',
  renda_fixa: 'Renda Fixa', alpha: 'Alpha', dividendos: 'Dividendos',
  teses: 'Teses', caixa: 'Caixa',
}

const MODULOS_TRADE = new Set(['momentum', 'alpha', 'wheel', 'teses'])

const PERIODOS = [
  { key: '1m', label: '1M', days: 30 },
  { key: '3m', label: '3M', days: 90 },
  { key: '6m', label: '6M', days: 180 },
  { key: '1y', label: '1A', days: 365 },
  { key: 'all', label: 'Tudo', days: 0 },
] as const

type SortKey = 'ticker' | 'data_saida' | 'duracao_dias' | 'pl_reais' | 'pl_percentual'
type SortDir = 'asc' | 'desc'

interface HistPosition {
  id: number; ticker: string; nome: string; tipo: string; modulo: string
  quantidade: number; preco_medio: number; preco_atual: number | null
  valor_investido: number; pl_reais: number | null; pl_percentual: number | null
  data_abertura: string | null; data_saida: string | null
  motivo_saida: string | null; duracao_dias: number | null
}

function isTrade(p: HistPosition) { return MODULOS_TRADE.has(p.modulo) }

// ─── Summary Cards ──────────────────────────────────────────────────────────

function SummaryCards({ items }: { items: HistPosition[] }) {
  if (items.length === 0) return null
  const totalPL = items.reduce((a, p) => a + (p.pl_reais || 0), 0)
  const wins = items.filter(p => (p.pl_reais || 0) > 0).length
  const losses = items.filter(p => (p.pl_reais || 0) < 0).length
  const winRate = (wins / items.length) * 100
  const avgReturn = items.reduce((a, p) => a + (p.pl_percentual || 0), 0) / items.length
  const best = items.reduce((b, p) => (p.pl_reais || 0) > (b.pl_reais || 0) ? p : b, items[0])
  const worst = items.reduce((w, p) => (p.pl_reais || 0) < (w.pl_reais || 0) ? p : w, items[0])

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
      <div className="apex-card p-4">
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Total</p>
        <p className="text-lg font-bold font-mono mt-1" style={{ color: '#f1f5f9' }}>{items.length}</p>
        <p className="text-xs mt-0.5" style={{ color: '#475569' }}>{wins}W / {losses}L</p>
      </div>
      <div className="apex-card p-4">
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Win Rate</p>
        <p className="text-lg font-bold font-mono mt-1" style={{ color: winRate >= 50 ? '#00E676' : '#FF5252' }}>{winRate.toFixed(1)}%</p>
      </div>
      <div className="apex-card p-4">
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>P&L Total</p>
        <p className="text-lg font-bold font-mono mt-1" style={{ color: totalPL >= 0 ? '#00E676' : '#FF5252' }}>
          {totalPL >= 0 ? '+' : ''}R$ {totalPL.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
        </p>
      </div>
      <div className="apex-card p-4">
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Retorno Médio</p>
        <p className="text-lg font-bold font-mono mt-1" style={{ color: avgReturn >= 0 ? '#00E676' : '#FF5252' }}>
          {avgReturn >= 0 ? '+' : ''}{avgReturn.toFixed(2)}%
        </p>
      </div>
      {(best.pl_reais || 0) > 0 && (
        <div className="apex-card p-4">
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Melhor</p>
          <p className="text-sm font-bold font-mono mt-1" style={{ color: '#00E676' }}>{best.ticker}</p>
          <p className="text-xs font-mono" style={{ color: '#00E676' }}>+R$ {(best.pl_reais || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
        </div>
      )}
      {(worst.pl_reais || 0) < 0 && (
        <div className="apex-card p-4">
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Pior</p>
          <p className="text-sm font-bold font-mono mt-1" style={{ color: '#FF5252' }}>{worst.ticker}</p>
          <p className="text-xs font-mono" style={{ color: '#FF5252' }}>R$ {(worst.pl_reais || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
        </div>
      )}
    </motion.div>
  )
}

// ─── Sort Header ────────────────────────────────────────────────────────────

function SortHeader({ label, field, sortKey, sortDir, onSort, className }: {
  label: string; field: SortKey; sortKey: SortKey; sortDir: SortDir; onSort: (k: SortKey) => void; className?: string
}) {
  const active = sortKey === field
  return (
    <button onClick={() => onSort(field)} className={`flex items-center gap-0.5 hover:text-slate-300 transition-colors ${className || ''}`}
      style={{ color: active ? '#f1f5f9' : '#475569' }}>
      <span>{label}</span>
      {active && (sortDir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />)}
    </button>
  )
}

// ─── Table ──────────────────────────────────────────────────────────────────

function HistTable({ items, onDelete, accentColor, sortKey, sortDir, onSort }: {
  items: HistPosition[]; onDelete: (id: number, ticker: string) => void; accentColor: string
  sortKey: SortKey; sortDir: SortDir; onSort: (k: SortKey) => void
}) {
  const grouped = items.reduce<Record<string, HistPosition[]>>((acc, p) => {
    const key = p.modulo || 'outros'
    ;(acc[key] ??= []).push(p)
    return acc
  }, {})

  return (
    <>
      {Object.entries(grouped).map(([modulo, rows]) => (
        <motion.div key={modulo} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className="apex-card overflow-hidden">
            <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid #0f1724' }}>
              <div className="w-2 h-2 rounded-full" style={{ background: accentColor }} />
              <span className="text-sm font-mono font-medium" style={{ color: '#f1f5f9' }}>{MODULE_LABELS[modulo] || modulo}</span>
              <span className="text-xs" style={{ color: '#475569' }}>({rows.length})</span>
            </div>

            <div className="hidden md:grid grid-cols-8 px-4 py-2 text-xs font-mono uppercase tracking-wider" style={{ borderBottom: '1px solid #0f1724' }}>
              <SortHeader label="Ticker" field="ticker" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <span className="text-right" style={{ color: '#475569' }}>PM</span>
              <span className="text-right" style={{ color: '#475569' }}>Abertura</span>
              <SortHeader label="Saída" field="data_saida" sortKey={sortKey} sortDir={sortDir} onSort={onSort} className="justify-end" />
              <SortHeader label="Duração" field="duracao_dias" sortKey={sortKey} sortDir={sortDir} onSort={onSort} className="justify-end" />
              <SortHeader label="P&L R$" field="pl_reais" sortKey={sortKey} sortDir={sortDir} onSort={onSort} className="justify-end" />
              <SortHeader label="P&L %" field="pl_percentual" sortKey={sortKey} sortDir={sortDir} onSort={onSort} className="justify-end" />
              <span></span>
            </div>

            {rows.map(p => (
              <div key={p.id} className="grid grid-cols-8 px-4 py-2.5 items-center hover:bg-white/[0.02] transition-colors group" style={{ borderBottom: '1px solid #080c14' }}>
                <div>
                  <p className="text-sm font-mono font-medium" style={{ color: '#f1f5f9' }}>{p.ticker}</p>
                  <p className="text-[10px]" style={{ color: '#475569' }}>{p.motivo_saida || ''}</p>
                </div>
                <p className="text-xs font-mono text-right" style={{ color: '#94a3b8' }}>R$ {(p.preco_medio || 0).toFixed(2)}</p>
                <p className="text-xs font-mono text-right" style={{ color: '#94a3b8' }}>
                  {p.data_abertura ? new Date(p.data_abertura).toLocaleDateString('pt-BR') : '—'}
                </p>
                <p className="text-xs font-mono text-right" style={{ color: '#94a3b8' }}>
                  {p.data_saida ? new Date(p.data_saida).toLocaleDateString('pt-BR') : '—'}
                </p>
                <p className="text-xs font-mono text-right" style={{ color: '#94a3b8' }}>{p.duracao_dias != null ? `${p.duracao_dias}d` : '—'}</p>
                <p className="text-sm font-mono font-bold text-right" style={{ color: (p.pl_reais || 0) >= 0 ? '#00E676' : '#FF5252' }}>
                  {(p.pl_reais || 0) >= 0 ? '+' : ''}R$ {(p.pl_reais || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </p>
                <p className="text-xs font-mono text-right" style={{ color: (p.pl_percentual || 0) >= 0 ? '#00E676' : '#FF5252' }}>
                  {(p.pl_percentual || 0) >= 0 ? '+' : ''}{(p.pl_percentual || 0).toFixed(2)}%
                </p>
                <div className="flex justify-end">
                  <button onClick={() => onDelete(p.id, p.ticker)}
                    className="p-1.5 rounded-lg opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-all hover:bg-red-500/10"
                    style={{ color: '#FF5252' }} title="Remover do histórico">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      ))}
    </>
  )
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function HistoricoPage() {
  const navigate = useNavigate()
  const [positions, setPositions] = useState<HistPosition[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'trades' | 'carteira'>('trades')
  const [busca, setBusca] = useState('')
  const [periodo, setPeriodo] = useState<string>('all')
  const [filtroModulo, setFiltroModulo] = useState<string>('todos')
  const [sortKey, setSortKey] = useState<SortKey>('data_saida')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => { loadHistorico() }, [])
  useEffect(() => { setFiltroModulo('todos') }, [tab])

  useEffect(() => {
    const handler = () => loadHistorico()
    window.addEventListener('portfolio-changed', handler)
    return () => window.removeEventListener('portfolio-changed', handler)
  }, [])

  const loadHistorico = async () => {
    setLoading(true)
    try {
      const res = await api.get('/portfolio/posicoes/historico')
      setPositions(res.data?.posicoes || [])
    } catch { /* silent */ }
    setLoading(false)
  }

  const handleDelete = async (id: number, ticker: string) => {
    if (!confirm(`Remover ${ticker} permanentemente do histórico?`)) return
    try {
      await api.delete(`/portfolio/posicoes/${id}/permanente`)
      setPositions(prev => prev.filter(p => p.id !== id))
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Erro ao remover')
    }
  }

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc') }
    else { setSortKey(key); setSortDir('desc') }
  }

  // Pipeline: tab → período → busca → módulo → sort
  const filteredItems = useMemo(() => {
    let items = tab === 'trades' ? positions.filter(isTrade) : positions.filter(p => !isTrade(p))

    // Período
    const periodoObj = PERIODOS.find(p => p.key === periodo)
    if (periodoObj && periodoObj.days > 0) {
      const cutoff = new Date()
      cutoff.setDate(cutoff.getDate() - periodoObj.days)
      items = items.filter(p => p.data_saida && new Date(p.data_saida) >= cutoff)
    }

    // Busca por ticker
    if (busca.trim()) {
      const q = busca.trim().toUpperCase()
      items = items.filter(p => p.ticker.includes(q) || (p.nome || '').toUpperCase().includes(q))
    }

    // Módulo
    if (filtroModulo !== 'todos') {
      items = items.filter(p => p.modulo === filtroModulo)
    }

    // Sort
    items = [...items].sort((a, b) => {
      let va: number, vb: number
      switch (sortKey) {
        case 'ticker': return sortDir === 'asc' ? a.ticker.localeCompare(b.ticker) : b.ticker.localeCompare(a.ticker)
        case 'data_saida':
          va = a.data_saida ? new Date(a.data_saida).getTime() : 0
          vb = b.data_saida ? new Date(b.data_saida).getTime() : 0
          break
        case 'duracao_dias': va = a.duracao_dias ?? 0; vb = b.duracao_dias ?? 0; break
        case 'pl_reais': va = a.pl_reais ?? 0; vb = b.pl_reais ?? 0; break
        case 'pl_percentual': va = a.pl_percentual ?? 0; vb = b.pl_percentual ?? 0; break
        default: va = 0; vb = 0
      }
      return sortDir === 'asc' ? va - vb : vb - va
    })

    return items
  }, [positions, tab, periodo, busca, filtroModulo, sortKey, sortDir])

  // Módulos disponíveis no tab atual (para filtro)
  const modulosDisponiveis = useMemo(() => {
    const base = tab === 'trades' ? positions.filter(isTrade) : positions.filter(p => !isTrade(p))
    return [...new Set(base.map(p => p.modulo).filter(Boolean))]
  }, [positions, tab])

  const trades = positions.filter(isTrade)
  const carteira = positions.filter(p => !isTrade(p))

  return (
    <div className="p-8 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/positions')} className="p-2 rounded-lg transition-all hover:bg-white/5" style={{ color: '#64748b' }}>
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Histórico</h1>
            <p className="text-sm mt-1" style={{ color: '#64748b' }}>{positions.length} posição(ões) encerrada(s)</p>
          </div>
        </div>

        {/* Tab: Trades / Carteira */}
        <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid #1e293b' }}>
          <button onClick={() => setTab('trades')}
            className="px-4 py-2 text-xs font-medium transition-all flex items-center gap-1.5"
            style={{ background: tab === 'trades' ? 'rgba(255,152,0,0.12)' : 'transparent', color: tab === 'trades' ? '#FF9800' : '#64748b' }}>
            <Zap size={12} /> Trades ({trades.length})
          </button>
          <button onClick={() => setTab('carteira')}
            className="px-4 py-2 text-xs font-medium transition-all flex items-center gap-1.5"
            style={{ background: tab === 'carteira' ? 'rgba(0,230,118,0.12)' : 'transparent', color: tab === 'carteira' ? '#00E676' : '#64748b' }}>
            <Briefcase size={12} /> Carteira ({carteira.length})
          </button>
        </div>
      </div>

      {/* Toolbar: busca + período + módulo */}
      {!loading && positions.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[180px] max-w-[280px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#475569' }} />
            <input
              type="text" value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar ticker..."
              className="w-full pl-9 pr-3 py-2 rounded-lg text-xs font-mono bg-transparent outline-none transition-colors"
              style={{ border: '1px solid #1e293b', color: '#f1f5f9' }}
            />
          </div>

          {/* Período */}
          <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid #1e293b' }}>
            <div className="flex items-center px-2" style={{ color: '#475569' }}><Calendar size={12} /></div>
            {PERIODOS.map(p => (
              <button key={p.key} onClick={() => setPeriodo(p.key)}
                className="px-2.5 py-1.5 text-[11px] font-mono font-medium transition-all"
                style={{
                  background: periodo === p.key ? 'rgba(255,152,0,0.12)' : 'transparent',
                  color: periodo === p.key ? '#FF9800' : '#64748b',
                }}>
                {p.label}
              </button>
            ))}
          </div>

          {/* Filtro módulo */}
          {modulosDisponiveis.length > 1 && (
            <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid #1e293b' }}>
              <button onClick={() => setFiltroModulo('todos')}
                className="px-2.5 py-1.5 text-[11px] font-mono font-medium transition-all"
                style={{ background: filtroModulo === 'todos' ? 'rgba(0,230,118,0.12)' : 'transparent', color: filtroModulo === 'todos' ? '#00E676' : '#64748b' }}>
                Todos
              </button>
              {modulosDisponiveis.map(m => (
                <button key={m} onClick={() => setFiltroModulo(m)}
                  className="px-2.5 py-1.5 text-[11px] font-mono font-medium transition-all"
                  style={{ background: filtroModulo === m ? 'rgba(0,230,118,0.12)' : 'transparent', color: filtroModulo === m ? '#00E676' : '#64748b' }}>
                  {MODULE_LABELS[m] || m}
                </button>
              ))}
            </div>
          )}

          {/* Count */}
          <span className="text-[11px] font-mono ml-auto" style={{ color: '#475569' }}>
            {filteredItems.length} resultado{filteredItems.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-3" style={{ color: '#64748b' }}>
          <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#FF9800' }} />
          <span className="text-sm">Carregando histórico...</span>
        </div>
      )}

      {!loading && filteredItems.length === 0 && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-12 text-center">
          <History size={28} className="mx-auto mb-3" style={{ color: '#1e293b' }} />
          <h3 className="font-semibold mb-2" style={{ color: '#f1f5f9' }}>
            {busca || periodo !== 'all' || filtroModulo !== 'todos'
              ? 'Nenhum resultado para os filtros aplicados'
              : tab === 'trades' ? 'Nenhum trade encerrado' : 'Nenhuma posição de carteira encerrada'}
          </h3>
          <p className="text-sm" style={{ color: '#64748b' }}>
            {busca || periodo !== 'all' || filtroModulo !== 'todos'
              ? 'Tente ajustar a busca ou período.'
              : tab === 'trades'
                ? 'Trades encerrados (Momentum, Alpha, Wheel, Teses) aparecerão aqui.'
                : 'Posições de carteira encerradas (Dividendos, ETFs, FIIs, Renda Fixa) aparecerão aqui.'}
          </p>
        </motion.div>
      )}

      {!loading && filteredItems.length > 0 && (
        <>
          <div className="flex items-center gap-2">
            {tab === 'trades' ? (
              <>
                <Zap size={14} style={{ color: '#FF9800' }} />
                <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#FF9800' }}>Trades — Operações especulativas</span>
              </>
            ) : (
              <>
                <Briefcase size={14} style={{ color: '#00E676' }} />
                <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#00E676' }}>Carteira — Rebalanceamento / Fechamento</span>
              </>
            )}
          </div>

          <SummaryCards items={filteredItems} />
          <HistTable
            items={filteredItems} onDelete={handleDelete}
            accentColor={tab === 'trades' ? '#FF9800' : '#00E676'}
            sortKey={sortKey} sortDir={sortDir} onSort={handleSort}
          />
        </>
      )}
    </div>
  )
}
