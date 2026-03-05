/**
 * Setup Wizard — Nova Carteira Simulada
 * Fluxo: Capital/Nome → Questionário de Perfil → Alocação Sugerida (ajustável) → Confirmar
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, ChevronLeft, Check, FlaskConical, Loader2 } from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

// ─── Types ──────────────────────────────────────────────────────────────────

interface Answers {
  volatility: string
  liquidity: string
  income: string
  experience: string[]
  time_available: string
  objective: string
  horizon: string
}

interface Alocacao {
  etfs: number
  fiis: number
  renda_fixa: number
  momentum: number
  wheel: number
  alpha: number
  dividendos: number
  teses: number
  caixa: number
}

const MODULO_LABELS: Record<keyof Alocacao, string> = {
  etfs: 'ETFs',
  fiis: 'FIIs',
  renda_fixa: 'Renda Fixa',
  momentum: 'Momentum · Trade Técnico',
  wheel: 'Wheel · Opções',
  alpha: 'Alpha · Valor com Stop',
  dividendos: 'Dividendos',
  teses: 'Teses · Convicção DCA',
  caixa: 'Caixa',
}

const MODULO_COLORS: Record<keyof Alocacao, string> = {
  etfs: '#00E676',
  fiis: '#2979FF',
  renda_fixa: '#FFCA28',
  momentum: '#FF6E6E',
  wheel: '#A78BFA',
  alpha: '#F06292',
  dividendos: '#FFD700',
  teses: '#FFA000',
  caixa: '#78909C',
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function OptionBtn({
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
      className="w-full text-left px-4 py-3 rounded-xl text-sm transition-all flex items-center gap-3"
      style={{
        background: selected ? 'rgba(255,152,0,0.08)' : 'rgba(15,23,42,0.6)',
        border: selected ? '1px solid rgba(255,152,0,0.4)' : '1px solid #1e293b',
        color: selected ? '#f1f5f9' : '#94a3b8',
      }}
    >
      <div
        className="w-5 h-5 flex items-center justify-center flex-shrink-0 transition-all"
        style={{
          background: selected ? '#FF9800' : 'transparent',
          border: selected ? '1px solid #FF9800' : '1px solid #1e293b',
          borderRadius: multi ? '4px' : '50%',
        }}
      >
        {selected && <Check size={11} color="#0a0e17" strokeWidth={3} />}
      </div>
      {children}
    </button>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function SetupSimuladaPage() {
  const navigate = useNavigate()
  const { setPortfolioAtivo, setPortfolios } = useStore()

  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [nome, setNome] = useState('Carteira Simulada APEX')
  const [capital, setCapital] = useState('')
  const [capitalErr, setCapitalErr] = useState('')

  // Formata capital no padrão pt-BR (1.000.000) e atualiza estado
  const handleCapitalChange = (raw: string) => {
    const digitsOnly = raw.replace(/\D/g, '')
    if (!digitsOnly) { setCapital(''); setCapitalErr(''); return }
    const num = parseInt(digitsOnly, 10)
    setCapital(num.toLocaleString('pt-BR'))
    setCapitalErr('')
  }

  // Converte string formatada ("1.000.000") para número
  const parseCapital = () => parseFloat(capital.replace(/\./g, '').replace(',', '.'))

  const [answers, setAnswers] = useState<Answers>({
    volatility: '',
    liquidity: '',
    income: '',
    experience: [],
    time_available: '',
    objective: '',
    horizon: '',
  })

  const [loading, setLoading] = useState(false)
  const [sugestao, setSugestao] = useState<{ estrategia: string; score: number; explicacao: string } | null>(null)
  const [alocacao, setAlocacao] = useState<Alocacao>({
    etfs: 0, fiis: 0, renda_fixa: 0, momentum: 0,
    wheel: 0, alpha: 0, dividendos: 0, teses: 0, caixa: 0,
  })

  // ─── Step 1 → 2 validation ──────────────────────────────────────────────
  const irParaQuestionario = () => {
    const cap = parseCapital()
    if (!nome.trim()) return
    if (isNaN(cap) || cap <= 0) {
      setCapitalErr('Informe um capital válido')
      return
    }
    setCapitalErr('')
    setStep(2)
  }

  // ─── Step 2 → 3: chama backend ──────────────────────────────────────────
  const analisarPerfil = async () => {
    const campos: (keyof Answers)[] = ['volatility', 'liquidity', 'income', 'time_available', 'objective', 'horizon']
    for (const c of campos) {
      if (!answers[c] || (Array.isArray(answers[c]) ? (answers[c] as string[]).length === 0 : answers[c] === '')) {
        return // incompleto — UI já mostra visual
      }
    }
    setLoading(true)
    try {
      const cap = parseCapital()
      const res = await api.post('/portfolio/sugerir-alocacao', {
        capital: cap,
        answers: { ...answers, goal_type: answers.objective === 'renda_passiva' ? 'renda' : 'crescimento' },
      })
      const { estrategia, score, alocacao: alocSugerida, explicacao } = res.data
      setSugestao({ estrategia, score, explicacao })
      setAlocacao(alocSugerida as Alocacao)
      setStep(3)
    } catch {
      /* silent */
    }
    setLoading(false)
  }

  // ─── Step 3: criar carteira ──────────────────────────────────────────────
  const criarCarteira = async () => {
    const total = Object.values(alocacao).reduce((a, b) => a + b, 0)
    if (Math.abs(total - 100) > 0.5) return
    setLoading(true)
    try {
      const cap = parseCapital()
      await api.post('/portfolio/criar-simulada-perfil', {
        nome: nome.trim(),
        capital: cap,
        alocacao,
      })
      const rl = await api.get('/portfolio/listar')
      setPortfolios(rl.data)
      const ativo = rl.data.find((p: any) => p.ativo) ?? rl.data[0]
      if (ativo) setPortfolioAtivo(ativo)
      navigate('/sugestoes-alocacao', { state: { portfolioId: ativo?.id, modo: 'inicial' } })
    } catch { /* silent */ }
    setLoading(false)
  }

  const totalAlocacao = Object.values(alocacao).reduce((a, b) => a + b, 0)
  const totalOk = Math.abs(totalAlocacao - 100) <= 0.5

  const pieData = (Object.entries(alocacao) as [keyof Alocacao, number][])
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: MODULO_LABELS[k], value: v, color: MODULO_COLORS[k] }))

  const toggleExp = (v: string) => {
    setAnswers(a => ({
      ...a,
      experience: a.experience.includes(v)
        ? a.experience.filter(x => x !== v)
        : [...a.experience, v],
    }))
  }

  const answersComplete = ['volatility', 'liquidity', 'income', 'time_available', 'objective', 'horizon']
    .every(k => answers[k as keyof Answers] !== '')

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: '#0a0e17' }}
    >
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(255,152,0,0.12)', border: '1px solid rgba(255,152,0,0.3)' }}
          >
            <FlaskConical size={17} style={{ color: '#FF9800' }} />
          </div>
          <div>
            <h1 className="text-lg font-bold" style={{ color: '#f1f5f9' }}>Nova Carteira Simulada</h1>
            <p className="text-xs" style={{ color: '#64748b' }}>
              Etapa {step} de 3 — {step === 1 ? 'Capital e Nome' : step === 2 ? 'Perfil de Investidor' : 'Alocação Sugerida'}
            </p>
          </div>
          {/* Progress dots */}
          <div className="ml-auto flex gap-1.5">
            {[1, 2, 3].map(s => (
              <div
                key={s}
                className="rounded-full transition-all"
                style={{
                  width: s === step ? '20px' : '6px',
                  height: '6px',
                  background: s <= step ? '#FF9800' : '#1e293b',
                }}
              />
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          {/* ───── STEP 1: Nome + Capital ─────────────────────────────────── */}
          {step === 1 && (
            <motion.div
              key="s1"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="space-y-6"
            >
              <div
                className="rounded-2xl p-6 space-y-5"
                style={{ background: '#0d1117', border: '1px solid #1e293b' }}
              >
                <div>
                  <label className="text-xs font-mono uppercase tracking-wider block mb-2" style={{ color: '#64748b' }}>
                    Nome da Carteira
                  </label>
                  <input
                    value={nome}
                    onChange={e => setNome(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                    style={{ background: '#0a0e17', border: '1px solid #334155', color: '#f1f5f9' }}
                    placeholder="ex: Carteira Simulada Agressiva"
                  />
                </div>
                <div>
                  <label className="text-xs font-mono uppercase tracking-wider block mb-2" style={{ color: '#64748b' }}>
                    Capital Disponível (R$)
                  </label>
                  <input
                    value={capital}
                    onChange={e => handleCapitalChange(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl text-sm outline-none font-mono"
                    style={{ background: '#0a0e17', border: `1px solid ${capitalErr ? '#FF5252' : '#334155'}`, color: '#f1f5f9' }}
                    placeholder="ex: 50.000"
                    inputMode="numeric"
                  />
                  {capitalErr && <p className="text-xs mt-1.5" style={{ color: '#FF5252' }}>{capitalErr}</p>}
                  <p className="text-xs mt-1.5" style={{ color: '#475569' }}>
                    O APEX Manager vai sugerir a alocação ideal para este montante.
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => navigate(-1)}
                  className="flex-1 py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                  style={{ color: '#64748b', border: '1px solid #1e293b' }}
                >
                  <ChevronLeft size={16} /> Voltar
                </button>
                <button
                  onClick={irParaQuestionario}
                  disabled={!nome.trim() || !capital}
                  className="flex-[2] py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2"
                  style={{
                    background: nome.trim() && capital ? 'rgba(255,152,0,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${nome.trim() && capital ? 'rgba(255,152,0,0.4)' : '#1e293b'}`,
                    color: nome.trim() && capital ? '#FF9800' : '#475569',
                  }}
                >
                  Continuar <ChevronRight size={16} />
                </button>
              </div>
            </motion.div>
          )}

          {/* ───── STEP 2: Questionário ──────────────────────────────────── */}
          {step === 2 && (
            <motion.div
              key="s2"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="space-y-4"
            >
              <div
                className="rounded-2xl p-6 space-y-6 overflow-y-auto"
                style={{ background: '#0d1117', border: '1px solid #1e293b', maxHeight: '60vh' }}
              >

                {/* 1. Volatilidade */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    1. Se sua carteira cair 20% em um mês, você:
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'vende_tudo', l: 'Vende tudo — não aguento ver perda' },
                      { v: 'vende_parte', l: 'Vende parte para reduzir risco' },
                      { v: 'mantem', l: 'Mantém — acredito na recuperação' },
                      { v: 'compra_mais', l: 'Compra mais — é uma oportunidade' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.volatility === o.v} onClick={() => setAnswers(a => ({ ...a, volatility: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 2. Liquidez */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    2. Nos próximos 12 meses, precisará resgatar parte do capital?
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'mais_30pct', l: 'Sim, mais de 30%' },
                      { v: '10_30pct', l: 'Sim, entre 10% e 30%' },
                      { v: 'menos_10pct', l: 'Menos de 10%' },
                      { v: 'nenhuma', l: 'Não precisarei de nada' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.liquidity === o.v} onClick={() => setAnswers(a => ({ ...a, liquidity: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 3. Renda */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    3. Sua situação de renda ativa:
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'depende_portfolio', l: 'Vivo do portfólio — preciso de renda' },
                      { v: 'parcial', l: 'Renda ativa, mas suplemento com o portfólio' },
                      { v: 'ativa', l: 'Renda ativa sólida — não dependo da carteira' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.income === o.v} onClick={() => setAnswers(a => ({ ...a, income: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 4. Experiência */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    4. Onde já investiu? (múltipla escolha)
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'iniciante', l: 'Sou iniciante — só poupança/CDB' },
                      { v: 'acoes_br', l: 'Ações brasileiras (B3)' },
                      { v: 'etfs', l: 'ETFs / Fundos de índice' },
                      { v: 'bdrs', l: 'BDRs / Ações internacionais' },
                      { v: 'opcoes', l: 'Opções e derivativos' },
                      { v: 'exterior', l: 'Conta no exterior (NYSE/NASDAQ)' },
                    ].map(o => (
                      <OptionBtn key={o.v} multi selected={answers.experience.includes(o.v)} onClick={() => toggleExp(o.v)}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 5. Objetivo */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    5. Objetivo principal desta carteira simulada:
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'preservacao', l: 'Preservação de capital — segurança acima de tudo' },
                      { v: 'renda_passiva', l: 'Renda passiva — dividendos e juros mensais' },
                      { v: 'equilibrio', l: 'Equilíbrio entre crescimento e renda' },
                      { v: 'crescimento', l: 'Crescimento máximo — aceito volatilidade' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.objective === o.v} onClick={() => setAnswers(a => ({ ...a, objective: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 6. Horizonte */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    6. Horizonte de investimento:
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'ate_2anos', l: 'Até 2 anos' },
                      { v: '2_5anos', l: '2 a 5 anos' },
                      { v: '5_10anos', l: '5 a 10 anos' },
                      { v: 'mais_10anos', l: 'Mais de 10 anos' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.horizon === o.v} onClick={() => setAnswers(a => ({ ...a, horizon: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

                {/* 7. Tempo */}
                <div>
                  <p className="text-sm font-medium mb-3" style={{ color: '#f1f5f9' }}>
                    7. Tempo semanal dedicado à carteira:
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { v: 'menos_1h', l: 'Menos de 1h — quero algo passivo' },
                      { v: '1_3h', l: '1 a 3 horas' },
                      { v: '3_5h', l: '3 a 5 horas' },
                      { v: 'mais_5h', l: 'Mais de 5h — acompanho ativamente' },
                    ].map(o => (
                      <OptionBtn key={o.v} selected={answers.time_available === o.v} onClick={() => setAnswers(a => ({ ...a, time_available: o.v }))}>
                        {o.l}
                      </OptionBtn>
                    ))}
                  </div>
                </div>

              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                  style={{ color: '#64748b', border: '1px solid #1e293b' }}
                >
                  <ChevronLeft size={16} /> Voltar
                </button>
                <button
                  onClick={analisarPerfil}
                  disabled={loading || !answersComplete}
                  className="flex-[2] py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2"
                  style={{
                    background: answersComplete && !loading ? 'rgba(255,152,0,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${answersComplete && !loading ? 'rgba(255,152,0,0.4)' : '#1e293b'}`,
                    color: answersComplete && !loading ? '#FF9800' : '#475569',
                  }}
                >
                  {loading ? <><Loader2 size={16} className="animate-spin" /> Analisando...</> : <>Analisar Perfil <ChevronRight size={16} /></>}
                </button>
              </div>
            </motion.div>
          )}

          {/* ───── STEP 3: Alocação Sugerida ─────────────────────────────── */}
          {step === 3 && sugestao && (
            <motion.div
              key="s3"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="space-y-4"
            >
              {/* Estratégia */}
              <div
                className="rounded-2xl p-5"
                style={{ background: '#0d1117', border: '1px solid rgba(255,152,0,0.2)' }}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span
                    className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg"
                    style={{ background: 'rgba(255,152,0,0.12)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.3)' }}
                  >
                    APEX {sugestao.estrategia}
                  </span>
                  <span className="text-xs" style={{ color: '#64748b' }}>Score {sugestao.score}/15</span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>{sugestao.explicacao}</p>
              </div>

              {/* Pie + Alocação Editável */}
              <div
                className="rounded-2xl p-5"
                style={{ background: '#0d1117', border: '1px solid #1e293b' }}
              >
                <div className="flex items-start gap-4">
                  {/* Pie chart */}
                  <div style={{ width: 120, height: 120, flexShrink: 0 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={pieData} cx="50%" cy="50%" innerRadius={28} outerRadius={52} dataKey="value" stroke="none">
                          {pieData.map((entry, i) => (
                            <Cell key={i} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ background: '#0d1117', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                          formatter={(v: number) => [`${v}%`, '']}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Sliders */}
                  <div className="flex-1 space-y-2">
                    <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
                      Ajuste a alocação (total: <span style={{ color: totalOk ? '#00E676' : '#FF5252' }}>{totalAlocacao.toFixed(0)}%</span>)
                    </p>
                    {(Object.entries(alocacao) as [keyof Alocacao, number][]).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className="text-[11px] font-mono w-20 flex-shrink-0" style={{ color: MODULO_COLORS[key] }}>
                          {MODULO_LABELS[key]}
                        </span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={5}
                          value={val}
                          onChange={e => setAlocacao(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                          className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer"
                          style={{ accentColor: MODULO_COLORS[key] }}
                        />
                        <span className="text-[11px] font-mono w-8 text-right" style={{ color: '#f1f5f9' }}>{val}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Capital summary */}
              <div
                className="rounded-xl px-4 py-3 flex items-center justify-between text-sm"
                style={{ background: 'rgba(255,152,0,0.05)', border: '1px solid rgba(255,152,0,0.15)' }}
              >
                <span style={{ color: '#64748b' }}>Capital inicial</span>
                <span className="font-mono font-bold" style={{ color: '#FF9800' }}>
                  R$ {parseCapital().toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </span>
              </div>

              {!totalOk && (
                <p className="text-xs text-center" style={{ color: '#FF5252' }}>
                  A soma da alocação deve ser exatamente 100% (atual: {totalAlocacao.toFixed(0)}%)
                </p>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                  style={{ color: '#64748b', border: '1px solid #1e293b' }}
                >
                  <ChevronLeft size={16} /> Voltar
                </button>
                <button
                  onClick={criarCarteira}
                  disabled={loading || !totalOk}
                  className="flex-[2] py-3 rounded-xl text-sm font-medium transition-all flex items-center justify-center gap-2"
                  style={{
                    background: totalOk && !loading ? 'rgba(255,152,0,0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${totalOk && !loading ? 'rgba(255,152,0,0.4)' : '#1e293b'}`,
                    color: totalOk && !loading ? '#FF9800' : '#475569',
                  }}
                >
                  {loading
                    ? <><Loader2 size={16} className="animate-spin" /> Criando...</>
                    : <><FlaskConical size={15} /> Criar Carteira Simulada</>
                  }
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
