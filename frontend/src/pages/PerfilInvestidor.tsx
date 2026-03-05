/**
 * PerfilInvestidor — Questionário completo de perfil do investidor.
 *
 * Acessado de duas formas:
 *  1. Onboarding "do zero"  → state: { userId, name, tipo, fromOnboarding }
 *  2. Positions (ao clicar Rebalancear sem perfil) → state: { returnTo }
 *
 * Fluxo: patrimônio → objetivo → volatilidade → liquidez → renda → experiência
 *       → tempo → objetivo principal → horizonte → aporte → FINALIZA
 *
 * Ao finalizar chama POST /onboarding/finalize e:
 *  - Se veio do onboarding → navega pra /sugestoes-alocacao com modo 'inicial'
 *  - Se veio de Positions  → navega de volta pra /positions (rebalancear)
 */
import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, ChevronLeft, Check, BrainCircuit } from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

// ─── Types ──────────────────────────────────────────────────────────────────

type Step =
  | 'patrimony'
  | 'goal'
  | 'volatility'
  | 'liquidity'
  | 'income'
  | 'experience'
  | 'time'
  | 'objective'
  | 'horizon'
  | 'aporte'

interface FormState {
  patrimony: string
  goalType: string
  goalValue: string
  goalDescription: string
  volatility: string
  liquidity: string
  income: string
  experience: string[]
  timeAvailable: string
  objective: string
  horizon: string
  aporteMensal: string
  fazAporte: string
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function useTypewriter(text: string, speed = 18) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    setDisplayed('')
    setDone(false)
    if (!text) return
    let i = 0
    const timer = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) { clearInterval(timer); setDone(true) }
    }, speed)
    return () => clearInterval(timer)
  }, [text, speed])

  return { displayed, done }
}

function AIMessage({ text, typing = false }: { text: string; typing?: boolean }) {
  const { displayed, done } = useTypewriter(typing ? text : '')
  const content = typing ? displayed : text

  return (
    <div className="mb-6">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
          <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
        </div>
        <p className="text-base leading-relaxed pt-1" style={{ color: '#f1f5f9' }}>
          {content}
          {typing && !done && (
            <span className="inline-block w-0.5 h-4 ml-0.5 align-middle animate-pulse" style={{ background: '#00E676' }} />
          )}
        </p>
      </div>
    </div>
  )
}

