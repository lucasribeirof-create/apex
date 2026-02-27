import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, X, TrendingUp, TrendingDown, ChevronDown, ChevronUp, Trash2, PlusCircle, Lightbulb, Globe, Building2, BrainCircuit } from 'lucide-react'
import api from '@/services/api'
import AnaliseModal from '@/components/AnaliseModal'

interface Tese {
  id: number
  ticker: string
  nome: string
  tipo: string
  mercado: string
  moeda: string
  tese: string | null
  quantidade: number
  preco_medio: number
  preco_medio_usd: number | null
  preco_atual_brl: number
  preco_atual_usd: number | null
  valor_investido_brl: number
  valor_atual_brl: number
  pl_reais: number
  pl_percentual: number
  dolar_brl: number
  num_aportes: number
  data_entrada: string | null
}

interface Aporte {
  id: number
  data: string
  quantidade: number
  preco: number
  valor_total: number
  nota: string | null
}

const MERCADO_ICONS: Record<string, React.FC<{ size?: number; style?: React.CSSProperties }>> = {
  B3: Building2,
  BDR: Globe,
  NYSE: Globe,
  NASDAQ: Globe,
  AMEX: Globe,
}

const MERCADO_COLORS: Record<string, string> = {
  B3: '#00E676',
  BDR: '#00BFA5',
  NYSE: '#64FFDA',
  NASDAQ: '#64FFDA',
  AMEX: '#64FFDA',
}

function fmt(v: number, decimals = 2) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function fmtCurrency(v: number, moeda: 'BRL' | 'USD' = 'BRL') {
  if (moeda === 'USD') return `US$ ${fmt(v)}`
  return `R$ ${fmt(v)}`
}

