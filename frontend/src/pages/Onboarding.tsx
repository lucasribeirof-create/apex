import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, ChevronLeft, Check, AlertTriangle, TrendingUp, Wallet, Target, Loader2, BrainCircuit, Shield } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import ThinkingSteps from '@/components/ThinkingSteps'

// ─── Types ──────────────────────────────────────────────────────────────────

type Step =
  | 'welcome'
  | 'name'
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
  | 'result'

interface OnboardingState {
  name: string
  patrimony: string
  goalType: string
  goalValue: string
  goalHorizon: string
  goalDescription: string
  volatility: string
  liquidity: string
  income: string
  experience: string[]
  timeAvailable: string
  objective: string
  horizon: string
  aporteMensal: string   // R$ por mês (vazio = sem aportes)
  fazAporte: string      // 'sim' | 'nao' | 'eventual'
}

// ─── Typewriter Hook ─────────────────────────────────────────────────────────

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
      if (i >= text.length) {
        clearInterval(timer)
        setDone(true)
      }
    }, speed)
    return () => clearInterval(timer)
  }, [text, speed])

  return { displayed, done }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function OptionButton({
  selected,
  onClick,
  children,
  multi = false,
}: {
  selected: boolean
  onClick: () => void
  children: React.ReactNode
  multi?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center gap-3"
      style={{
        background: selected ? 'rgba(0, 230, 118, 0.08)' : 'rgba(15, 23, 42, 0.6)',
        border: selected ? '1px solid rgba(0, 230, 118, 0.4)' : '1px solid #1e293b',
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

function AIMessage({ text, typing = false }: { text: string; typing?: boolean }) {
  const { displayed, done } = useTypewriter(typing ? text : '')
  const content = typing ? displayed : text

  return (
    <div className="mb-6">
      <div className="flex items-start gap-3 mb-4">
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}
        >
          <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
        </div>
        <p
          className="text-base leading-relaxed pt-1"
          style={{ color: '#f1f5f9' }}
        >
          {content}
          {typing && !done && (
            <span
              className="inline-block w-0.5 h-4 ml-0.5 align-middle animate-pulse"
              style={{ background: '#00E676' }}
            />
          )}
        </p>
      </div>
    </div>
  )
}

// ─── Allocation Chart ─────────────────────────────────────────────────────────

const ALLOC_COLORS: Record<string, string> = {
  ETFs: '#00E676',
  FIIs: '#00BFA5',
  'Renda Fixa': '#1DE9B6',
  Momentum: '#64FFDA',
  Wheel: '#26A69A',
  Convicção: '#FF6B35',
  Caixa: '#475569',
}

function AllocationChart({ allocation }: { allocation: Record<string, number> }) {
  const data = Object.entries(allocation)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))

  return (
    <div className="flex items-center gap-8">
      <ResponsiveContainer width={200} height={200}>
        <PieChart>
          <Pie data={data} cx={95} cy={95} innerRadius={55} outerRadius={90} paddingAngle={2} dataKey="value">
            {data.map((entry) => (
              <Cell key={entry.name} fill={ALLOC_COLORS[entry.name] || '#94a3b8'} />
            ))}
          </Pie>
          <Tooltip
            formatter={(v: number) => `${v}%`}
            contentStyle={{
              background: '#0f1729',
              border: '1px solid #1e293b',
              borderRadius: '8px',
              color: '#f1f5f9',
            }}
          />
        </PieChart>
      </ResponsiveContainer>

      <div className="space-y-2">
        {data.map(({ name, value }) => (
          <div key={name} className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: ALLOC_COLORS[name] || '#94a3b8' }} />
            <span className="text-sm" style={{ color: '#94a3b8' }}>{name}</span>
            <span className="text-sm font-mono ml-auto" style={{ color: '#f1f5f9' }}>{value}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>('welcome')
  const [state, setState] = useState<OnboardingState>({
    name: '',
    patrimony: '',
    goalType: '',
    goalValue: '',
    goalHorizon: '',
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
  const [userId, setUserId] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Plano estratégico (Estrategista)
  const [plano, setPlano] = useState<any>(null)
  const [planoLoading, setPlanoLoading] = useState(false)
  const [selectedCenarioIdx, setSelectedCenarioIdx] = useState<number | null>(null)

  const { setUser, setStrategy } = useStore()
  const navigate = useNavigate()

  // Quando chega ao step result, dispara o Estrategista em background
  useEffect(() => {
    if (step === 'result' && result?.user_id && !plano && !planoLoading) {
      setPlanoLoading(true)
      api.post('/onboarding/plano', { user_id: result.user_id })
        .then((r) => setPlano(r.data))
        .catch(() => setPlano(null))
        .finally(() => setPlanoLoading(false))
    }
  }, [step, result])

  const stepOrder: Step[] = [
    'welcome', 'name', 'patrimony', 'goal',
    'volatility', 'liquidity', 'income',
    'experience', 'time', 'objective', 'horizon', 'aporte', 'result',
  ]

  const stepIndex = stepOrder.indexOf(step)
  const progress = ((stepIndex) / (stepOrder.length - 1)) * 100

  const handleNext = async () => {
    if (step === 'welcome') {
      setStep('name')
      return
    }

    if (step === 'name') {
      if (!state.name.trim()) return setError('Por favor, informe o nome da carteira.')
      setError('')
      setStep('patrimony')
      return
    }

    if (step === 'patrimony') {
      if (!state.patrimony) return setError('Por favor, informe seu patrimônio.')
      setError('')

      // Cria usuário no backend
      try {
        setLoading(true)
        const res = await api.post('/onboarding/start', { name: state.name })
        setUserId(res.data.user_id)
      } catch {
        setError('Erro ao conectar com o servidor. Verifique se o backend está rodando.')
        setLoading(false)
        return
      } finally {
        setLoading(false)
      }
      setStep('goal')
      return
    }

    if (step === 'horizon') {
      if (!state.horizon) return setError('Selecione uma opção para continuar.')
      setError('')
      const nextIndex = stepIndex + 1
      if (nextIndex < stepOrder.length) setStep(stepOrder[nextIndex])
      return
    }

    if (step === 'aporte') {
      if (!state.fazAporte) return setError('Selecione uma opção para continuar.')
      if (state.fazAporte === 'sim' && !state.aporteMensal) return setError('Informe o valor do aporte mensal.')
      setError('')
      // Finaliza onboarding
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
          user_id: userId,
          name: state.name,
          answers,
          total_patrimony: parseFloat(state.patrimony.replace(/\D/g, '')) || 0,
          aporte_mensal: aporteMensal,
        })

        setResult(res.data)
        // Não autenticar ainda — o usuário precisa escolher o fluxo antes de entrar no app.
        setStep('result')
      } catch {
        setError('Erro ao finalizar onboarding.')
      } finally {
        setLoading(false)
      }
      return
    }

    if (step === 'goal') {
      if (!state.goalType) return setError('Selecione uma opção para continuar.')
      if (state.goalType === 'valor' && !state.goalValue.trim()) return setError('Informe o valor que você quer atingir.')
      if (state.goalType === 'percentual' && !state.goalValue.trim()) return setError('Informe o retorno % anual que você busca.')
      if (state.goalType === 'renda' && !state.goalValue.trim()) return setError('Informe a renda mensal que você quer receber.')
      if (state.goalType === 'livre' && !state.goalDescription.trim()) return setError('Conte um pouco sobre seu objetivo.')
      setError('')
    }

    const nextIndex = stepIndex + 1
    if (nextIndex < stepOrder.length) {
      setStep(stepOrder[nextIndex])
    }
  }

  const handleBack = () => {
    const prevIndex = stepIndex - 1
    if (prevIndex >= 0) setStep(stepOrder[prevIndex])
  }

  const handleFinish = () => {
    navigate('/briefing')
  }

  const formatMoney = (value: string) => {
    const digits = value.replace(/\D/g, '')
    if (!digits) return ''
    return 'R$ ' + Number(digits).toLocaleString('pt-BR')
  }

  // ─── Progress Bar ──────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen flex" style={{ background: '#0a0e17' }}>
      {/* Left decorative panel */}
      <div className="hidden lg:flex w-80 flex-col justify-between p-8 border-r" style={{ borderColor: '#1e293b', background: '#0a0e1a' }}>
        <div>
          <div className="flex items-center gap-3 mb-12">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="font-bold text-sm" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <div>
              <h1 className="font-bold" style={{ color: '#f1f5f9' }}>APEX Manager</h1>
              <p className="text-xs font-mono" style={{ color: '#64748b' }}>Portfolio Intelligence</p>
            </div>
          </div>

          <div className="space-y-6">
            {['Diagnóstico de perfil', 'Definição de estratégia', 'Alocação personalizada'].map((item, i) => (
              <div key={i} className="flex items-start gap-3">
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono flex-shrink-0 mt-0.5"
                  style={{
                    background: i < stepIndex / 3 ? 'rgba(0, 230, 118, 0.1)' : 'transparent',
                    border: `1px solid ${i < stepIndex / 3 ? '#00E676' : '#1e293b'}`,
                    color: i < stepIndex / 3 ? '#00E676' : '#64748b',
                  }}
                >
                  {i + 1}
                </div>
                <div>
                  <p className="text-sm font-medium" style={{ color: i < stepIndex / 3 ? '#f1f5f9' : '#64748b' }}>{item}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs" style={{ color: '#475569' }}>
          &copy; 2026 APEX Manager · Confidencial
        </p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Progress bar */}
        {step !== 'welcome' && step !== 'result' && (
          <div className="h-0.5 w-full" style={{ background: '#1e293b' }}>
            <div
              className="h-full transition-all duration-500"
              style={{
                width: `${progress}%`,
                background: 'linear-gradient(90deg, #00E676, #00BFA5)',
              }}
            />
          </div>
        )}

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
                {/* ── Welcome ─────────────────────────────────────────────── */}
                {step === 'welcome' && (
                  <div className="text-center">
                    <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                      <span className="text-2xl font-bold" style={{ color: '#0a0e17' }}>A</span>
                    </div>
                    <h1 className="text-3xl font-bold mb-3" style={{ color: '#f1f5f9' }}>
                      Bem-vindo ao <span className="text-green-gradient">APEX Manager</span>
                    </h1>
                    <p className="mb-2" style={{ color: '#94a3b8' }}>
                      Seu gestor de patrimônio com inteligência artificial.
                    </p>
                    <p className="text-sm mb-10" style={{ color: '#64748b' }}>
                      Vou fazer algumas perguntas para entender seu perfil e montar a estratégia ideal para você. Leva menos de 5 minutos.
                    </p>
                    <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={handleNext}>
                      Iniciar Diagnóstico
                      <ChevronRight size={18} />
                    </button>
                  </div>
                )}

                {/* ── Name (nome da carteira) ───────────────────────────────── */}
                {step === 'name' && (
                  <div>
                    <AIMessage
                      text="Como quer chamar esta carteira? Esse nome aparecerá na lista ao selecionar carteira."
                      typing
                    />
                    <input
                      className="apex-input mb-2"
                      placeholder="Nome da carteira"
                      value={state.name}
                      onChange={(e) => setState({ ...state, name: e.target.value })}
                      onKeyDown={(e) => e.key === 'Enter' && handleNext()}
                      autoFocus
                    />
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Patrimony ─────────────────────────────────────────────── */}
                {step === 'patrimony' && (
                  <div>
                    <AIMessage
                      text={`${state.name}, qual é seu patrimônio total disponível para investir? Inclua tudo: ações, fundos, renda fixa, caixa. Esse número é fundamental para calibrar a estratégia.`}
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

                {/* ── Goal ─────────────────────────────────────────────────── */}
                {step === 'goal' && (
                  <div>
                    <AIMessage
                      text="Qual é o seu objetivo com esse patrimônio? Isso vai definir qual estratégia faz mais sentido para você."
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'valor', label: 'Quero chegar em um valor específico (R$)' },
                        { value: 'percentual', label: 'Quero um retorno de X% ao ano' },
                        { value: 'renda', label: 'Quero viver de renda passiva (R$/mês)' },
                        { value: 'livre', label: 'Quero explicar do meu jeito' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.goalType === opt.value}
                          onClick={() => setState({ ...state, goalType: opt.value, goalValue: '' })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>

                    {/* Campo contextual por tipo */}
                    {state.goalType === 'valor' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual valor você quer atingir?</label>
                        <input
                          className="apex-input"
                          placeholder="Ex: R$ 2.000.000"
                          value={state.goalValue ? 'R$ ' + Number(state.goalValue).toLocaleString('pt-BR') : ''}
                          onChange={(e) => setState({ ...state, goalValue: e.target.value.replace(/\D/g, '') })}
                          autoFocus
                        />
                      </div>
                    )}

                    {state.goalType === 'percentual' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual retorno anual você busca?</label>
                        <div className="relative">
                          <input
                            className="apex-input"
                            placeholder="Ex: 15"
                            type="number"
                            min="1"
                            max="200"
                            value={state.goalValue}
                            onChange={(e) => setState({ ...state, goalValue: e.target.value })}
                            autoFocus
                          />
                          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-mono" style={{ color: '#64748b' }}>% ao ano</span>
                        </div>
                      </div>
                    )}

                    {state.goalType === 'renda' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Qual renda mensal você quer receber?</label>
                        <input
                          className="apex-input"
                          placeholder="Ex: R$ 10.000 por mês"
                          value={state.goalValue ? 'R$ ' + Number(state.goalValue).toLocaleString('pt-BR') : ''}
                          onChange={(e) => setState({ ...state, goalValue: e.target.value.replace(/\D/g, '') })}
                          autoFocus
                        />
                      </div>
                    )}

                    {state.goalType === 'livre' && (
                      <div className="mt-1">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>Conta com suas palavras:</label>
                        <textarea
                          className="apex-input resize-none"
                          rows={4}
                          placeholder="Ex: Quero garantir minha aposentadoria em 10 anos com uma renda de R$ 20k/mês e ainda ter reserva para imóveis..."
                          value={state.goalDescription}
                          onChange={(e) => setState({ ...state, goalDescription: e.target.value })}
                          autoFocus
                          style={{ lineHeight: '1.6' }}
                        />
                      </div>
                    )}

                    {/* Campo livre complementar — para qualquer tipo de objetivo */}
                    {state.goalType && state.goalType !== 'livre' && (
                      <div className="mt-3">
                        <label className="text-xs mb-1.5 block" style={{ color: '#64748b' }}>
                          Quer acrescentar algo? (opcional)
                        </label>
                        <textarea
                          className="apex-input resize-none"
                          rows={3}
                          placeholder="Ex: Quero crescimento agressivo nos próximos 5 anos e depois viver de renda..."
                          value={state.goalDescription}
                          onChange={(e) => setState({ ...state, goalDescription: e.target.value })}
                          style={{ lineHeight: '1.6' }}
                        />
                      </div>
                    )}

                    {error && <p className="text-sm mt-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Volatility ───────────────────────────────────────────── */}
                {step === 'volatility' && (
                  <div>
                    <AIMessage
                      text="Cenário real: seu portfólio cai 20% em 3 meses, mas os fundamentos das empresas continuam sólidos. O que você faz?"
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'sell_all', label: 'Vendo tudo — não aguentaria ver mais' },
                        { value: 'sell_partial', label: 'Vendo parte para reduzir o nervosismo' },
                        { value: 'hold', label: 'Seguro firme — já esperava volatilidade' },
                        { value: 'buy_more', label: 'Compro mais — queda é oportunidade' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.volatility === opt.value}
                          onClick={() => setState({ ...state, volatility: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Liquidity ───────────────────────────────────────────── */}
                {step === 'liquidity' && (
                  <div>
                    <AIMessage
                      text="Nos próximos 12 meses, você precisa sacar algum valor desse portfólio? Isso impacta diretamente quanto risco podemos correr."
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'none', label: 'Não preciso de nada — capital 100% investido' },
                        { value: 'small', label: 'Talvez até 10% — alguma reserva de emergência' },
                        { value: 'medium', label: 'Entre 10% e 30% — tenho despesas planejadas' },
                        { value: 'large', label: 'Mais de 30% — necessidade real de liquidez' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.liquidity === opt.value}
                          onClick={() => setState({ ...state, liquidity: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Income ──────────────────────────────────────────────── */}
                {step === 'income' && (
                  <div>
                    <AIMessage
                      text="Qual é sua situação de renda hoje? Preciso entender se você depende do portfólio para pagar suas contas."
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'active', label: 'Tenho renda ativa (salário, empresa) — não dependo do portfólio' },
                        { value: 'partial', label: 'Renda ativa + complemento do portfólio' },
                        { value: 'depends_portfolio', label: 'Dependo do portfólio para renda corrente' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.income === opt.value}
                          onClick={() => setState({ ...state, income: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Experience ──────────────────────────────────────────── */}
                {step === 'experience' && (
                  <div>
                    <AIMessage
                      text="Com quais mercados você já tem experiência? Pode selecionar mais de um — seja honesto, isso muda completamente a estratégia."
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'stocks_br', label: 'Ações brasileiras' },
                        { value: 'fiis', label: 'FIIs (Fundos Imobiliários)' },
                        { value: 'renda_fixa', label: 'Renda Fixa (Tesouro, CDB, LCI)' },
                        { value: 'options', label: 'Opções (calls, puts, Wheel)' },
                        { value: 'international', label: 'Exterior (ETFs, BDRs, ações EUA)' },
                        { value: 'none', label: 'Nenhuma experiência — estou começando' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.experience.includes(opt.value)}
                          multi
                          onClick={() => {
                            const exp = state.experience.includes(opt.value)
                              ? state.experience.filter((e) => e !== opt.value)
                              : [...state.experience, opt.value]
                            setState({ ...state, experience: exp })
                          }}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Time Available ──────────────────────────────────────── */}
                {step === 'time' && (
                  <div>
                    <AIMessage
                      text="Quanto tempo você consegue dedicar ao portfólio por semana? Sem ilusão — responda como é na prática, não como gostaría que fosse."
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'none', label: 'Menos de 1 hora — quero tudo no automático' },
                        { value: 'few_per_week', label: '1 a 3 horas — acompanho pontualmente' },
                        { value: 'daily', label: '30+ min por dia — sigo o mercado de perto' },
                        { value: 'professional', label: 'Tempo integral — investir é minha prioridade' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.timeAvailable === opt.value}
                          onClick={() => setState({ ...state, timeAvailable: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Objective ───────────────────────────────────────────── */}
                {step === 'objective' && (
                  <div>
                    <AIMessage
                      text="Se você tivesse que escolher uma missão principal para esse portfólio, qual seria?"
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'growth', label: 'Crescimento máximo — quero multiplicar patrimônio' },
                        { value: 'income', label: 'Renda passiva — quero dividendos e proventos mensais' },
                        { value: 'preservation', label: 'Preservação — proteger o que tenho com crescimento real' },
                        { value: 'balance', label: 'Equilíbrio — crescimento com alguma geração de renda' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.objective === opt.value}
                          onClick={() => setState({ ...state, objective: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── Horizon ─────────────────────────────────────────────── */}
                {step === 'horizon' && (
                  <div>
                    <AIMessage
                      text="Última pergunta: qual o horizonte mínimo que você consegue deixar esse capital investido sem precisar resgatar?"
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: '2_less', label: 'Até 2 anos — posso precisar desse capital em breve' },
                        { value: '2_5', label: '2 a 5 anos — médio prazo' },
                        { value: '5_10', label: '5 a 10 anos — longo prazo' },
                        { value: '10_plus', label: '+10 anos — visão geracional' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.horizon === opt.value}
                          onClick={() => setState({ ...state, horizon: opt.value })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* ── Aporte ─────────────────────────────────────────────────────── */}
                {step === 'aporte' && (
                  <div>
                    <AIMessage
                      text={`Quase lá, ${state.name}. Aportes regulares mudam completamente o plano de crescimento patrimonial. Você pretende fazer aportes mensais?`}
                      typing
                    />
                    <div className="space-y-2 mb-4">
                      {[
                        { value: 'sim', label: 'Sim — tenho uma renda e consigo poupar todo mês' },
                        { value: 'eventual', label: 'Eventualmente — quando sobrar dinheiro' },
                        { value: 'nao', label: 'Não — vou trabalhar só com o capital atual' },
                      ].map((opt) => (
                        <OptionButton
                          key={opt.value}
                          selected={state.fazAporte === opt.value}
                          onClick={() => setState({ ...state, fazAporte: opt.value, aporteMensal: opt.value !== 'sim' ? '' : state.aporteMensal })}
                        >
                          {opt.label}
                        </OptionButton>
                      ))}
                    </div>
                    {state.fazAporte === 'sim' && (
                      <div className="mb-4">
                        <p className="text-sm mb-2" style={{ color: '#94a3b8' }}>Qual valor mensal você consegue aportar?</p>
                        <input
                          className="apex-input"
                          placeholder="R$ 0"
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

                {/* ── Result ───────────────────────────────────────────────── */}
                {step === 'result' && result && (
                  <div>
                    {/* Badge estratégia */}
                    <div className="text-center mb-6">
                      <div
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-mono mb-4"
                        style={{
                          background: result.strategy_type === 'ALPHA' ? 'rgba(0, 230, 118, 0.1)'
                            : result.strategy_type === 'RENDA' ? 'rgba(0, 191, 165, 0.1)'
                            : result.strategy_type === 'CUSTOM' ? 'rgba(255, 152, 0, 0.1)'
                            : 'rgba(148, 163, 184, 0.1)',
                          border: `1px solid ${
                            result.strategy_type === 'ALPHA' ? 'rgba(0, 230, 118, 0.3)'
                            : result.strategy_type === 'RENDA' ? 'rgba(0, 191, 165, 0.3)'
                            : result.strategy_type === 'CUSTOM' ? 'rgba(255, 152, 0, 0.3)'
                            : 'rgba(148, 163, 184, 0.2)'
                          }`,
                          color: result.strategy_type === 'ALPHA' ? '#00E676'
                            : result.strategy_type === 'RENDA' ? '#00BFA5'
                            : result.strategy_type === 'CUSTOM' ? '#FF9800'
                            : '#94a3b8',
                        }}
                      >
                        APEX {result.strategy_type}
                      </div>
                      <h2 className="text-2xl font-bold mb-1" style={{ color: '#f1f5f9' }}>
                        Perfil configurado
                      </h2>
                      <p className="text-sm" style={{ color: '#64748b' }}>Score: {result.risk_score}/15</p>
                    </div>

                    {/* Diagnóstico do Estrategista */}
                    <div className="rounded-xl p-5 mb-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                          <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
                        </div>
                        <span className="text-sm font-medium" style={{ color: '#94a3b8' }}>Estrategista APEX</span>
                        {planoLoading && <Loader2 size={13} className="animate-spin ml-1" style={{ color: '#64748b' }} />}
                      </div>

                      {planoLoading && !plano && (
                        <div className="py-3">
                          <ThinkingSteps
                            steps={[
                              'Lendo seu perfil de risco e objetivos...',
                              'Calculando viabilidade da sua meta financeira...',
                              'Definindo a estratégia ideal para seu patrimônio...',
                              'Projetando fases de crescimento e horizontes...',
                              'Montando diagnóstico personalizado...',
                            ]}
                            intervalMs={2500}
                            color="#00E676"
                          />
                        </div>
                      )}

                      {plano && (
                        <div className="space-y-4">
                          {/* Diagnóstico — rich text com **bold** */}
                          <div className="text-sm leading-relaxed space-y-1.5" style={{ color: '#f1f5f9' }}>
                            {plano.diagnostico.split('\n').map((line: string, i: number) => {
                              const parts = line.split(/\*\*(.*?)\*\*/g)
                              return (
                                <p key={i} className={line === '' ? 'mb-2' : ''}>
                                  {parts.map((part: string, j: number) =>
                                    j % 2 === 1
                                      ? <strong key={j} style={{ color: '#00E676' }}>{part}</strong>
                                      : part
                                  )}
                                </p>
                              )
                            })}
                          </div>

                          {/* Alerta se meta inviável */}
                          {!plano.meta_viavel && (
                            <div className="flex items-start gap-2 rounded-lg px-3 py-2"
                              style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)' }}>
                              <AlertTriangle size={13} style={{ color: '#f59e0b', flexShrink: 0, marginTop: 2 }} />
                              <span className="text-xs" style={{ color: '#f59e0b' }}>
                                Meta desafiadora no prazo declarado — veja os cenários abaixo.
                              </span>
                            </div>
                          )}

                          {/* Fase atual */}
                          <div className="flex items-start gap-3 pt-1">
                            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                              style={{ background: 'rgba(0,230,118,0.08)', border: '1px solid rgba(0,230,118,0.15)' }}>
                              <TrendingUp size={13} style={{ color: '#00E676' }} />
                            </div>
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-wider mb-0.5" style={{ color: '#00E676' }}>
                                Fase: {plano.fase_atual}
                              </p>
                              <p className="text-xs leading-relaxed" style={{ color: '#94a3b8' }}>{plano.fase_descricao}</p>
                            </div>
                          </div>

                          {/* Estratégia recomendada (se diferente da classificada) */}
                          {plano.estrategia_recomendada !== result.strategy_type && (
                            <div className="rounded-lg px-3 py-2.5"
                              style={{ background: 'rgba(0,230,118,0.04)', border: '1px solid rgba(0,230,118,0.12)' }}>
                              <p className="text-xs font-semibold mb-1" style={{ color: '#00E676' }}>
                                Estratégia ajustada → APEX {plano.estrategia_recomendada}
                              </p>
                              <p className="text-xs" style={{ color: '#64748b' }}>{plano.estrategia_razao}</p>
                            </div>
                          )}

                          {/* ── Cenários comparáveis ────────────────────────── */}
                          {plano.cenarios?.length > 0 && (
                            <div className="pt-2">
                              <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#475569' }}>Cenários para sua meta</p>
                              <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(plano.cenarios.length, 3)}, 1fr)` }}>
                                {plano.cenarios.map((c: any, i: number) => {
                                  const isRec = c.nome?.toLowerCase().includes('recomendado') || c.nome?.toLowerCase().includes('equilibrado')
                                  const defaultIdx = plano.cenarios.findIndex((x: any) => x.nome?.toLowerCase().includes('recomendado') || x.nome?.toLowerCase().includes('equilibrado'))
                                  const effectiveSelectedIdx = selectedCenarioIdx !== null ? selectedCenarioIdx : defaultIdx
                                  const isSelected = i === effectiveSelectedIdx
                                  const colorMap: Record<number, string> = { 0: '#3B82F6', 1: '#00E676', 2: '#FF9800' }
                                  const accent = colorMap[i] || '#64748b'
                                  return (
                                    <div key={i}
                                      onClick={() => setSelectedCenarioIdx(i)}
                                      className="rounded-xl p-4 relative cursor-pointer transition-all"
                                      style={{
                                        background: isSelected ? `${accent}08` : 'rgba(30,41,59,0.3)',
                                        border: isSelected ? `2px solid ${accent}55` : '1px solid #1e293b',
                                        boxShadow: isSelected ? `0 0 16px ${accent}18` : 'none',
                                      }}>
                                      {isRec && (
                                        <span className="absolute -top-2.5 left-3 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                                          style={{ background: '#00E676', color: '#0a0e17' }}>
                                          Recomendado
                                        </span>
                                      )}
                                      {isSelected && !isRec && (
                                        <span className="absolute -top-2.5 right-3 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                                          style={{ background: accent, color: '#0a0e17' }}>
                                          Selecionado
                                        </span>
                                      )}
                                      <p className="text-sm font-bold mb-1.5" style={{ color: accent }}>{c.nome}</p>
                                      <p className="text-xs leading-relaxed mb-3" style={{ color: '#94a3b8' }}>{c.descricao}</p>

                                      {/* Módulos como chips */}
                                      <div className="flex flex-wrap gap-1 mb-3">
                                        {c.modulos?.map((mod: string, mi: number) => (
                                          <span key={mi} className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                                            style={{ background: `${accent}12`, color: accent, border: `1px solid ${accent}30` }}>
                                            {mod}
                                          </span>
                                        ))}
                                      </div>

                                      <div className="space-y-1.5 text-xs">
                                        <div>
                                          <span className="block mb-0.5" style={{ color: '#64748b' }}>Alocação</span>
                                          <span className="font-mono" style={{ color: '#cbd5e1', fontSize: '10px', lineHeight: '1.4' }}>{c.alocacao_resumo}</span>
                                        </div>
                                        <div>
                                          <span className="block mb-0.5" style={{ color: '#64748b' }}>Retorno</span>
                                          <span className="font-mono font-bold" style={{ color: accent }}>{c.rentabilidade_esperada}</span>
                                        </div>
                                        <div>
                                          <span className="block mb-0.5" style={{ color: '#64748b' }}>Tempo</span>
                                          <span className="font-mono font-bold" style={{ color: '#f1f5f9' }}>{c.tempo_meta}</span>
                                        </div>
                                        <div className="pt-1 mt-1" style={{ borderTop: '1px solid rgba(100,116,139,0.15)' }}>
                                          <p className="text-[10px] leading-relaxed" style={{ color: '#f59e0b' }}>
                                            ⚠ {c.risco_principal}
                                          </p>
                                        </div>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          )}

                          {/* ── Módulos + Riscos + Marcos — tudo reativo ao cenário selecionado ── */}
                          {(() => {
                            const defaultIdx = plano.cenarios?.findIndex((x: any) => x.nome?.toLowerCase().includes('recomendado') || x.nome?.toLowerCase().includes('equilibrado')) ?? 1
                            const selIdx = selectedCenarioIdx !== null ? selectedCenarioIdx : defaultIdx
                            const selCenario = plano.cenarios?.[selIdx]
                            const colorMap: Record<number, string> = { 0: '#3B82F6', 1: '#00E676', 2: '#FF9800' }
                            const accent = colorMap[selIdx] || '#00E676'

                            // Parsear alocacao_resumo → [{pct, nome}]
                            const parseAlocacao = (resumo: string) =>
                              (resumo || '').split('·').map(part => {
                                const t = part.trim()
                                const m = t.match(/^(\d[\d,.]*)%?\s+(.+)$/)
                                return m ? { pct: m[1] + '%', nome: m[2].trim() } : { pct: '', nome: t }
                              }).filter(x => x.nome)

                            const alocItems = parseAlocacao(selCenario?.alocacao_resumo || '')

                            // Módulos enriquecidos: usa peso/por_que de modulos_sugeridos se o nome bater
                            const sugeridos: Record<string, any> = {}
                            plano.modulos_sugeridos?.forEach((ms: any) => {
                              sugeridos[ms.nome?.toLowerCase()] = ms
                            })

                            const modItems = alocItems.length > 0
                              ? alocItems.map(({ pct, nome }) => {
                                  const match = sugeridos[nome.toLowerCase()]
                                  return { pct: match?.peso_sugerido || pct, nome, por_que: match?.por_que || null }
                                })
                              : (selCenario?.modulos || []).map((nome: string) => {
                                  const match = sugeridos[nome.toLowerCase()]
                                  return { pct: match?.peso_sugerido || '●', nome, por_que: match?.por_que || null }
                                })

                            return (
                              <>
                                {/* Módulos */}
                                {modItems.length > 0 && (
                                  <div className="pt-1">
                                    <p className="text-xs font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>
                                      Módulos — {selCenario?.nome || 'Selecionado'}
                                    </p>
                                    <div className="space-y-1.5">
                                      {modItems.map((mod: { pct: string; nome: string; por_que: string | null }, i: number) => (
                                        <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2"
                                          style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid #1e293b' }}>
                                          <span className="text-xs font-bold font-mono px-2 py-0.5 rounded flex-shrink-0"
                                            style={{ background: `${accent}12`, color: accent, minWidth: 44, textAlign: 'center' }}>
                                            {mod.pct}
                                          </span>
                                          <div className="min-w-0 flex-1">
                                            <span className="text-sm font-semibold block" style={{ color: '#f1f5f9' }}>{mod.nome}</span>
                                            {mod.por_que && (
                                              <p className="text-xs" style={{ color: '#64748b', lineHeight: '1.4' }}>{mod.por_que}</p>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Riscos — risco_principal do cenário + riscos gerais */}
                                <div className="rounded-lg px-4 py-3"
                                  style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.15)' }}>
                                  <div className="flex items-center gap-2 mb-2">
                                    <Shield size={13} style={{ color: '#ef4444' }} />
                                    <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#ef4444' }}>
                                      Riscos — {selCenario?.nome}
                                    </p>
                                  </div>
                                  <div className="space-y-1">
                                    {selCenario?.risco_principal && (
                                      <p className="text-xs leading-relaxed pl-5 font-medium" style={{ color: '#fca5a5' }}>
                                        • {selCenario.risco_principal}
                                      </p>
                                    )}
                                    {plano.riscos_e_tradeoffs?.map((r: string, i: number) => (
                                      <p key={i} className="text-xs leading-relaxed pl-5" style={{ color: '#fca5a580' }}>
                                        • {r}
                                      </p>
                                    ))}
                                  </div>
                                </div>

                                {/* Marcos */}
                                {plano.marcos?.length > 0 && (
                                  <div>
                                    <p className="text-xs font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>Marcos de progresso</p>
                                    <div className="space-y-2">
                                      {plano.marcos.map((m: any, i: number) => (
                                        <div key={i} className="flex items-start gap-3 rounded-lg px-3 py-2"
                                          style={{ background: 'rgba(30,41,59,0.5)', border: '1px solid #1e293b' }}>
                                          <Target size={12} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                                          <div className="min-w-0 flex-1">
                                            <div className="flex items-baseline gap-2 flex-wrap">
                                              <span className="text-sm font-semibold" style={{ color: '#f1f5f9' }}>
                                                R$ {(m.patrimonio / 1_000_000).toFixed(1)}M
                                              </span>
                                              <span className="text-xs" style={{ color: '#64748b' }}>→</span>
                                              <span className="text-xs font-mono" style={{ color: '#00BFA5' }}>
                                                ~R$ {m.renda_mensal_possivel.toLocaleString('pt-BR')}/mês
                                              </span>
                                              <span className="text-xs font-mono" style={{ color: accent }}>
                                                ~{m.estimativa_anos}a
                                              </span>
                                            </div>
                                            <p className="text-xs mt-0.5" style={{ color: '#475569' }}>{m.descricao}</p>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </>
                            )
                          })()}
                        </div>
                      )}

                      {!planoLoading && !plano && (
                        <p className="text-sm leading-relaxed" style={{ color: '#f1f5f9' }}>{result.ai_explanation}</p>
                      )}
                    </div>

                    {/* Alocação alvo */}
                    <div className="rounded-xl p-5 mb-6" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                      <h3 className="text-xs font-mono uppercase tracking-wider mb-4" style={{ color: '#64748b' }}>Alocação alvo inicial</h3>
                      <AllocationChart
                        allocation={(() => {
                          // Se o Estrategista recomendou outra estratégia e já devolveu a alocação correta, usa ela
                          const src = (plano?.allocation) || result.allocation
                          return {
                            ETFs: src.etfs ?? 0,
                            FIIs: src.fiis ?? 0,
                            'Renda Fixa': src.renda_fixa ?? 0,
                            Momentum: src.momentum ?? 0,
                            Wheel: src.wheel ?? 0,
                            Convicção: src.alpha ?? 0,
                            Dividendos: src.dividendos ?? 0,
                            Caixa: src.caixa ?? src.cash ?? 0,
                          }
                        })()}
                      />
                    </div>

                    {/* ─── ESCOLHA DO FLUXO — só aparece quando análise concluída ─────────── */}
                    <div className="mt-6">
                      <div className="text-center mb-5">
                        <p className="text-base font-bold" style={{ color: '#f1f5f9' }}>Como você quer começar?</p>
                        <p className="text-sm mt-1" style={{ color: '#64748b' }}>Essa escolha define o próximo passo no APEX</p>
                      </div>

                      {/* Aguardando análise */}
                      {planoLoading && (
                        <div className="flex items-center gap-3 justify-center py-6 rounded-xl mb-3"
                          style={{ background: 'rgba(0,230,118,0.03)', border: '1px dashed rgba(0,230,118,0.2)' }}>
                          <Loader2 size={16} className="animate-spin" style={{ color: '#00E676' }} />
                          <span className="text-sm" style={{ color: '#64748b' }}>Estrategista analisando seu perfil... aguarde para continuar</span>
                        </div>
                      )}

                      {/* Card 1: Já tenho investimentos */}
                      <button
                        className="w-full text-left rounded-2xl p-5 mb-3 transition-all"
                        style={{
                          background: planoLoading ? 'rgba(30,41,59,0.4)' : 'rgba(0,230,118,0.05)',
                          border: planoLoading ? '2px solid rgba(30,41,59,0.5)' : '2px solid rgba(0,230,118,0.3)',
                          cursor: planoLoading ? 'not-allowed' : 'pointer',
                          opacity: planoLoading ? 0.5 : 1,
                        }}
                        disabled={planoLoading}
                        onMouseEnter={(e) => { if (!planoLoading) { e.currentTarget.style.background = 'rgba(0,230,118,0.10)'; e.currentTarget.style.borderColor = 'rgba(0,230,118,0.55)' }}}
                        onMouseLeave={(e) => { if (!planoLoading) { e.currentTarget.style.background = 'rgba(0,230,118,0.05)'; e.currentTarget.style.borderColor = 'rgba(0,230,118,0.3)' }}}
                        onClick={() => {
                          if (planoLoading) return
                          setUser(String(result.user_id), state.name)
                          setStrategy((plano?.estrategia_recomendada || result.strategy_type) as 'CORE' | 'ALPHA' | 'RENDA' | 'CUSTOM')
                          navigate('/positions')
                        }}
                      >
                        <div className="flex items-start gap-4">
                          <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(0,230,118,0.12)', border: '1px solid rgba(0,230,118,0.2)' }}>
                            <Wallet size={20} style={{ color: '#00E676' }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>Já tenho investimentos</div>
                            <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                              Vou registrar os ativos que já tenho. O cérebro analisa minha carteira atual e sugere realocações baseadas na estratégia <strong style={{ color: '#00E676' }}>APEX {plano?.estrategia_recomendada || result.strategy_type}</strong>.
                            </div>
                            <div className="mt-3 flex items-center gap-2 text-xs font-mono flex-wrap">
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Preencher portfólio</span>
                              <span style={{ color: '#475569' }}>→</span>
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Cérebro analisa</span>
                              <span style={{ color: '#475569' }}>→</span>
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Sugestões de ajuste</span>
                            </div>
                          </div>
                          <ChevronRight size={20} style={{ color: planoLoading ? '#1e293b' : '#475569', flexShrink: 0, marginTop: 2 }} />
                        </div>
                      </button>

                      {/* Card 2: Começando do zero */}
                      <button
                        className="w-full text-left rounded-2xl p-5 transition-all"
                        style={{
                          background: planoLoading ? 'rgba(30,41,59,0.4)' : 'rgba(0,191,165,0.05)',
                          border: planoLoading ? '2px solid rgba(30,41,59,0.5)' : '2px solid rgba(0,191,165,0.3)',
                          cursor: planoLoading ? 'not-allowed' : 'pointer',
                          opacity: planoLoading ? 0.5 : 1,
                        }}
                        disabled={planoLoading}
                        onMouseEnter={(e) => { if (!planoLoading) { e.currentTarget.style.background = 'rgba(0,191,165,0.10)'; e.currentTarget.style.borderColor = 'rgba(0,191,165,0.55)' }}}
                        onMouseLeave={(e) => { if (!planoLoading) { e.currentTarget.style.background = 'rgba(0,191,165,0.05)'; e.currentTarget.style.borderColor = 'rgba(0,191,165,0.3)' }}}
                        onClick={() => {
                          if (planoLoading) return
                          setUser(String(result.user_id), state.name)
                          setStrategy((plano?.estrategia_recomendada || result.strategy_type) as 'CORE' | 'ALPHA' | 'RENDA' | 'CUSTOM')
                          navigate('/sugestoes-alocacao')
                        }}
                      >
                        <div className="flex items-start gap-4">
                          <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(0,191,165,0.12)', border: '1px solid rgba(0,191,165,0.2)' }}>
                            <BrainCircuit size={20} style={{ color: '#00BFA5' }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>Estou começando do zero</div>
                            <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                              Ainda não tenho ativos. O gestor APEX age como um gestor profissional: analisa o momento de mercado, seu perfil e seu capital, e monta um plano de alocação inicial com o que comprar.
                            </div>
                            <div className="mt-3 flex items-center gap-2 text-xs font-mono flex-wrap">
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>Macro + perfil</span>
                              <span style={{ color: '#475569' }}>→</span>
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>Plano de alocação</span>
                              <span style={{ color: '#475569' }}>→</span>
                              <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>O que comprar</span>
                            </div>
                          </div>
                          <ChevronRight size={20} style={{ color: planoLoading ? '#1e293b' : '#475569', flexShrink: 0, marginTop: 2 }} />
                        </div>
                      </button>
                    </div>
                  </div>
                )}

                {/* ── Loading (finalizando) ─────────────────────────────────── */}
                {loading && step !== 'result' && (
                  <div className="mt-4 flex items-center gap-3" style={{ color: '#64748b' }}>
                    <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#00E676' }} />
                    <span className="text-sm">Analisando seu perfil...</span>
                  </div>
                )}

              </motion.div>
            </AnimatePresence>

            {/* Navigation buttons */}
            {step !== 'welcome' && step !== 'result' && (
              <div className="flex gap-3 mt-6">
                {step !== 'name' && (
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
                      {step === 'horizon' ? 'Ver minha estratégia' : 'Continuar'}
                      <ChevronRight size={18} />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
