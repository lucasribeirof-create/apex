/**
 * Onboarding - Fluxo simplificado de 4 passos.
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronRight, ChevronLeft, Check,
  Wallet, BrainCircuit, Settings, Building2, FlaskConical,
} from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

// --- Typewriter Hook ---------------------------------------------------------

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

// --- Sub-components ----------------------------------------------------------

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
        <p className="text-base leading-relaxed pt-1" style={{ color: '#f1f5f9' }}>
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


// --- Main Component ----------------------------------------------------------

type Step = 'welcome' | 'name' | 'tipo' | 'caminho'

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>('welcome')
  const [name, setName] = useState('')
  const [tipo, setTipo] = useState<'real' | 'simulada' | ''>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [aiInfo, setAiInfo] = useState<{ provider: string; model: string; configured: boolean } | null>(null)

  const { setUser, setStrategy, setPortfolioAtivo, setPortfolios } = useStore()
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/settings/ai')
      .then(r => setAiInfo(r.data))
      .catch(() => setAiInfo(null))
  }, [])

  const stepOrder: Step[] = ['welcome', 'name', 'tipo', 'caminho']
  const stepIndex = stepOrder.indexOf(step)
  const progress = (stepIndex / (stepOrder.length - 1)) * 100

  const handleNext = () => {
    if (step === 'welcome') { setStep('name'); return }
    if (step === 'name') {
      if (!name.trim()) { setError('Por favor, informe seu nome.'); return }
      setError('')
      setStep('tipo')
      return
    }
    if (step === 'tipo') {
      if (!tipo) { setError('Escolha o tipo de carteira.'); return }
      setError('')
      setStep('caminho')
      return
    }
  }

  const handleBack = () => {
    const prevIndex = stepIndex - 1
    if (prevIndex >= 0) setStep(stepOrder[prevIndex])
  }

  async function jaTemAtivos() {
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/onboarding/quick-start', { name, tipo })
      const { user_id, portfolio_id } = res.data
      setUser(String(user_id), name)
      const rl = await api.get('/portfolio/listar')
      setPortfolios(rl.data)
      const ativo = rl.data.find((p: any) => p.id === portfolio_id) ?? rl.data[0]
      if (ativo) setPortfolioAtivo(ativo)
      navigate('/positions')
    } catch {
      setError('Erro ao criar carteira. Verifique se o backend est\u00e1 rodando.')
    }
    setLoading(false)
  }

  async function doZero() {
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/onboarding/start', { name })
      const userId = res.data.user_id
      setUser(String(userId), name)
      navigate('/perfil-investidor', {
        state: { userId, name, tipo, fromOnboarding: true },
      })
    } catch {
      setError('Erro ao conectar com o servidor.')
    }
    setLoading(false)
  }

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
            {['Identifica\u00e7\u00e3o', 'Tipo de carteira', 'Primeiro passo'].map((item, i) => (
              <div key={i} className="flex items-start gap-3">
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono flex-shrink-0 mt-0.5"
                  style={{
                    background: stepIndex > i + 1 ? 'rgba(0, 230, 118, 0.1)' : 'transparent',
                    border: `1px solid ${stepIndex > i + 1 ? '#00E676' : '#1e293b'}`,
                    color: stepIndex > i + 1 ? '#00E676' : '#64748b',
                  }}
                >
                  {stepIndex > i + 1 ? <Check size={12} /> : i + 1}
                </div>
                <p className="text-sm font-medium" style={{ color: stepIndex > i + 1 ? '#f1f5f9' : '#64748b' }}>{item}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs" style={{ color: '#475569' }}>&copy; 2026 APEX Manager</p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {step !== 'welcome' && (
          <div className="h-0.5 w-full" style={{ background: '#1e293b' }}>
            <div
              className="h-full transition-all duration-500"
              style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #00E676, #00BFA5)' }}
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
                {/* Welcome */}
                {step === 'welcome' && (
                  <div className="text-center">
                    <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                      <span className="text-2xl font-bold" style={{ color: '#0a0e17' }}>A</span>
                    </div>
                    <h1 className="text-3xl font-bold mb-3" style={{ color: '#f1f5f9' }}>
                      {'Bem-vindo ao '}<span className="text-green-gradient">APEX Manager</span>
                    </h1>
                    <p className="mb-2" style={{ color: '#94a3b8' }}>
                      {`Seu gestor de patrim\u00f4nio com intelig\u00eancia artificial.`}
                    </p>
                    <p className="text-sm mb-10" style={{ color: '#64748b' }}>
                      {`Em menos de 1 minuto voc\u00ea configura tudo e come\u00e7a a usar.`}
                    </p>
                    <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={handleNext}>
                      Iniciar
                      <ChevronRight size={18} />
                    </button>

                    {aiInfo && (
                      <button
                        onClick={() => navigate('/configurar-ia')}
                        className="mt-6 mx-auto flex items-center gap-2 px-4 py-2 rounded-full transition-all hover:scale-[1.02]"
                        style={{
                          background: 'rgba(15,23,42,0.6)',
                          border: `1px solid ${aiInfo.configured ? 'rgba(170,0,255,0.2)' : 'rgba(255,82,82,0.25)'}`,
                        }}
                        title="Trocar provedor de IA"
                      >
                        <BrainCircuit size={13} style={{ color: aiInfo.configured ? '#AA00FF' : '#FF5252' }} />
                        <span className="text-[11px] font-mono" style={{ color: aiInfo.configured ? '#c4b5fd' : '#fca5a5' }}>
                          {aiInfo.configured
                            ? `${aiInfo.provider.toUpperCase()} \u00b7 ${aiInfo.model}`
                            : `IA n\u00e3o configurada`}
                        </span>
                        <Settings size={11} style={{ color: '#475569' }} />
                      </button>
                    )}
                  </div>
                )}

                {/* Name */}
                {step === 'name' && (
                  <div>
                    <AIMessage
                      text={`Ol\u00e1! Como voc\u00ea se chama? Vou usar seu nome durante toda a nossa intera\u00e7\u00e3o.`}
                      typing
                    />
                    <input
                      className="apex-input mb-2"
                      placeholder="Seu nome..."
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleNext()}
                      autoFocus
                    />
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* Tipo de Carteira */}
                {step === 'tipo' && (
                  <div>
                    <AIMessage
                      text={`${name}, que tipo de carteira voc\u00ea quer criar?`}
                      typing
                    />
                    <div className="space-y-3 mb-4">
                      <button
                        className="w-full text-left rounded-2xl p-5 transition-all"
                        style={{
                          background: tipo === 'real' ? 'rgba(0,230,118,0.08)' : 'rgba(15,23,42,0.6)',
                          border: tipo === 'real' ? '2px solid rgba(0,230,118,0.4)' : '2px solid #1e293b',
                        }}
                        onClick={() => setTipo('real')}
                      >
                        <div className="flex items-start gap-4">
                          <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                            style={{ background: tipo === 'real' ? 'rgba(0,230,118,0.15)' : 'rgba(0,230,118,0.05)', border: '1px solid rgba(0,230,118,0.2)' }}>
                            <Building2 size={20} style={{ color: '#00E676' }} />
                          </div>
                          <div className="flex-1">
                            <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                              Carteira Real
                            </div>
                            <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                              {`Para gerenciar seus investimentos reais. O gestor analisa, rebalanceia e gera plano de a\u00e7\u00e3o em PDF para executar na corretora.`}
                            </div>
                          </div>
                          <div
                            className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-1"
                            style={{
                              background: tipo === 'real' ? '#00E676' : 'transparent',
                              border: tipo === 'real' ? '1px solid #00E676' : '1px solid #1e293b',
                            }}
                          >
                            {tipo === 'real' && <Check size={12} color="#0a0e17" strokeWidth={3} />}
                          </div>
                        </div>
                      </button>

                      <button
                        className="w-full text-left rounded-2xl p-5 transition-all"
                        style={{
                          background: tipo === 'simulada' ? 'rgba(0,191,165,0.08)' : 'rgba(15,23,42,0.6)',
                          border: tipo === 'simulada' ? '2px solid rgba(0,191,165,0.4)' : '2px solid #1e293b',
                        }}
                        onClick={() => setTipo('simulada')}
                      >
                        <div className="flex items-start gap-4">
                          <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                            style={{ background: tipo === 'simulada' ? 'rgba(0,191,165,0.15)' : 'rgba(0,191,165,0.05)', border: '1px solid rgba(0,191,165,0.2)' }}>
                            <FlaskConical size={20} style={{ color: '#00BFA5' }} />
                          </div>
                          <div className="flex-1">
                            <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                              Carteira Simulada
                            </div>
                            <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                              {`Para testar estrat\u00e9gias com dinheiro fict\u00edcio. O gestor monta e rebalanceia automaticamente \u2014 ideal para aprender.`}
                            </div>
                          </div>
                          <div
                            className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-1"
                            style={{
                              background: tipo === 'simulada' ? '#00BFA5' : 'transparent',
                              border: tipo === 'simulada' ? '1px solid #00BFA5' : '1px solid #1e293b',
                            }}
                          >
                            {tipo === 'simulada' && <Check size={12} color="#0a0e17" strokeWidth={3} />}
                          </div>
                        </div>
                      </button>
                    </div>
                    {error && <p className="text-sm mb-3" style={{ color: '#FF5252' }}>{error}</p>}
                  </div>
                )}

                {/* Caminho */}
                {step === 'caminho' && (
                  <div>
                    <AIMessage
                      text={`Perfeito, ${name}. Agora me diz: voc\u00ea j\u00e1 tem investimentos que quer registrar ou quer come\u00e7ar do zero?`}
                      typing
                    />

                    <button
                      className="w-full text-left rounded-2xl p-5 mb-3 transition-all hover:brightness-110"
                      style={{
                        background: 'rgba(0,230,118,0.05)',
                        border: '2px solid rgba(0,230,118,0.3)',
                      }}
                      onClick={jaTemAtivos}
                      disabled={loading}
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                          style={{ background: 'rgba(0,230,118,0.12)', border: '1px solid rgba(0,230,118,0.2)' }}>
                          <Wallet size={20} style={{ color: '#00E676' }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                            {`J\u00e1 tenho investimentos`}
                          </div>
                          <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                            Vou direto registrar meus ativos. Depois posso pedir pro gestor analisar e rebalancear.
                          </div>
                          <div className="mt-3 flex items-center gap-2 text-xs font-mono flex-wrap">
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Registrar ativos</span>
                            <span style={{ color: '#475569' }}>{'\u2192'}</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Gestor analisa</span>
                            <span style={{ color: '#475569' }}>{'\u2192'}</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>Rebalancear</span>
                          </div>
                        </div>
                        <ChevronRight size={20} style={{ color: '#475569', flexShrink: 0, marginTop: 2 }} />
                      </div>
                    </button>

                    <button
                      className="w-full text-left rounded-2xl p-5 transition-all hover:brightness-110"
                      style={{
                        background: 'rgba(0,191,165,0.05)',
                        border: '2px solid rgba(0,191,165,0.3)',
                      }}
                      onClick={doZero}
                      disabled={loading}
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                          style={{ background: 'rgba(0,191,165,0.12)', border: '1px solid rgba(0,191,165,0.2)' }}>
                          <BrainCircuit size={20} style={{ color: '#00BFA5' }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>Quero criar do zero</div>
                          <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                            Respondo algumas perguntas e o gestor monta a carteira ideal com os ativos pra comprar.
                          </div>
                          <div className="mt-3 flex items-center gap-2 text-xs font-mono flex-wrap">
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>Perfil + capital</span>
                            <span style={{ color: '#475569' }}>{'\u2192'}</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>Gestor monta carteira</span>
                            <span style={{ color: '#475569' }}>{'\u2192'}</span>
                            <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,191,165,0.08)', color: '#00BFA5' }}>Aprovar ativos</span>
                          </div>
                        </div>
                        <ChevronRight size={20} style={{ color: '#475569', flexShrink: 0, marginTop: 2 }} />
                      </div>
                    </button>

                    {error && <p className="text-sm mt-3" style={{ color: '#FF5252' }}>{error}</p>}
                    {loading && (
                      <div className="mt-4 flex items-center gap-3" style={{ color: '#64748b' }}>
                        <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#00E676' }} />
                        <span className="text-sm">Criando sua carteira...</span>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>

            {step !== 'welcome' && step !== 'caminho' && (
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
                  Continuar
                  <ChevronRight size={18} />
                </button>
              </div>
            )}

            {step === 'caminho' && !loading && (
              <div className="mt-4">
                <button className="btn-secondary flex items-center gap-2" onClick={handleBack}>
                  <ChevronLeft size={18} />
                  Voltar
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