export default function TesesPage() {
  const [teses, setTeses] = useState<Tese[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [aportes, setAportes] = useState<Record<number, Aporte[]>>({})
  const [showAddModal, setShowAddModal] = useState(false)
  const [showAporteModal, setShowAporteModal] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [analisando, setAnalisando] = useState<{ id: number; ticker: string; modulo: string } | null>(null)

  // Form nova tese
  const [form, setForm] = useState({
    ticker: '', nome: '', tese: '', tipo: 'ACAO',
    mercado: 'B3', moeda: 'BRL',
    quantidade: '', preco_medio: '', nota_aporte: '',
  })

  // Form novo aporte
  const [aporteForm, setAporteForm] = useState({ quantidade: '', preco: '', nota: '' })

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const r = await api.get('/teses')
      setTeses(r.data)
    } catch {
      setError('Erro ao carregar teses')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleExpand = async (id: number) => {
    if (expandedId === id) { setExpandedId(null); return }
    setExpandedId(id)
    if (!aportes[id]) {
      const r = await api.get(`/teses/${id}/aportes`)
      setAportes(prev => ({ ...prev, [id]: r.data.aportes }))
    }
  }

  const handleAddTese = async () => {
    if (!form.ticker || !form.tese || !form.quantidade || !form.preco_medio) {
      setError('Preencha ticker, tese, quantidade e preço médio')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post('/teses', {
        ticker: form.ticker.toUpperCase(),
        nome: form.nome || undefined,
        tese: form.tese,
        tipo: form.tipo,
        mercado: form.mercado,
        moeda: form.moeda,
        quantidade: parseFloat(form.quantidade),
        preco_medio: parseFloat(form.preco_medio),
        nota_aporte: form.nota_aporte || undefined,
      })
      setShowAddModal(false)
      setForm({ ticker: '', nome: '', tese: '', tipo: 'ACAO', mercado: 'B3', moeda: 'BRL', quantidade: '', preco_medio: '', nota_aporte: '' })
      await load()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const handleAddAporte = async (positionId: number) => {
    if (!aporteForm.quantidade || !aporteForm.preco) {
      setError('Preencha quantidade e preço')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.post(`/teses/${positionId}/aportes`, {
        quantidade: parseFloat(aporteForm.quantidade),
        preco: parseFloat(aporteForm.preco),
        nota: aporteForm.nota || undefined,
      })
      // Atualiza aportes e posições
      const r = await api.get(`/teses/${positionId}/aportes`)
      setAportes(prev => ({ ...prev, [positionId]: r.data.aportes }))
      setShowAporteModal(null)
      setAporteForm({ quantidade: '', preco: '', nota: '' })
      await load()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Erro ao registrar aporte')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Encerrar esta posição?')) return
    setDeleting(id)
    try {
      await api.delete(`/teses/${id}`)
      await load()
    } catch {
      setError('Erro ao encerrar posição')
    } finally {
      setDeleting(null)
    }
  }

  const totalInvestido = teses.reduce((s, t) => s + t.valor_investido_brl, 0)
  const totalAtual = teses.reduce((s, t) => s + t.valor_atual_brl, 0)
  const totalPL = totalAtual - totalInvestido
  const totalPLPct = totalInvestido > 0 ? (totalPL / totalInvestido) * 100 : 0

  return (
    <div className="p-6 max-w-5xl mx-auto" style={{ color: '#f1f5f9' }}>
      {/* Análise IA modal */}
      {analisando && (
        <AnaliseModal
          positionId={analisando.id}
          ticker={analisando.ticker}
          modulo={analisando.modulo}
          onClose={() => setAnalisando(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Lightbulb size={24} style={{ color: '#FFD740' }} />
            Teses
          </h1>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            Buy &amp; Hold por convicção — DCA estrutural
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
          style={{ background: '#00E676', color: '#0a0e17' }}
        >
          <Plus size={16} />
          Nova Tese
        </button>
      </div>

      {/* Resumo */}
      {teses.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Investido', value: `R$ ${fmt(totalInvestido)}` },
            { label: 'Atual', value: `R$ ${fmt(totalAtual)}` },
            {
              label: 'Resultado',
              value: `${totalPL >= 0 ? '+' : ''}R$ ${fmt(totalPL)} (${totalPLPct >= 0 ? '+' : ''}${fmt(totalPLPct)}%)`,
              color: totalPL >= 0 ? '#00E676' : '#FF5252',
            },
          ].map(card => (
            <div key={card.label} className="rounded-xl p-4 border" style={{ background: '#111827', borderColor: '#1e293b' }}>
              <p className="text-xs mb-1" style={{ color: '#64748b' }}>{card.label}</p>
              <p className="text-lg font-bold" style={{ color: card.color || '#f1f5f9' }}>{card.value}</p>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm" style={{ background: 'rgba(255,82,82,0.1)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.2)' }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: '#00E676 transparent transparent transparent' }} />
        </div>
      ) : teses.length === 0 ? (
        <div className="text-center py-20" style={{ color: '#64748b' }}>
          <Lightbulb size={48} className="mx-auto mb-4 opacity-30" />
          <p className="font-medium">Nenhuma tese cadastrada</p>
          <p className="text-sm mt-1">Adicione sua primeira posição de convicção</p>
        </div>
      ) : (
        <div className="space-y-3">
          {teses.map(t => {
            const MercadoIcon = MERCADO_ICONS[t.mercado] || Globe
            const mercadoColor = MERCADO_COLORS[t.mercado] || '#64748b'
            const isExpanded = expandedId === t.id
            const plPositivo = t.pl_reais >= 0

            return (
              <motion.div
                key={t.id}
                layout
                className="rounded-xl border overflow-hidden"
                style={{ background: '#111827', borderColor: '#1e293b' }}
              >
                {/* Linha principal */}
                <div className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    {/* Left: ticker + tese */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-lg" style={{ color: '#f1f5f9' }}>{t.ticker}</span>
                        <span className="text-xs px-2 py-0.5 rounded font-mono flex items-center gap-1"
                          style={{ background: `${mercadoColor}18`, color: mercadoColor, border: `1px solid ${mercadoColor}33` }}>
                          <MercadoIcon size={10} />
                          {t.mercado}
                        </span>
                        {t.moeda === 'USD' && (
                          <span className="text-xs px-2 py-0.5 rounded font-mono" style={{ background: 'rgba(100,255,218,0.1)', color: '#64FFDA', border: '1px solid rgba(100,255,218,0.2)' }}>
                            USD
                          </span>
                        )}
                        <span className="text-xs" style={{ color: '#475569' }}>{t.nome !== t.ticker ? t.nome : ''}</span>
                      </div>
                      {t.tese && (
                        <p className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                          {t.tese}
                        </p>
                      )}
                    </div>

                    {/* Right: números */}
                    <div className="text-right shrink-0">
                      <div className="flex items-center justify-end gap-1 mb-1">
                        {plPositivo
                          ? <TrendingUp size={14} style={{ color: '#00E676' }} />
                          : <TrendingDown size={14} style={{ color: '#FF5252' }} />}
                        <span className="font-bold text-lg" style={{ color: plPositivo ? '#00E676' : '#FF5252' }}>
                          {plPositivo ? '+' : ''}{fmt(t.pl_percentual)}%
                        </span>
                      </div>
                      <p className="text-sm" style={{ color: plPositivo ? '#00E676' : '#FF5252' }}>
                        {plPositivo ? '+' : ''}R$ {fmt(t.pl_reais)}
                      </p>
                      <p className="text-xs mt-1" style={{ color: '#64748b' }}>
                        {t.moeda === 'USD'
                          ? `US$ ${fmt(t.preco_atual_usd ?? 0, 2)} → R$ ${fmt(t.preco_atual_brl)}`
                          : `atual R$ ${fmt(t.preco_atual_brl)}`}
                      </p>
                      <p className="text-xs" style={{ color: '#475569' }}>
                        PM: {t.moeda === 'USD'
                          ? `US$ ${fmt(t.preco_medio_usd ?? 0, 2)}`
                          : `R$ ${fmt(t.preco_medio)}`}
                      </p>
                    </div>
                  </div>

                  {/* Footer da card */}
                  <div className="flex items-center justify-between mt-3 pt-3 border-t" style={{ borderColor: '#1e293b' }}>
                    <div className="flex items-center gap-4 text-xs" style={{ color: '#64748b' }}>
                      <span>{fmt(t.quantidade, 4)} {t.tipo === 'ACAO' || t.tipo === 'BDR' ? 'ações' : 'cotas'}</span>
                      <span>Investido: R$ {fmt(t.valor_investido_brl)}</span>
                      <span>Atual: R$ {fmt(t.valor_atual_brl)}</span>
                      <span>{t.num_aportes} aporte{t.num_aportes !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setShowAporteModal(t.id); setAporteForm({ quantidade: '', preco: '', nota: '' }) }}
                        className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs transition-all"
                        style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}
                      >
                        <PlusCircle size={12} />
                        Aportar
                      </button>
                      <button
                        onClick={() => setAnalisando({ id: t.id, ticker: t.ticker, modulo: 'teses' })}
                        className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs transition-all"
                        style={{ background: 'rgba(139,92,246,0.12)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.25)' }}
                      >
                        <BrainCircuit size={12} />
                        Analisar
                      </button>
                      <button
                        onClick={() => toggleExpand(t.id)}
                        className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs transition-all"
                        style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}
                      >
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        Histórico
                      </button>
                      <button
                        onClick={() => handleDelete(t.id)}
                        disabled={deleting === t.id}
                        className="p-1.5 rounded-lg transition-all"
                        style={{ background: 'rgba(255,82,82,0.1)', color: '#FF5252' }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Histórico de aportes */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t overflow-hidden"
                      style={{ borderColor: '#1e293b' }}
                    >
                      <div className="p-4" style={{ background: '#0d1421' }}>
                        <p className="text-xs font-medium mb-3" style={{ color: '#64748b' }}>HISTÓRICO DE APORTES</p>
                        {!aportes[t.id] ? (
                          <p className="text-xs" style={{ color: '#475569' }}>Carregando...</p>
                        ) : aportes[t.id].length === 0 ? (
                          <p className="text-xs" style={{ color: '#475569' }}>Nenhum aporte registrado</p>
                        ) : (
                          <div className="space-y-2">
                            {aportes[t.id].map((a, i) => (
                              <div key={a.id} className="flex items-center justify-between text-xs py-2 border-b" style={{ borderColor: '#1e293b' }}>
                                <div className="flex items-center gap-3">
                                  <span className="font-mono" style={{ color: '#475569' }}>#{i + 1}</span>
                                  <span style={{ color: '#94a3b8' }}>
                                    {new Date(a.data).toLocaleDateString('pt-BR')}
                                  </span>
                                  {a.nota && <span style={{ color: '#64748b' }}>{a.nota}</span>}
                                </div>
                                <div className="flex items-center gap-4 text-right">
                                  <span style={{ color: '#94a3b8' }}>{fmt(a.quantidade, 4)} × {fmtCurrency(a.preco, t.moeda === 'USD' ? 'USD' : 'BRL')}</span>
                                  <span className="font-medium" style={{ color: '#f1f5f9' }}>
                                    {fmtCurrency(a.valor_total, t.moeda === 'USD' ? 'USD' : 'BRL')}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </div>
      )}

      {/* Modal — Nova Tese */}
      <AnimatePresence>
        {showAddModal && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.7)' }}
            onClick={e => e.target === e.currentTarget && setShowAddModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-lg rounded-2xl p-6 border"
              style={{ background: '#111827', borderColor: '#1e293b' }}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-bold">Nova Tese</h2>
                <button onClick={() => setShowAddModal(false)}><X size={20} style={{ color: '#64748b' }} /></button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Ticker *</label>
                    <input
                      className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      placeholder="MSFT34 / MSFT"
                      value={form.ticker}
                      onChange={e => setForm(f => ({ ...f, ticker: e.target.value.toUpperCase() }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Nome</label>
                    <input
                      className="w-full px-3 py-2 rounded-lg text-sm"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      placeholder="Microsoft"
                      value={form.nome}
                      onChange={e => setForm(f => ({ ...f, nome: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Tipo</label>
                    <select
                      className="w-full px-3 py-2 rounded-lg text-sm"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      value={form.tipo}
                      onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}
                    >
                      <option value="ACAO">Ação</option>
                      <option value="BDR">BDR</option>
                      <option value="ETF">ETF</option>
                      <option value="FII">FII</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Mercado</label>
                    <select
                      className="w-full px-3 py-2 rounded-lg text-sm"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      value={form.mercado}
                      onChange={e => {
                        const m = e.target.value
                        setForm(f => ({
                          ...f,
                          mercado: m,
                          moeda: (m === 'NYSE' || m === 'NASDAQ' || m === 'AMEX') ? 'USD' : 'BRL',
                        }))
                      }}
                    >
                      <option value="B3">B3</option>
                      <option value="BDR">BDR</option>
                      <option value="NYSE">NYSE</option>
                      <option value="NASDAQ">NASDAQ</option>
                      <option value="AMEX">AMEX</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Moeda</label>
                    <select
                      className="w-full px-3 py-2 rounded-lg text-sm"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      value={form.moeda}
                      onChange={e => setForm(f => ({ ...f, moeda: e.target.value }))}
                    >
                      <option value="BRL">BRL</option>
                      <option value="USD">USD</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Tese de Investimento *</label>
                  <textarea
                    className="w-full px-3 py-2 rounded-lg text-sm resize-none"
                    style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9', minHeight: '80px' }}
                    placeholder="Ex: Microsoft está barata relativo ao setor. Tese de IA (Copilot + Azure) ainda no início do ciclo de adoção. DCA mensal até valuation justo."
                    value={form.tese}
                    onChange={e => setForm(f => ({ ...f, tese: e.target.value }))}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Quantidade *</label>
                    <input
                      type="number" min="0"
                      className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      placeholder="10"
                      value={form.quantidade}
                      onChange={e => setForm(f => ({ ...f, quantidade: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#64748b' }}>
                      Preço Médio * ({form.moeda === 'USD' ? 'USD' : 'R$'})
                    </label>
                    <input
                      type="number" min="0" step="0.01"
                      className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                      style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                      placeholder={form.moeda === 'USD' ? '420.00' : '150.00'}
                      value={form.preco_medio}
                      onChange={e => setForm(f => ({ ...f, preco_medio: e.target.value }))}
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Nota do 1º Aporte</label>
                  <input
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                    placeholder="Ex: entrada inicial, valuation -20% da média histórica"
                    value={form.nota_aporte}
                    onChange={e => setForm(f => ({ ...f, nota_aporte: e.target.value }))}
                  />
                </div>

                {error && <p className="text-xs" style={{ color: '#FF5252' }}>{error}</p>}

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => setShowAddModal(false)}
                    className="flex-1 py-2 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={handleAddTese}
                    disabled={saving}
                    className="flex-1 py-2 rounded-lg text-sm font-medium transition-all"
                    style={{ background: '#00E676', color: '#0a0e17' }}
                  >
                    {saving ? 'Salvando...' : 'Adicionar Tese'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modal — Novo Aporte */}
      <AnimatePresence>
        {showAporteModal !== null && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.7)' }}
            onClick={e => e.target === e.currentTarget && setShowAporteModal(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-sm rounded-2xl p-6 border"
              style={{ background: '#111827', borderColor: '#1e293b' }}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold">Novo Aporte</h2>
                <button onClick={() => setShowAporteModal(null)}><X size={20} style={{ color: '#64748b' }} /></button>
              </div>
              {(() => {
                const pos = teses.find(t => t.id === showAporteModal)
                const moeda = pos?.moeda ?? 'BRL'
                return (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Quantidade *</label>
                      <input
                        type="number" min="0"
                        className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                        style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                        placeholder="5"
                        value={aporteForm.quantidade}
                        onChange={e => setAporteForm(f => ({ ...f, quantidade: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#64748b' }}>
                        Preço * ({moeda === 'USD' ? 'USD' : 'R$'})
                      </label>
                      <input
                        type="number" min="0" step="0.01"
                        className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                        style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                        placeholder={moeda === 'USD' ? '390.00' : '145.00'}
                        value={aporteForm.preco}
                        onChange={e => setAporteForm(f => ({ ...f, preco: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#64748b' }}>Nota</label>
                      <input
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background: '#0d1421', border: '1px solid #1e293b', color: '#f1f5f9' }}
                        placeholder="Ex: DCA mensal, queda de 5% no dia"
                        value={aporteForm.nota}
                        onChange={e => setAporteForm(f => ({ ...f, nota: e.target.value }))}
                      />
                    </div>
                    {error && <p className="text-xs" style={{ color: '#FF5252' }}>{error}</p>}
                    <div className="flex gap-3">
                      <button
                        onClick={() => setShowAporteModal(null)}
                        className="flex-1 py-2 rounded-lg text-sm"
                        style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={() => handleAddAporte(showAporteModal!)}
                        disabled={saving}
                        className="flex-1 py-2 rounded-lg text-sm font-medium"
                        style={{ background: '#00E676', color: '#0a0e17' }}
                      >
                        {saving ? 'Salvando...' : 'Registrar'}
                      </button>
                    </div>
                  </div>
                )
              })()}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
