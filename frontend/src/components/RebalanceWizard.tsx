/**
 * Wizard pré-rebalanceamento — 4 passos para configurar estratégia + alocação.
 * Infere alocação da carteira existente, coleta objetivo + risco + horizonte,
 * permite ajuste com sliders, salva no backend e navega para o rebalanceamento.
 */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, ChevronRight, ChevronLeft, Target, Shield, Clock,
  SlidersHorizontal, Loader2, TrendingUp, Wallet, Landmark, Zap,
  MessageSquare, Brain, AlertTriangle, Settings,
} from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import { useCostEstimates } from '@/hooks/useCostEstimates'

// ─── Types ──────────────────────────────────────────────────────────────────

type Step = 'objetivo' | 'risco' | 'horizonte' | 'descricao' | 'alocacao'

interface Position {
  modulo: string
  valor_atual: number
}

interface RebalanceWizardProps {
  onClose: () => void
  positions: Position[]
  portfolioId: number
}

// ─── Presets de alocação ────────────────────────────────────────────────────

const PRESETS: Record<string, Record<string, number>> = {
  CORE: { etfs: 30, fiis: 15, renda_fixa: 15, momentum: 15, wheel: 5, alpha: 5, dividendos: 5, caixa: 10 },
  ALPHA: { etfs: 20, fiis: 10, renda_fixa: 5, momentum: 25, wheel: 10, alpha: 20, dividendos: 0, caixa: 10 },
  RENDA: { etfs: 10, fiis: 30, renda_fixa: 25, momentum: 0, wheel: 5, alpha: 0, dividendos: 25, caixa: 5 },
}

const MODULE_LABELS: Record<string, string> = {
  etfs: 'ETFs', fiis: 'FIIs', renda_fixa: 'Renda Fixa', momentum: 'Momentum',
  wheel: 'Wheel', alpha: 'Alpha', dividendos: 'Dividendos', caixa: 'Caixa',
}

const MODULE_COLORS: Record<string, string> = {
  etfs: '#00E676', fiis: '#00BFA5', renda_fixa: '#FFD740', momentum: '#448AFF',
  wheel: '#FF9800', alpha: '#E040FB', dividendos: '#1DE9B6', caixa: '#475569',
}

const MODULE_ORDER = ['etfs', 'fiis', 'renda_fixa', 'momentum', 'wheel', 'alpha', 'dividendos', 'caixa']

// ─── Score mapping ──────────────────────────────────────────────────────────

function calcScore(risco: string, horizonte: string): number {
  const riscoMap: Record<string, number> = {
    conservador: 2, moderado: 5, agressivo: 8, muito_agressivo: 11,
  }
  const horizMap: Record<string, number> = {
    ate_2anos: 0, '2_5anos': 1, '5_10anos': 2, mais_10anos: 4,
  }
  return Math.min(15, (riscoMap[risco] ?? 5) + (horizMap[horizonte] ?? 1))
}

function mapEstrategia(objetivo: string, score: number): string {
  if (objetivo === 'renda_passiva') return 'RENDA'
  if (score >= 11) return 'ALPHA'
  return 'CORE'
}

// ─── Infer allocation from current positions ────────────────────────────────

function inferirAlocacao(positions: Position[]): Record<string, number> {
  const totais: Record<string, number> = {}
  let soma = 0
  for (const p of positions) {
    const mod = p.modulo || 'caixa'
    const key = mod === 'teses' ? 'caixa' : mod
    totais[key] = (totais[key] || 0) + (p.valor_atual || 0)
    soma += (p.valor_atual || 0)
  }
  if (soma === 0) return { ...PRESETS.CORE }

  const result: Record<string, number> = {}
  for (const mod of MODULE_ORDER) {
    result[mod] = Math.round(((totais[mod] || 0) / soma) * 100)
  }
  // Ajustar para somar 100
  const diff = 100 - Object.values(result).reduce((a, b) => a + b, 0)
  result.caixa = Math.max(0, (result.caixa || 0) + diff)
  return result
}

// ─── Option button ──────────────────────────────────────────────────────────

