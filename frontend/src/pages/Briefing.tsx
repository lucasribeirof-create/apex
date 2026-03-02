import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { RefreshCw, Sun, TrendingUp, TrendingDown } from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import ThinkingSteps from '@/components/ThinkingSteps'

interface BriefingData {
  id: number
  data: string
  conteudo: string
  regime: string
  macro: {
    dolar: number | null
    ibov: number | null
    ibov_variacao: number | null
  }
}

interface MacroData {
  sp500: number | null
  sp500_variacao: number | null
  ibov: number | null
  ibov_variacao: number | null
  dolar: number | null
  dolar_variacao: number | null
}

function RegimeBadge({ regime }: { regime: string }) {
  const map: Record<string, { color: string; bg: string; dot: string; label: string }> = {
    BULL: { color: '#00E676', bg: 'rgba(0,230,118,0.08)', dot: '#00E676', label: 'BULL' },
    MISTO: { color: '#FFD740', bg: 'rgba(255,215,64,0.08)', dot: '#FFD740', label: 'MISTO' },
    BEAR: { color: '#FF5252', bg: 'rgba(255,82,82,0.08)', dot: '#FF5252', label: 'BEAR' },
  }
  const s = map[regime] || map.MISTO
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-mono" style={{ background: s.bg, border: `1px solid ${s.color}30`, color: s.color }}>
      <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: s.dot }} />
      {s.label}
    </div>
  )
}