function OptionButton({
  selected, onClick, children, multi = false,
}: { selected: boolean; onClick: () => void; children: React.ReactNode; multi?: boolean }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center gap-3"
      style={{
        background: selected ? 'rgba(0,230,118,0.08)' : 'rgba(15,23,42,0.6)',
        border: selected ? '1px solid rgba(0,230,118,0.4)' : '1px solid #1e293b',
        color: selected ? '#00E676' : '#94a3b8',
      }}
    >
      <div
        className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 transition-all"
        style={{
          background: selected ? '#00E676' : 'transparent',
          border: selected ? '1px solid #00E676' : '1px solid #1e293b',
          borderRadius: multi ? '4px' : '50%',
        }}
      >
        {selected && <Check size={12} color="#0a0e17" strokeWidth={3} />}
      </div>
      <span style={{ color: selected ? '#f1f5f9' : '#94a3b8' }}>{children}</span>
    </button>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function PerfilInvestidorPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { userId, userName, setUser, setStrategy, setPortfolioAtivo, setPortfolios } = useStore()

  // Dados vindos do onboarding ou da tela de posições
  const locState = (location.state || {}) as {
    userId?: number
    name?: string
    tipo?: string
    fromOnboarding?: boolean
    returnTo?: string
  }

  const effectiveUserId = locState.userId ?? (userId ? parseInt(userId) : null)
  const effectiveName = locState.name ?? userName ?? 'Investidor'
  const tipo = locState.tipo ?? 'real'
  const fromOnboarding = locState.fromOnboarding ?? false
  const returnTo = locState.returnTo

  const stepOrder: Step[] = [
    'patrimony', 'goal', 'volatility', 'liquidity', 'income',
    'experience', 'time', 'objective', 'horizon', 'aporte',
  ]

  const [step, setStep] = useState<Step>('patrimony')
  const [state, setState] = useState<FormState>({
    patrimony: '',
    goalType: '',
    goalValue: '',
    goalDescription: '',
    volatility: '',
    liquidity: '',
    income: '',
    experience: [],
    timeAvailable: '',
    objective: '',
    horizon: '',
    aporteMensal: '',
    fazAporte: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const stepIndex = stepOrder.indexOf(step)
  const progress = ((stepIndex + 1) / stepOrder.length) * 100

  const formatMoney = (value: string) => {
    const digits = value.replace(/\D/g, '')
    if (!digits) return ''
    return 'R$ ' + Number(digits).toLocaleString('pt-BR')
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  const handleBack = () => {
    const prev = stepIndex - 1
    if (prev >= 0) setStep(stepOrder[prev])
  }

  const handleNext = async () => {
    setError('')

    // Patrimony
    if (step === 'patrimony') {
      if (!state.patrimony) return setError('Por favor, informe seu patrimônio.')
      setStep('goal')
      return
    }

    // Goal
    if (step === 'goal') {
      if (!state.goalType) return setError('Selecione uma opção para continuar.')
      if (state.goalType === 'valor' && !state.goalValue.trim()) return setError('Informe o valor que você quer atingir.')
      if (state.goalType === 'percentual' && !state.goalValue.trim()) return setError('Informe o retorno % anual.')
      if (state.goalType === 'renda' && !state.goalValue.trim()) return setError('Informe a renda mensal.')
      if (state.goalType === 'livre' && !state.goalDescription.trim()) return setError('Conte um pouco sobre seu objetivo.')
    }

    // Aporte — final step
    if (step === 'aporte') {
      if (!state.fazAporte) return setError('Selecione uma opção.')
      if (state.fazAporte === 'sim' && !state.aporteMensal) return setError('Informe o valor do aporte mensal.')
      await finalize()
      return
    }

    // Selection steps
    const selectionReqs: Record<string, { field: keyof FormState; msg: string }> = {
      volatility: { field: 'volatility', msg: 'Selecione seu nível de conforto com volatilidade.' },
      liquidity: { field: 'liquidity', msg: 'Selecione sua necessidade de liquidez.' },
      income: { field: 'income', msg: 'Selecione se precisa de renda mensal.' },
      time: { field: 'timeAvailable', msg: 'Selecione quanto tempo dedica aos investimentos.' },
      objective: { field: 'objective', msg: 'Selecione seu objetivo principal.' },
      horizon: { field: 'horizon', msg: 'Selecione o horizonte de investimento.' },
    }
    if (step in selectionReqs) {
      const { field, msg } = selectionReqs[step]
      const val = state[field]
      if (!val || (Array.isArray(val) && val.length === 0)) return setError(msg)
    }
    if (step === 'experience') {
      if (!state.experience.length) return setError('Selecione pelo menos uma opção.')
    }

    // Go to next step
    const next = stepIndex + 1
    if (next < stepOrder.length) setStep(stepOrder[next])
  }

  // ── Finalizar ──────────────────────────────────────────────────────────────

  async function finalize() {
    setLoading(true)
    try {
      const answers = {
        goal_type: state.goalType,
        goal_description: state.goalDescription || null,
        goal_value: parseFloat(state.goalValue) || null,
        volatility: state.volatility,
        liquidity: state.liquidity,
        income: state.income,
        experience: state.experience,
        time_available: state.timeAvailable,
        objective: state.objective,
        horizon: state.horizon,
      }
      const aporteMensal = state.fazAporte === 'sim'
        ? (parseFloat(state.aporteMensal.replace(/\./g, '').replace(',', '.')) || 0)
        : 0

      const res = await api.post('/onboarding/finalize', {
        user_id: effectiveUserId,
        name: effectiveName,
        answers,
        total_patrimony: parseFloat(state.patrimony.replace(/\D/g, '')) || 0,
        aporte_mensal: aporteMensal,
      })

      const { user_id, portfolio_id, strategy_type } = res.data

      // Atualiza store
      setUser(String(user_id), effectiveName)
      setStrategy(strategy_type as 'CORE' | 'ALPHA' | 'RENDA' | 'CUSTOM')

      // Carrega portfolios
      const rl = await api.get('/portfolio/listar')
      setPortfolios(rl.data)
      const ativo = rl.data.find((p: any) => p.id === portfolio_id) ?? rl.data[0]
      if (ativo) setPortfolioAtivo(ativo)

      // Navegação
      if (returnTo === 'rebalanceamento') {
        navigate('/sugestoes-alocacao', {
          state: { portfolioId: portfolio_id, modo: 'rebalanceamento', forceRefresh: true },
        })
      } else if (fromOnboarding) {
        navigate('/sugestoes-alocacao', {
          state: { portfolioId: portfolio_id, modo: 'inicial' },
        })
      } else {
        navigate('/positions')
      }
    } catch {
      setError('Erro ao finalizar perfil. Verifique o backend.')
    }
    setLoading(false)
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  const stepLabels = ['Patrimônio', 'Objetivo', 'Tolerância a risco', 'Horizonte', 'Finalizar']

  return (
    <div className="min-h-screen flex" style={{ background: '#0a0e17' }}>
      {/* Left panel */}
      <div className="hidden lg:flex w-80 flex-col justify-between p-8 border-r" style={{ borderColor: '#1e293b', background: '#0a0e1a' }}>
        <div>
          <div className="flex items-center gap-3 mb-12">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="font-bold text-sm" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <div>
              <h1 className="font-bold" style={{ color: '#f1f5f9' }}>Perfil do Investidor</h1>
              <p className="text-xs font-mono" style={{ color: '#64748b' }}>Questionário de perfil</p>
            </div>
          </div>

          <div className="space-y-6">
            {stepLabels.map((item, i) => {
              const filled = stepIndex >= (i * 2)
              return (
                <div key={i} className="flex items-start gap-3">
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono flex-shrink-0 mt-0.5"
                    style={{
                      background: filled ? 'rgba(0,230,118,0.1)' : 'transparent',
                      border: `1px solid ${filled ? '#00E676' : '#1e293b'}`,
                      color: filled ? '#00E676' : '#64748b',
                    }}
                  >
                    {filled ? <Check size={12} /> : i + 1}
                  </div>
                  <p className="text-sm font-medium" style={{ color: filled ? '#f1f5f9' : '#64748b' }}>{item}</p>
                </div>
              )
            })}
          </div>
        </div>

        <p className="text-xs" style={{ color: '#475569' }}>&copy; 2026 APEX Manager · Confidencial</p>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col">
        {/* Progress bar */}
        <div className="h-0.5 w-full" style={{ background: '#1e293b' }}>
          <div className="h-full transition-all duration-500" style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #00E676, #00BFA5)' }} />
        </div>

        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-xl">
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.3 }}
              >
                {/* ── Patrimony ───────────────────────────────────────── */}
                {step === 'patrimony' && (
                  <div>
                    <AIMessage
                      text={`${effectiveName}, qual é seu patrimônio total disponível para investir? Inclua tudo: ações, fundos, renda fixa, caixa. Esse número é fundamental para calibrar a estratégia.`}
                      typing
                    />
                    <input
                      className="apex-input mb-2"
                      placeholder="R$ 0"
                      value={state.patrimony ? formatMoney(state.patrimony) : ''}
                      onChange={(e) => setState({ ...state, patrimony: e.target.value.replace(/\D/g, '') })}
                      onKeyDown={(e) => e.key === 'Enter' && handleNext()}
                      autoFocus
                    />
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Goal ────────────────────────────────────────────── */}
                {step === 'goal' && (
                  <div>
                    <AIMessage text="Qual é o seu objetivo com esse patrimônio? Isso vai definir qual estratégia faz mais sentido para você." typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'valor', label: 'Quero chegar em um valor específico (R$)' },
                        { value: 'percentual', label: 'Quero um retorno de X% ao ano' },
                        { value: 'renda', label: 'Quero viver de renda passiva (R$/mês)' },
                        { value: 'livre', label: 'Quero explicar do meu jeito' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.goalType === opt.value}
                          onClick={() => setState({ ...state, goalType: opt.value, goalValue: '' })}>
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>

                    {state.goalType === 'valor' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual valor quer atingir?</label>
                        <input className="apex-input" placeholder="Ex: R$ 2.000.000"
                          value={state.goalValue ? 'R$ ' + Number(state.goalValue).toLocaleString('pt-BR') : ''}
                          onChange={(e) => setState({ ...state, goalValue: e.target.value.replace(/\D/g, '') })} autoFocus />
                      </div>
                    )}
                    {state.goalType === 'percentual' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual retorno anual?</label>
                        <div className="relative">
                          <input className="apex-input" placeholder="Ex: 15" type="number" min="1" max="200"
                            value={state.goalValue} onChange={(e) => setState({ ...state, goalValue: e.target.value })} autoFocus />
                          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-mono" style={{ color: '#64748b' }}>% ao ano</span>
                        </div>
                      </div>
                    )}
                    {state.goalType === 'renda' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual renda mensal?</label>
                        <input className="apex-input" placeholder="Ex: R$ 10.000 por mês"
                          value={state.goalValue ? 'R$ ' + Number(state.goalValue).toLocaleString('pt-BR') : ''}
                          onChange={(e) => setState({ ...state, goalValue: e.target.value.replace(/\D/g, '') })} autoFocus />
                      </div>
                    )}
                    {state.goalType === 'livre' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Conta com suas palavras:</label>
                        <textarea className="apex-input resize-none" rows={4}
                          placeholder="Ex: Quero garantir minha aposentadoria em 10 anos..."
                          value={state.goalDescription}
                          onChange={(e) => setState({ ...state, goalDescription: e.target.value })} autoFocus style={{ lineHeight: '1.6' }} />
                      </div>
                    )}
                    {state.goalType && state.goalType !== 'livre' && (
                      <div className="mt-3">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Quer acrescentar algo? (opcional)</label>
                        <textarea className="apex-input resize-none" rows={3}
                          placeholder="Ex: Quero crescimento agressivo nos próximos 5 anos..."
                          value={state.goalDescription}
                          onChange={(e) => setState({ ...state, goalDescription: e.target.value })} style={{ lineHeight: '1.6' }} />
                      </div>
                    )}
                    {error && <p className="text-sm mt-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Volatility ──────────────────────────────────────── */}
                {step === 'volatility' && (
                  <div>
                    <AIMessage text="Cenário real: seu portfólio cai 20% em 3 meses, mas os fundamentos continuam sólidos. O que você faz?" typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'sell_all', label: 'Vendo tudo — não aguentaria ver mais' },
                        { value: 'sell_partial', label: 'Vendo parte para reduzir o nervosismo' },
                        { value: 'hold', label: 'Seguro firme — já esperava volatilidade' },
                        { value: 'buy_more', label: 'Compro mais — queda é oportunidade' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.volatility === opt.value}
                          onClick={() => setState({ ...state, volatility: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Liquidity ───────────────────────────────────────── */}
                {step === 'liquidity' && (
                  <div>
                    <AIMessage text="Nos próximos 12 meses, você precisa sacar algum valor desse portfólio?" typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'none', label: 'Não preciso de nada — capital 100% investido' },
                        { value: 'small', label: 'Talvez até 10% — alguma reserva de emergência' },
                        { value: 'medium', label: 'Entre 10% e 30% — tenho despesas planejadas' },
                        { value: 'large', label: 'Mais de 30% — necessidade real de liquidez' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.liquidity === opt.value}
                          onClick={() => setState({ ...state, liquidity: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Income ──────────────────────────────────────────── */}
                {step === 'income' && (
                  <div>
                    <AIMessage text="Qual é sua situação de renda hoje? Preciso entender se você depende do portfólio para pagar contas." typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'active', label: 'Tenho renda ativa (salário, empresa) — não dependo do portfólio' },
                        { value: 'partial', label: 'Renda ativa + complemento do portfólio' },
                        { value: 'depends_portfolio', label: 'Dependo do portfólio para renda corrente' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.income === opt.value}
                          onClick={() => setState({ ...state, income: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Experience ──────────────────────────────────────── */}
                {step === 'experience' && (
                  <div>
                    <AIMessage text="Com quais mercados você já tem experiência? Pode selecionar mais de um." typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'stocks_br', label: 'Ações brasileiras' },
                        { value: 'fiis', label: 'FIIs (Fundos Imobiliários)' },
                        { value: 'renda_fixa', label: 'Renda Fixa (Tesouro, CDB, LCI)' },
                        { value: 'options', label: 'Opções (calls, puts, Wheel)' },
                        { value: 'international', label: 'Exterior (ETFs, BDRs, ações EUA)' },
                        { value: 'none', label: 'Nenhuma experiência — estou começando' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.experience.includes(opt.value)} multi
                          onClick={() => {
                            const exp = state.experience.includes(opt.value)
                              ? state.experience.filter((e) => e !== opt.value)
                              : [...state.experience, opt.value]
                            setState({ ...state, experience: exp })
                          }}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Time ────────────────────────────────────────────── */}
                {step === 'time' && (
                  <div>
                    <AIMessage text="Quanto tempo você consegue dedicar ao portfólio por semana? Responda como é na prática." typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'none', label: 'Menos de 1 hora — quero tudo no automático' },
                        { value: 'few_per_week', label: '1 a 3 horas — acompanho pontualmente' },
                        { value: 'daily', label: '30+ min por dia — sigo o mercado de perto' },
                        { value: 'professional', label: 'Tempo integral — investir é minha prioridade' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.timeAvailable === opt.value}
                          onClick={() => setState({ ...state, timeAvailable: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Objective ───────────────────────────────────────── */}
                {step === 'objective' && (
                  <div>
                    <AIMessage text="Se você tivesse que escolher uma missão principal para esse portfólio, qual seria?" typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'growth', label: 'Crescimento máximo — quero multiplicar patrimônio' },
                        { value: 'income', label: 'Renda passiva — quero dividendos e proventos mensais' },
                        { value: 'preservation', label: 'Preservação — proteger o que tenho com crescimento real' },
                        { value: 'balance', label: 'Equilíbrio — crescimento com alguma geração de renda' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.objective === opt.value}
                          onClick={() => setState({ ...state, objective: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Horizon ─────────────────────────────────────────── */}
                {step === 'horizon' && (
                  <div>
                    <AIMessage text="Qual o horizonte mínimo que você consegue deixar esse capital investido sem resgatar?" typing />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: '2_less', label: 'Até 2 anos — posso precisar em breve' },
                        { value: '2_5', label: '2 a 5 anos — médio prazo' },
                        { value: '5_10', label: '5 a 10 anos — longo prazo' },
                        { value: '10_plus', label: '+10 anos — visão geracional' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.horizon === opt.value}
                          onClick={() => setState({ ...state, horizon: opt.value })}>{opt.label}</OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Aporte ──────────────────────────────────────────── */}
                {step === 'aporte' && (
                  <div>
                    <AIMessage
                      text={`Quase lá, ${effectiveName}. Aportes regulares mudam completamente o plano. Você pretende fazer aportes mensais?`}
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'sim', label: 'Sim — tenho renda e consigo poupar todo mês' },
                        { value: 'eventual', label: 'Eventualmente — quando sobrar dinheiro' },
                        { value: 'nao', label: 'Não — vou trabalhar só com o capital atual' },
                      ].map((opt) => (
                        <OptionButton key={opt.value} selected={state.fazAporte === opt.value}
                          onClick={() => setState({ ...state, fazAporte: opt.value, aporteMensal: opt.value !== 'sim' ? '' : state.aporteMensal })}>
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                    {state.fazAporte === 'sim' && (
                      <div className="mb-4">
                        <p className="text-sm mb-2" style={{ color: '#94a3b8' }}>Qual valor mensal?</p>
                        <input
                          className="apex-input" placeholder="R$ 0"
                          value={state.aporteMensal ? `R$ ${state.aporteMensal}` : ''}
                          onChange={(e) => {
                            const digits = e.target.value.replace(/\D/g, '')
                            if (!digits) { setState({ ...state, aporteMensal: '' }); return }
                            setState({ ...state, aporteMensal: Number(digits).toLocaleString('pt-BR') })
                          }}
                          onKeyDown={(e) => e.key === 'Enter' && handleNext()}
                          autoFocus
                        />
                      </div>
                    )}
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>

            {/* Navigation buttons */}
            <div className="flex gap-3 mt-6">
              {stepIndex > 0 && (
                <button className="btn-secondary flex items-center gap-2" onClick={handleBack}>
                  <ChevronLeft size={18} />
                  Voltar
                </button>
              )}
              <button
                className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={handleNext}
                disabled={loading}
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'rgba(10,14,23,0.3)', borderTopColor: '#0a0e17' }} />
                ) : (
                  <>
                    {step === 'aporte' ? 'Finalizar perfil' : step === 'horizon' ? 'Quase lá!' : 'Continuar'}
                    <ChevronRight size={18} />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