function OptionBtn({ selected, onClick, icon, title, desc }: {
  selected: boolean; onClick: () => void; icon: React.ReactNode; title: string; desc: string
}) {
  return (
    <button onClick={onClick} className="w-full text-left px-4 py-4 rounded-xl transition-all duration-200 flex items-start gap-3"
      style={{
        background: selected ? 'rgba(0,230,118,0.08)' : 'rgba(15,23,42,0.6)',
        border: selected ? '1px solid rgba(0,230,118,0.4)' : '1px solid #1e293b',
      }}
    >
      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: selected ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.04)', color: selected ? '#00E676' : '#64748b' }}>
        {icon}
      </div>
      <div>
        <p className="text-sm font-medium" style={{ color: selected ? '#00E676' : '#e2e8f0' }}>{title}</p>
        <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{desc}</p>
      </div>
    </button>
  )
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function RebalanceWizard({ onClose, positions, portfolioId }: RebalanceWizardProps) {
  const navigate = useNavigate()
  const { userId } = useStore()
  const { format: fmtCost } = useCostEstimates()
  const costLabel = fmtCost('sugerir_alocacao')
  const rebalCostLabel = fmtCost('sugerir_portfolio')

  const [step, setStep] = useState<Step>('objetivo')
  const [objetivo, setObjetivo] = useState('')
  const [risco, setRisco] = useState('')
  const [horizonte, setHorizonte] = useState('')
  const [descricao, setDescricao] = useState('')
  const [alocacao, setAlocacao] = useState<Record<string, number>>(() => inferirAlocacao(positions))
  const [saving, setSaving] = useState(false)
  const [loadingAI, setLoadingAI] = useState(false)
  const [aiFailed, setAiFailed] = useState(false)
  const [racional, setRacional] = useState('')
  const [aiSuggestion, setAiSuggestion] = useState<Record<string, number> | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const steps: Step[] = ['objetivo', 'risco', 'horizonte', 'descricao', 'alocacao']
  const stepIdx = steps.indexOf(step)

  const score = useMemo(() => calcScore(risco, horizonte), [risco, horizonte])
  const estrategia = useMemo(() => mapEstrategia(objetivo, score), [objetivo, score])

  // When objetivo/risco/horizonte change, set fallback preset (AI will override when moving to alocação)
  useEffect(() => {
    if (objetivo && risco && horizonte && !racional) {
      const est = mapEstrategia(objetivo, calcScore(risco, horizonte))
      setAlocacao({ ...PRESETS[est] })
    }
  }, [objetivo, risco, horizonte])
  // eslint-disable-line react-hooks/exhaustive-deps

  const total = useMemo(() => MODULE_ORDER.reduce((s, m) => s + (alocacao[m] || 0), 0), [alocacao])

  const canProceed = () => {
    if (step === 'objetivo') return !!objetivo
    if (step === 'risco') return !!risco
    if (step === 'horizonte') return !!horizonte
    if (step === 'descricao') return true  // optional, always can proceed
    if (step === 'alocacao') return total >= 99 && total <= 101
    return false
  }

  const handleSlider = (mod: string, val: number) => {
    setAlocacao(prev => ({ ...prev, [mod]: val }))
  }

  const handlePreset = (preset: string) => {
    setAlocacao({ ...PRESETS[preset] })
  }

  const handleConfirm = async () => {
    setSaving(true)
    setErro(null)
    try {
      const headers: Record<string, string> = {}
      if (userId) headers['x-user-id'] = String(userId)
      await api.patch('/portfolio/configurar-rebalance', {
        estrategia,
        score_perfil: score,
        objetivo,
        horizonte,
        descricao: descricao.trim() || null,
        alocacao,
      }, { headers })

      // Navigate to rebalance page
      onClose()
      navigate('/sugestoes-alocacao', {
        state: { portfolioId, modo: 'rebalanceamento' },
      })
    } catch (e: any) {
      setErro(e?.response?.data?.detail || 'Erro ao salvar configuração')
    } finally {
      setSaving(false)
    }
  }

  const fetchAISuggestion = async () => {
    setLoadingAI(true)
    setAiFailed(false)
    setErro(null)
    try {
      const headers: Record<string, string> = {}
      if (userId) headers['x-user-id'] = String(userId)
      const { data } = await api.post('/portfolio/sugerir-alocacao', {
        objetivo,
        horizonte,
        risco,
        descricao: descricao.trim() || null,
        posicoes: positions.map(p => ({ modulo: p.modulo, valor_atual: p.valor_atual })),
      }, { headers })
      if (data.alocacao) {
        setAlocacao(data.alocacao)
        setAiSuggestion({ ...data.alocacao })
      }
      if (data.racional) setRacional(data.racional)
      setLoadingAI(false)
      setStep('alocacao')
    } catch (e: any) {
      setLoadingAI(false)
      setAiFailed(true)
    }
  }

  const handleUsePreset = () => {
    setAiFailed(false)
    setStep('alocacao')
  }

  const handleGoToSettings = () => {
    onClose()
    navigate('/configuracoes')
  }

  const next = () => {
    if (step === 'alocacao') {
      handleConfirm()
      return
    }
    // When moving from descrição to alocação, call AI first
    if (step === 'descricao') {
      fetchAISuggestion()
      return
    }
    setStep(steps[stepIdx + 1])
  }
  const prev = () => {
    if (stepIdx > 0) setStep(steps[stepIdx - 1])
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="w-full rounded-2xl shadow-2xl overflow-hidden flex flex-col"
          style={{ maxWidth: 540, maxHeight: '90vh', background: '#0d1117', border: '1px solid #1e293b' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#1e293b' }}>
            <div>
              <p className="font-bold text-white text-base">Configurar Rebalanceamento</p>
              <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                Passo {stepIdx + 1} de {steps.length}
              </p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg transition-colors" style={{ color: '#64748b' }}>
              <X size={18} />
            </button>
          </div>

          {/* Progress bar */}
          <div className="h-1 w-full" style={{ background: '#1e293b' }}>
            <motion.div
              className="h-full"
              style={{ background: '#00E676' }}
              animate={{ width: `${((stepIdx + 1) / steps.length) * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {/* AI loading overlay */}
            {loadingAI && (
              <motion.div
                key="loading-ai"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col items-center justify-center py-16 gap-4"
              >
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                >
                  <Brain size={36} style={{ color: '#00E676' }} />
                </motion.div>
                <p className="text-sm font-semibold text-white">Analisando cenário macro e seu perfil…</p>
                <p className="text-xs text-center max-w-xs" style={{ color: '#64748b' }}>
                  A IA está avaliando suas posições, o contexto macroeconômico e suas expectativas para sugerir a alocação ideal.
                </p>
                <motion.div
                  className="h-0.5 rounded-full mt-2"
                  style={{ background: '#00E676', width: 0 }}
                  animate={{ width: '200px' }}
                  transition={{ duration: 8, ease: 'linear' }}
                />
              </motion.div>
            )}

            {/* AI failed overlay */}
            {aiFailed && !loadingAI && (
              <motion.div
                key="ai-failed"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col items-center justify-center py-12 gap-4"
              >
                <div className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: 'rgba(255,82,82,0.1)' }}>
                  <AlertTriangle size={28} style={{ color: '#FF5252' }} />
                </div>
                <p className="text-sm font-semibold text-white">A IA não conseguiu analisar</p>
                <p className="text-xs text-center max-w-xs leading-relaxed" style={{ color: '#64748b' }}>
                  Pode ser que a chave de API esteja inválida, sem créditos, ou o serviço esteja fora do ar.
                  Você pode continuar com a alocação padrão ou ir às configurações para ajustar a IA.
                </p>
                <div className="flex gap-3 mt-2">
                  <button
                    onClick={handleUsePreset}
                    className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all"
                    style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
                  >
                    <SlidersHorizontal size={14} />
                    Usar preset {estrategia}
                  </button>
                  <button
                    onClick={handleGoToSettings}
                    className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all"
                    style={{ background: 'rgba(255,255,255,0.04)', color: '#94a3b8', border: '1px solid #1e293b' }}
                  >
                    <Settings size={14} />
                    Configurar IA
                  </button>
                </div>
              </motion.div>
            )}

            {!loadingAI && !aiFailed && (
            <AnimatePresence mode="wait">
              {/* ─── Step 1: Objetivo ─── */}
              {step === 'objetivo' && (
                <motion.div key="objetivo" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.2 }}>
                  <div className="flex items-center gap-2 mb-4">
                    <Target size={18} style={{ color: '#00E676' }} />
                    <p className="text-sm font-semibold text-white">Qual o principal objetivo desta carteira?</p>
                  </div>
                  <div className="space-y-2.5">
                    <OptionBtn selected={objetivo === 'crescimento'} onClick={() => setObjetivo('crescimento')}
                      icon={<TrendingUp size={16} />} title="Crescimento de Capital"
                      desc="Maximizar valorização no longo prazo, aceito mais volatilidade" />
                    <OptionBtn selected={objetivo === 'renda_passiva'} onClick={() => setObjetivo('renda_passiva')}
                      icon={<Wallet size={16} />} title="Renda Passiva"
                      desc="Geração de renda recorrente via dividendos, FIIs e juros" />
                    <OptionBtn selected={objetivo === 'preservacao'} onClick={() => setObjetivo('preservacao')}
                      icon={<Landmark size={16} />} title="Preservação de Patrimônio"
                      desc="Proteger contra inflação com risco mínimo" />
                    <OptionBtn selected={objetivo === 'equilibrio'} onClick={() => setObjetivo('equilibrio')}
                      icon={<SlidersHorizontal size={16} />} title="Equilíbrio"
                      desc="Mix de crescimento e renda, risco moderado" />
                  </div>
                </motion.div>
              )}

              {/* ─── Step 2: Risco ─── */}
              {step === 'risco' && (
                <motion.div key="risco" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.2 }}>
                  <div className="flex items-center gap-2 mb-4">
                    <Shield size={18} style={{ color: '#00E676' }} />
                    <p className="text-sm font-semibold text-white">Como reage a quedas na carteira?</p>
                  </div>
                  <div className="space-y-2.5">
                    <OptionBtn selected={risco === 'conservador'} onClick={() => setRisco('conservador')}
                      icon={<Shield size={16} />} title="Conservador"
                      desc="Queda de 10% já me incomoda. Prefiro segurança." />
                    <OptionBtn selected={risco === 'moderado'} onClick={() => setRisco('moderado')}
                      icon={<SlidersHorizontal size={16} />} title="Moderado"
                      desc="Aguento -15% a -20% se fizer sentido no longo prazo." />
                    <OptionBtn selected={risco === 'agressivo'} onClick={() => setRisco('agressivo')}
                      icon={<TrendingUp size={16} />} title="Agressivo"
                      desc="Aceito -30% ou mais se a tese estiver intacta." />
                    <OptionBtn selected={risco === 'muito_agressivo'} onClick={() => setRisco('muito_agressivo')}
                      icon={<Zap size={16} />} title="Muito Agressivo"
                      desc="Queda é oportunidade de compra. Foco em retorno máximo." />
                  </div>
                </motion.div>
              )}

              {/* ─── Step 3: Horizonte ─── */}
              {step === 'horizonte' && (
                <motion.div key="horizonte" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.2 }}>
                  <div className="flex items-center gap-2 mb-4">
                    <Clock size={18} style={{ color: '#00E676' }} />
                    <p className="text-sm font-semibold text-white">Horizonte de investimento?</p>
                  </div>
                  <div className="space-y-2.5">
                    <OptionBtn selected={horizonte === 'ate_2anos'} onClick={() => setHorizonte('ate_2anos')}
                      icon={<Clock size={16} />} title="Até 2 anos"
                      desc="Curto prazo, preciso de liquidez em breve" />
                    <OptionBtn selected={horizonte === '2_5anos'} onClick={() => setHorizonte('2_5anos')}
                      icon={<Clock size={16} />} title="2 a 5 anos"
                      desc="Médio prazo, aceito alguma oscilação" />
                    <OptionBtn selected={horizonte === '5_10anos'} onClick={() => setHorizonte('5_10anos')}
                      icon={<Clock size={16} />} title="5 a 10 anos"
                      desc="Longo prazo, foco em crescimento composto" />
                    <OptionBtn selected={horizonte === 'mais_10anos'} onClick={() => setHorizonte('mais_10anos')}
                      icon={<Clock size={16} />} title="10+ anos"
                      desc="Muito longo prazo, posso maximizar risco/retorno" />
                  </div>
                </motion.div>
              )}

              {/* ─── Step 4: Descrição livre ─── */}
              {step === 'descricao' && (
                <motion.div key="descricao" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.2 }}>
                  <div className="flex items-center gap-2 mb-2">
                    <MessageSquare size={18} style={{ color: '#00E676' }} />
                    <p className="text-sm font-semibold text-white">Conte mais sobre suas expectativas</p>
                  </div>
                  <p className="text-xs mb-4" style={{ color: '#64748b' }}>
                    Opcional, mas quanto mais contexto, melhor. Descreva metas, restrições, setores que gosta,
                    ativos que quer manter, preocupações, ou qualquer coisa que um gestor profissional deveria saber.
                  </p>
                  <textarea
                    value={descricao}
                    onChange={(e) => setDescricao(e.target.value)}
                    maxLength={2000}
                    rows={6}
                    placeholder={"Ex: Quero maximizar crescimento nos próximos 5 anos para depois viver de renda. Gosto de WEGE3 e não quero vender. Prefiro evitar estatais. Tenho aporte mensal de R$5.000..."}
                    className="w-full rounded-xl px-4 py-3 text-sm resize-none outline-none transition-all"
                    style={{
                      background: 'rgba(15,23,42,0.6)',
                      border: '1px solid #1e293b',
                      color: '#e2e8f0',
                      minHeight: 140,
                    }}
                    onFocus={(e) => e.currentTarget.style.borderColor = 'rgba(0,230,118,0.4)'}
                    onBlur={(e) => e.currentTarget.style.borderColor = '#1e293b'}
                  />
                  <div className="flex justify-end mt-2">
                    <span className="text-xs tabular-nums" style={{ color: '#475569' }}>
                      {descricao.length}/2000
                    </span>
                  </div>
                </motion.div>
              )}

              {/* ─── Step 5: Alocação ─── */}
              {step === 'alocacao' && (
                <motion.div key="alocacao" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.2 }}>
                  <div className="flex items-center gap-2 mb-2">
                    <SlidersHorizontal size={18} style={{ color: '#00E676' }} />
                    <p className="text-sm font-semibold text-white">Alocação Alvo por Módulo</p>
                  </div>
                  {racional ? (
                    <div className="mb-4 px-3 py-2.5 rounded-xl" style={{ background: 'rgba(0,230,118,0.04)', border: '1px solid rgba(0,230,118,0.15)' }}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <Brain size={12} style={{ color: '#00E676' }} />
                        <span className="text-xs font-semibold" style={{ color: '#00E676' }}>Recomendação da IA</span>
                      </div>
                      <p className="text-xs leading-relaxed" style={{ color: '#94a3b8' }}>{racional}</p>
                    </div>
                  ) : (
                    <p className="text-xs mb-4" style={{ color: '#64748b' }}>
                      Perfil: <strong style={{ color: '#00E676' }}>{estrategia}</strong> (score {score}/15). Ajuste como preferir.
                    </p>
                  )}
                  <p className="text-xs mb-3" style={{ color: '#475569' }}>Ajuste livremente — você tem a palavra final.</p>

                  {/* Preset buttons */}
                  <div className="flex gap-2 mb-4 flex-wrap">
                    {aiSuggestion && (
                      <button onClick={() => setAlocacao({ ...aiSuggestion })}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1"
                        style={MODULE_ORDER.every(m => alocacao[m] === aiSuggestion[m]) ? {
                          background: 'rgba(168,85,247,0.15)', color: '#a855f7', border: '1px solid rgba(168,85,247,0.3)',
                        } : {
                          background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid #1e293b',
                        }}
                      >
                        <Brain size={11} /> IA
                        {costLabel && <span style={{ color: '#7c3aed', fontSize: 9, opacity: 0.7 }}>{costLabel}</span>}
                      </button>
                    )}
                    {(['CORE', 'ALPHA', 'RENDA'] as const).map(p => {
                      const isActive = MODULE_ORDER.every(m => alocacao[m] === PRESETS[p][m])
                      return (
                        <button key={p} onClick={() => handlePreset(p)}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                          style={isActive ? {
                            background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)',
                          } : {
                            background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid #1e293b',
                          }}
                        >
                          {p}
                        </button>
                      )
                    })}
                    <button onClick={() => setAlocacao(inferirAlocacao(positions))}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                      style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid #1e293b' }}
                    >
                      Inferir da Carteira
                    </button>
                  </div>

                  {/* Sliders */}
                  <div className="space-y-3">
                    {MODULE_ORDER.map(mod => (
                      <div key={mod}>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ background: MODULE_COLORS[mod] }} />
                            <span className="text-xs font-medium" style={{ color: '#e2e8f0' }}>{MODULE_LABELS[mod]}</span>
                          </div>
                          <span className="text-xs font-bold tabular-nums" style={{ color: MODULE_COLORS[mod] }}>
                            {alocacao[mod] || 0}%
                          </span>
                        </div>
                        <input
                          type="range"
                          min={0} max={100} step={5}
                          value={alocacao[mod] || 0}
                          onChange={(e) => handleSlider(mod, Number(e.target.value))}
                          className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
                          style={{
                            background: `linear-gradient(to right, ${MODULE_COLORS[mod]} 0%, ${MODULE_COLORS[mod]} ${alocacao[mod] || 0}%, #1e293b ${alocacao[mod] || 0}%, #1e293b 100%)`,
                            accentColor: MODULE_COLORS[mod],
                          }}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Total indicator */}
                  <div className="mt-4 flex items-center justify-between px-3 py-2.5 rounded-xl" style={{
                    background: total === 100 ? 'rgba(0,230,118,0.06)' : 'rgba(255,82,82,0.06)',
                    border: total === 100 ? '1px solid rgba(0,230,118,0.2)' : '1px solid rgba(255,82,82,0.2)',
                  }}>
                    <span className="text-xs font-medium" style={{ color: '#94a3b8' }}>Total da Alocação</span>
                    <span className="text-sm font-bold tabular-nums" style={{ color: total === 100 ? '#00E676' : '#FF5252' }}>
                      {total}%
                    </span>
                  </div>

                  {erro && (
                    <p className="text-xs mt-3 text-center" style={{ color: '#FF5252' }}>{erro}</p>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
            )}
          </div>

          {/* Footer — hide during loading/failed states */}
          {!loadingAI && !aiFailed && (
          <div className="flex items-center justify-between px-6 py-4 border-t" style={{ borderColor: '#1e293b' }}>
            <button
              onClick={stepIdx === 0 ? onClose : prev}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm transition-all"
              style={{ color: '#64748b' }}
            >
              <ChevronLeft size={16} />
              {stepIdx === 0 ? 'Cancelar' : 'Voltar'}
            </button>

            <button
              onClick={next}
              disabled={!canProceed() || saving || loadingAI}
              className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
              style={{
                background: canProceed() && !saving && !loadingAI ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.04)',
                color: canProceed() && !saving && !loadingAI ? '#00E676' : '#334155',
                border: canProceed() && !saving && !loadingAI ? '1px solid rgba(0,230,118,0.3)' : '1px solid #1e293b',
              }}
            >
              {saving ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Salvando…
                </>
              ) : step === 'alocacao' ? (
                <>
                  Rebalancear
                  {rebalCostLabel && <span style={{ fontSize: 10, opacity: 0.6 }}>{rebalCostLabel}</span>}
                  <ChevronRight size={16} />
                </>
              ) : (
                <>
                  Próximo
                  <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
          )}
        </motion.div>
      </div>
    </>
  )
}