export default function BriefingPage() {
  const { userId } = useStore()
  const [briefing, setBriefing] = useState<BriefingData | null>(null)
  const [macro, setMacro] = useState<MacroData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [initialCheck, setInitialCheck] = useState(true)
  const [streamedText, setStreamedText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const streamedRef = useRef<HTMLDivElement>(null)

  const THINKING_STEPS = [
    'Verificando dados macro em tempo real...',
    'Avaliando S&P 500, IBOV, dólar e VIX...',
    'Lendo sua carteira e posições abertas...',
    'Identificando eventos do calendário econômico...',
    'Cruzando regime de mercado com o seu perfil...',
    'Escrevendo análise do Gestor APEX...',
  ]

  // Ao montar: verifica silenciosamente se já existe briefing hoje
  useEffect(() => {
    const checkExisting = async () => {
      try {
        const [briefingRes, macroRes] = await Promise.all([
          api.get('/briefing/hoje', { params: { check_only: true } }),
          api.get('/market/macro').catch(() => ({ data: null })),
        ])
        setBriefing(briefingRes.data)
        if (macroRes.data) setMacro(macroRes.data)
      } catch {
        // 404 = nenhum briefing hoje — mostra botão de gerar
        api.get('/market/macro').catch(() => null).then((r: any) => { if (r?.data) setMacro(r.data) })
      } finally {
        setInitialCheck(false)
      }
    }
    checkExisting()
  }, [])

  // Scroll automático durante streaming
  useEffect(() => {
    if (isStreaming && streamedRef.current) {
      streamedRef.current.scrollTop = streamedRef.current.scrollHeight
    }
  }, [streamedText, isStreaming])

  // Geração com streaming real — texto aparece token a token
  const streamBriefing = async (force = false) => {
    setError(null)
    setStreamedText('')
    if (force) setBriefing(null)
    setLoading(true)

    // Carrega macro em paralelo se ainda não tiver
    if (!macro) {
      api.get('/market/macro').catch(() => null).then((r: any) => { if (r?.data) setMacro(r.data) })
    }

    try {
      const url = `/api/briefing/stream${force ? '?force=true' : ''}`
      const headers: Record<string, string> = {}
      if (userId) headers['x-user-id'] = userId

      const response = await fetch(url, { headers })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `Erro ${response.status}`)
      }

      setLoading(false)
      setIsStreaming(true)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const t0 = Date.now()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.chunk !== undefined) {
              setStreamedText(prev => prev + data.chunk)
            }
            if (data.done) {
              if (data.briefing) setBriefing(data.briefing)
              setElapsed((Date.now() - t0) / 1000)
              setStreamedText('')
            }
            if (data.error) throw new Error(data.error)
          } catch (parseErr) {
            // ignora linha malformada
          }
        }
      }
    } catch (e: any) {
      setError(e.message || 'Erro ao gerar briefing')
      setLoading(false)
    }
    setIsStreaming(false)
  }

  // Renderizador de markdown leve (bold + bullets + line breaks)
  const renderText = (text: string) =>
    text.split('\n').map((line, i) => {
      const parts = line.split(/\*\*(.*?)\*\*/g)
      return (
        <p key={i} className={line === '' ? 'mb-3' : 'mb-1'}>
          {parts.map((part, j) =>
            j % 2 === 1 ? <strong key={j} style={{ color: '#e2e8f0' }}>{part}</strong> : part
          )}
        </p>
      )
    })

  return (
    <div className="p-8 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sun size={18} style={{ color: '#00E676' }} />
            <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Morning Briefing</h1>
          </div>
          <p className="text-sm" style={{ color: '#64748b' }}>
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>

        {(briefing || isStreaming) && (
          <button
            onClick={() => streamBriefing(true)}
            disabled={loading || isStreaming}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={(loading || isStreaming) ? 'animate-spin' : ''} />
            {(loading || isStreaming) ? 'Gerando...' : 'Atualizar'}
          </button>
        )}
      </div>

      {/* Check inicial silencioso */}
      {initialCheck && (
        <div className="flex items-center gap-2 py-4" style={{ color: '#475569' }}>
          <div className="w-4 h-4 rounded-full border-2 animate-spin"
            style={{ borderColor: '#334155', borderTopColor: '#475569' }} />
          <span className="text-sm">Verificando...</span>
        </div>
      )}

      {/* Tela inicial sem briefing hoje */}
      {!initialCheck && !briefing && !loading && !isStreaming && !error && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          className="apex-card p-10 flex flex-col items-center gap-5 text-center">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <Sun size={26} style={{ color: '#0a0e17' }} />
          </div>
          <div>
            <p className="text-lg font-bold mb-1" style={{ color: '#f1f5f9' }}>Morning Call</p>
            <p className="text-sm" style={{ color: '#64748b' }}>Nenhum briefing gerado hoje. Clique para analisar o mercado agora.</p>
          </div>
          <button onClick={() => streamBriefing(false)} className="btn-primary flex items-center gap-2 text-sm px-6 py-2.5">
            <Sun size={15} />
            Gerar Morning Call
          </button>
        </motion.div>
      )}

      {/* Loading — antes do streaming começar */}
      {loading && !isStreaming && (
        <div className="apex-card p-10 flex flex-col items-center gap-6">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <span className="text-xl font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <ThinkingSteps steps={THINKING_STEPS} intervalMs={2400} color="#00E676" />
        </div>
      )}

      {/* Error */}
      {error && !loading && !isStreaming && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-6 text-center">
          <p className="text-sm mb-4" style={{ color: '#FF5252' }}>{error}</p>
          <button onClick={() => streamBriefing(false)} className="btn-primary">Tentar Novamente</button>
        </motion.div>
      )}

      {/* Macro bar — aparece tão logo tiver dados (inclusive durante streaming) */}
      <AnimatePresence>
        {(briefing || (isStreaming && macro)) && macro && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-4 gap-3 mb-4">
            {/* Dólar */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
                <span className="text-xs font-bold" style={{ color: '#00E676' }}>BRL</span>
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>Dólar</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {(macro?.dolar || briefing?.macro?.dolar) ? `R$ ${Number(macro?.dolar || briefing?.macro?.dolar).toFixed(2)}` : '--'}
                </p>
                {macro?.dolar_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.dolar_variacao >= 0 ? '#FF5252' : '#00E676' }}>
                    {macro.dolar_variacao >= 0 ? '+' : ''}{macro.dolar_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* IBOVESPA */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.08)' }}>
                {(macro?.ibov_variacao ?? 0) >= 0
                  ? <TrendingUp size={14} style={{ color: '#00E676' }} />
                  : <TrendingDown size={14} style={{ color: '#FF5252' }} />}
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>IBOVESPA</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {(macro?.ibov || briefing?.macro?.ibov) ? Number(macro?.ibov || briefing?.macro?.ibov).toLocaleString('pt-BR', { maximumFractionDigits: 0 }) : '--'}
                </p>
                {macro?.ibov_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.ibov_variacao >= 0 ? '#00E676' : '#FF5252' }}>
                    {macro.ibov_variacao >= 0 ? '+' : ''}{macro.ibov_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* S&P 500 */}
            <div className="apex-card p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,188,212,0.08)' }}>
                {(macro?.sp500_variacao ?? 0) >= 0
                  ? <TrendingUp size={14} style={{ color: '#00BCD4' }} />
                  : <TrendingDown size={14} style={{ color: '#FF5252' }} />}
              </div>
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>S&P 500</p>
                <p className="text-sm font-mono font-bold" style={{ color: '#f1f5f9' }}>
                  {macro?.sp500 ? Number(macro.sp500).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '--'}
                </p>
                {macro?.sp500_variacao != null && (
                  <p className="text-xs font-mono" style={{ color: macro.sp500_variacao >= 0 ? '#00E676' : '#FF5252' }}>
                    {macro.sp500_variacao >= 0 ? '+' : ''}{macro.sp500_variacao.toFixed(2)}%
                  </p>
                )}
              </div>
            </div>

            {/* Regime */}
            <div className="apex-card p-4 flex items-center justify-between">
              <div>
                <p className="text-xs" style={{ color: '#64748b' }}>Regime</p>
                <div className="mt-1">
                  <RegimeBadge regime={briefing?.regime || 'MISTO'} />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Streaming — texto aparece ao vivo */}
      {isStreaming && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <span className="text-sm font-medium" style={{ color: '#94a3b8' }}>Gestor APEX</span>
            <div className="ml-auto flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#00E676' }} />
              <span className="text-xs font-mono" style={{ color: '#00E676' }}>gerando ao vivo</span>
            </div>
          </div>
          {/* Texto streamado — sem markdown (pode estar incompleto) */}
          <div ref={streamedRef} className="text-sm leading-relaxed overflow-y-auto" style={{ color: '#f1f5f9', maxHeight: '60vh' }}>
            {streamedText}
            {/* cursor piscante */}
            <span className="inline-block w-0.5 h-4 ml-0.5 align-middle animate-pulse" style={{ background: '#00E676' }} />
          </div>
          {/* Thinking steps durante silêncio */}
          {streamedText.length < 10 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid #1e293b' }}>
              <ThinkingSteps steps={THINKING_STEPS} intervalMs={2400} color="#00E676" />
            </div>
          )}
        </motion.div>
      )}

      {/* Briefing completo */}
      {briefing && !isStreaming && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <span className="text-sm font-medium" style={{ color: '#94a3b8' }}>Gestor APEX</span>
            <div className="ml-auto flex items-center gap-3">
              {elapsed != null && (
                <span className="text-xs font-mono px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                  gerado em {elapsed.toFixed(1)}s
                </span>
              )}
              <span className="text-xs font-mono" style={{ color: '#64748b' }}>
                {briefing.data ? new Date(briefing.data).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
            </div>
          </div>
          <div className="text-sm leading-relaxed" style={{ color: '#f1f5f9' }}>
            {renderText(briefing.conteudo)}
          </div>
        </motion.div>
      )}
    </div>
  )
}



