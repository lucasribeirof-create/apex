import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { DollarSign, PieChart, Calendar, TrendingUp, RefreshCw, ChevronDown, ChevronUp, CheckCircle2, AlertCircle } from 'lucide-react'
import api from '@/services/api'

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtMoney(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-700/50 ${className}`} />
}

type Tab = 'ativos' | 'historico' | 'calendario'

export default function DividendosPage() {
  const [resumo, setResumo] = useState<any>(null)
  const [ativos, setAtivos] = useState<any>(null)
  const [historico, setHistorico] = useState<any>(null)
  const [calendario, setCalendario] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('ativos')
  const [expandedSectors, setExpandedSectors] = useState<Record<string, boolean>>({})
  const [expandedMonths, setExpandedMonths] = useState<Record<string, boolean>>({})

  async function loadData() {
    setLoading(true)
    try {
      const [res, atv, hist, cal] = await Promise.all([
        api.get('/dividendos/resumo'),
        api.get('/dividendos/ativos'),
        api.get('/dividendos/historico'),
        api.get('/dividendos/calendario'),
      ])
      setResumo(res.data)
      setAtivos(atv.data)
      setHistorico(hist.data)
      setCalendario(cal.data)
    } catch (e) {
      console.error('Erro ao carregar dividendos:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  useEffect(() => {
    const handler = () => loadData()
    window.addEventListener('portfolio-changed', handler)
    return () => window.removeEventListener('portfolio-changed', handler)
  }, [])

  const toggleSector = (s: string) => setExpandedSectors(prev => ({ ...prev, [s]: !prev[s] }))
  const toggleMonth = (m: string) => setExpandedMonths(prev => ({ ...prev, [m]: !prev[m] }))

  const tabs: { key: Tab; label: string; icon: typeof DollarSign }[] = [
    { key: 'ativos', label: 'Ativos por Setor', icon: PieChart },
    { key: 'historico', label: 'Histórico', icon: TrendingUp },
    { key: 'calendario', label: 'Calendário', icon: Calendar },
  ]

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Dividendos</h1>
          <p className="text-sm mt-1" style={{ color: '#475569' }}>Acompanhe proventos recebidos, projeções e calendário</p>
        </div>
        <button
          onClick={loadData}
          className="p-2 rounded-lg transition-colors hover:bg-white/5"
          style={{ color: '#64748b' }}
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Summary Cards */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : resumo && (
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {[
            { label: 'Total 12 meses', value: `R$ ${fmtMoney(resumo.total_12m)}`, color: '#00E676' },
            { label: 'Projeção Mensal', value: `R$ ${fmtMoney(resumo.projecao_mensal)}`, color: '#448AFF' },
            { label: 'Yield on Cost', value: `${resumo.yield_on_cost?.toFixed(2)}%`, color: '#FFD740' },
            { label: 'DY Médio', value: `${resumo.dy_medio?.toFixed(2)}%`, color: '#AA00FF' },
          ].map(card => (
            <div key={card.label} className="apex-card p-4">
              <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>{card.label}</p>
              <p className="text-xl font-bold font-data" style={{ color: card.color }}>{card.value}</p>
            </div>
          ))}
        </motion.div>
      )}

      {/* Pagadores info */}
      {!loading && resumo && (
        <div className="flex items-center gap-4 text-xs" style={{ color: '#64748b' }}>
          <span>{resumo.ativos_pagadores} de {resumo.total_ativos} ativos pagam dividendos</span>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all flex-1 justify-center"
            style={{
              background: tab === t.key ? 'rgba(68,138,255,0.15)' : 'transparent',
              color: tab === t.key ? '#448AFF' : '#64748b',
              border: tab === t.key ? '1px solid rgba(68,138,255,0.3)' : '1px solid transparent',
            }}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        {tab === 'ativos' && (
          <motion.div key="ativos" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-32 rounded-xl" />)}
              </div>
            ) : ativos?.setores?.length > 0 ? (
              <div className="space-y-3">
                {ativos.setores.map((setor: any) => (
                  <div key={setor.setor} className="apex-card overflow-hidden">
                    <button
                      onClick={() => toggleSector(setor.setor)}
                      className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(68,138,255,0.15)' }}>
                          <PieChart size={14} style={{ color: '#448AFF' }} />
                        </div>
                        <div className="text-left">
                          <p className="text-sm font-medium" style={{ color: '#e2e8f0' }}>{setor.setor}</p>
                          <p className="text-xs" style={{ color: '#475569' }}>{setor.quantidade_ativos} ativo{setor.quantidade_ativos > 1 ? 's' : ''}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <p className="text-sm font-bold font-data" style={{ color: '#00E676' }}>R$ {fmtMoney(setor.total_12m)}</p>
                        {expandedSectors[setor.setor] ? <ChevronUp size={16} style={{ color: '#475569' }} /> : <ChevronDown size={16} style={{ color: '#475569' }} />}
                      </div>
                    </button>

                    <AnimatePresence>
                      {expandedSectors[setor.setor] && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          style={{ overflow: 'hidden' }}
                        >
                          <div className="px-4 pb-4">
                            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid #1e293b' }}>
                              <table className="w-full text-xs">
                                <thead>
                                  <tr style={{ background: 'rgba(15,23,42,0.8)' }}>
                                    <th className="text-left p-2 font-mono uppercase" style={{ color: '#475569' }}>Ticker</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>Qtd</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>DY 12m</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>Total 12m</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>Freq.</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>Últ. Ex-Date</th>
                                    <th className="text-right p-2 font-mono uppercase" style={{ color: '#475569' }}>Últ. Pgto</th>
                                    <th className="text-center p-2 font-mono uppercase" style={{ color: '#475569' }}>Dados</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {setor.ativos.map((ativo: any) => (
                                    <tr key={ativo.ticker} className="border-t" style={{ borderColor: '#1e293b' }}>
                                      <td className="p-2">
                                        <span className="font-bold" style={{ color: '#e2e8f0' }}>{ativo.ticker}</span>
                                        <span className="ml-1 text-[10px] px-1 py-0.5 rounded" style={{
                                          background: ativo.tipo === 'FII' ? 'rgba(170,0,255,0.15)' : 'rgba(68,138,255,0.15)',
                                          color: ativo.tipo === 'FII' ? '#AA00FF' : '#448AFF',
                                        }}>{ativo.tipo}</span>
                                        {ativo.ultimo_tipo && ativo.ultimo_tipo !== 'DIVIDENDO' && (
                                          <span className="ml-1 text-[10px] px-1 py-0.5 rounded" style={{ background: 'rgba(255,215,64,0.15)', color: '#FFD740' }}>{ativo.ultimo_tipo}</span>
                                        )}
                                      </td>
                                      <td className="p-2 text-right font-data" style={{ color: '#94a3b8' }}>{ativo.quantidade}</td>
                                      <td className="p-2 text-right font-data font-bold" style={{ color: ativo.dy_12m >= 8 ? '#00E676' : ativo.dy_12m >= 5 ? '#FFD740' : '#94a3b8' }}>
                                        {ativo.dy_12m.toFixed(2)}%
                                      </td>
                                      <td className="p-2 text-right font-data" style={{ color: '#e2e8f0' }}>R$ {fmtMoney(ativo.total_12m_reais)}</td>
                                      <td className="p-2 text-right" style={{ color: '#64748b' }}>{ativo.frequencia}</td>
                                      <td className="p-2 text-right font-mono" style={{ color: '#94a3b8' }}>{ativo.ultimo_ex_date || '—'}</td>
                                      <td className="p-2 text-right font-mono" style={{ color: '#94a3b8' }}>{ativo.ultimo_pagamento || '—'}</td>
                                      <td className="p-2 text-center">
                                        {ativo.confianca >= 80 ? (
                                          <CheckCircle2 size={13} style={{ color: '#00E676' }} className="inline" />
                                        ) : ativo.confianca >= 40 ? (
                                          <AlertCircle size={13} style={{ color: '#FFD740' }} className="inline" />
                                        ) : (
                                          <AlertCircle size={13} style={{ color: '#FF5252' }} className="inline" />
                                        )}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))}
              </div>
            ) : (
              <div className="apex-card p-8 text-center">
                <p style={{ color: '#475569' }}>Nenhum ativo pagador de dividendos encontrado.</p>
              </div>
            )}
          </motion.div>
        )}

        {tab === 'historico' && (
          <motion.div key="historico" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 rounded-xl" />)}
              </div>
            ) : (
              <div className="space-y-6">
                {/* Year Summary */}
                {historico?.anos?.length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {historico.anos.slice(0, 4).map((ano: any) => (
                      <div key={ano.ano} className="apex-card p-4">
                        <p className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: '#475569' }}>{ano.ano}</p>
                        <p className="text-lg font-bold font-data" style={{ color: '#00E676' }}>R$ {fmt(ano.total)}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Monthly Breakdown */}
                {historico?.meses?.length > 0 ? (
                  <div className="space-y-2">
                    {historico.meses.map((mes: any) => {
                      const [ano, m] = mes.mes.split('-')
                      const meses_nomes = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
                      const label = `${meses_nomes[parseInt(m) - 1]} ${ano}`

                      return (
                        <div key={mes.mes} className="apex-card overflow-hidden">
                          <button
                            onClick={() => toggleMonth(mes.mes)}
                            className="w-full flex items-center justify-between p-3 hover:bg-white/[0.02] transition-colors"
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.1)' }}>
                                <Calendar size={12} style={{ color: '#00E676' }} />
                              </div>
                              <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>{label}</span>
                              <span className="text-xs" style={{ color: '#475569' }}>{mes.detalhes.length} pagamento{mes.detalhes.length > 1 ? 's' : ''}</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-sm font-bold font-data" style={{ color: '#00E676' }}>R$ {fmtMoney(mes.total)}</span>
                              {expandedMonths[mes.mes] ? <ChevronUp size={14} style={{ color: '#475569' }} /> : <ChevronDown size={14} style={{ color: '#475569' }} />}
                            </div>
                          </button>

                          <AnimatePresence>
                            {expandedMonths[mes.mes] && (
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                style={{ overflow: 'hidden' }}
                              >
                                <div className="px-3 pb-3 space-y-1">
                                  {mes.detalhes.map((d: any, i: number) => (
                                    <div key={i} className="flex items-center justify-between rounded-lg p-2 text-xs" style={{ background: 'rgba(15,23,42,0.6)' }}>
                                      <div className="flex items-center gap-2">
                                        <span className="font-bold" style={{ color: '#e2e8f0' }}>{d.ticker}</span>
                                        <span className="px-1 py-0.5 rounded text-[10px]" style={{
                                          background: d.tipo_provento === 'JCP' ? 'rgba(255,215,64,0.15)' : 'rgba(0,230,118,0.1)',
                                          color: d.tipo_provento === 'JCP' ? '#FFD740' : '#00E676',
                                        }}>{d.tipo_provento}</span>
                                        {d.source === 'merged' && (
                                          <span title="Dado cruzado BRAPI + yFinance"><CheckCircle2 size={10} style={{ color: '#00E676' }} /></span>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-4">
                                        {d.ex_date && (
                                          <span style={{ color: '#64748b' }}>ex: {d.ex_date}</span>
                                        )}
                                        {d.payment_date && (
                                          <span style={{ color: '#475569' }}>pgto: {d.payment_date}</span>
                                        )}
                                        <span style={{ color: '#64748b' }}>{d.quantidade} × R$ {d.valor_por_cota.toFixed(4)}</span>
                                        <span className="font-bold font-data" style={{ color: '#e2e8f0' }}>R$ {fmtMoney(d.valor_total)}</span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="apex-card p-8 text-center">
                    <p style={{ color: '#475569' }}>Nenhum histórico de dividendos disponível.</p>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {tab === 'calendario' && (
          <motion.div key="calendario" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
              </div>
            ) : calendario?.proximos?.length > 0 ? (
              <div className="space-y-3">
                {/* 30-day projection */}
                <div className="apex-card p-4 flex items-center justify-between">
                  <span className="text-sm" style={{ color: '#94a3b8' }}>Projeção próximos 30 dias</span>
                  <span className="text-lg font-bold font-data" style={{ color: '#00E676' }}>R$ {fmtMoney(calendario.total_projetado_30d)}</span>
                </div>

                {/* Timeline */}
                <div className="space-y-2">
                  {calendario.proximos.map((item: any, i: number) => {
                    const urgency = item.dias_restantes <= 7 ? '#FF5252' : item.dias_restantes <= 30 ? '#FFD740' : '#448AFF'
                    return (
                      <div key={i} className="apex-card p-4 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-1 h-12 rounded-full" style={{ background: urgency }} />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold" style={{ color: '#e2e8f0' }}>{item.ticker}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
                                background: item.tipo === 'FII' ? 'rgba(170,0,255,0.15)' : 'rgba(68,138,255,0.15)',
                                color: item.tipo === 'FII' ? '#AA00FF' : '#448AFF',
                              }}>{item.tipo}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(100,116,139,0.15)', color: '#64748b' }}>{item.frequencia}</span>
                              {item.ultimo_tipo && item.ultimo_tipo !== 'DIVIDENDO' && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,215,64,0.15)', color: '#FFD740' }}>{item.ultimo_tipo}</span>
                              )}
                              {item.confianca === 'alta' ? (
                                <span title="Dados cruzados"><CheckCircle2 size={11} style={{ color: '#00E676' }} /></span>
                              ) : (
                                <span title="Estimativa"><AlertCircle size={11} style={{ color: '#FFD740' }} /></span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 mt-1 text-xs">
                              <span style={{ color: '#64748b' }}>Ex: <span className="font-mono" style={{ color: '#94a3b8' }}>{item.data_ex_estimada}</span></span>
                              <span style={{ color: '#64748b' }}>Pgto: <span className="font-mono" style={{ color: '#94a3b8' }}>{item.data_pagamento_estimada}</span></span>
                              <span style={{ color: '#475569' }}>DY {item.dy_12m.toFixed(2)}%</span>
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold font-data" style={{ color: '#e2e8f0' }}>R$ {fmtMoney(item.valor_estimado)}</p>
                          <p className="text-xs" style={{ color: urgency }}>
                            {item.dias_restantes === 0 ? 'Hoje' : item.dias_restantes === 1 ? 'Amanhã' : `${item.dias_restantes} dias`}
                          </p>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <div className="apex-card p-8 text-center">
                <p style={{ color: '#475569' }}>Nenhum dividendo projetado.</p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
