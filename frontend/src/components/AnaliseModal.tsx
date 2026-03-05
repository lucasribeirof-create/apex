/**
 * Modal de análise de posição com chat contínuo.
 *
 * Fase 1 — streaming da análise inicial via GET /chat/analisar-posicao/{id}
 * Fase 2 — chat: usuário responde, discute, justifica via POST /chat/
 *
 * Painel de Tese: edita e salva a tese via PATCH /portfolio/posicoes/{id}.
 */
import { useEffect, useRef, useState, KeyboardEvent } from 'react'
import { X, BrainCircuit, Loader2, Send, BookText, Check, ChevronDown, ChevronUp, FlaskConical, Lightbulb, Download } from 'lucide-react'
import DOMPurify from 'dompurify'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Markdown ─────────────────────────────────────────────────────────────────
function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<span class="block text-green-400 font-bold text-sm mt-3">$1</span>')
    .replace(/^## (.+)$/gm, '<span class="block text-green-400 font-bold mt-3">$1</span>')
    .replace(/^# (.+)$/gm, '<span class="block text-green-300 font-bold text-base mt-3">$1</span>')
    .replace(/^- (.+)$/gm, '<span class="block pl-3 before:content-[\'•\'] before:text-green-400 before:mr-2">$1</span>')
    .replace(/\n{2,}/g, '</p><p class="mt-2">')
    .replace(/\n/g, '<br/>')
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface Mensagem {
  role: 'assistant' | 'user'
  content: string
  streaming?: boolean
}

interface AnaliseModalProps {
  positionId: number
  ticker: string
  modulo: string
  tese?: string | null
  onClose: () => void
  onTeseSalva?: (novaTese: string) => void
}

const MODULO_LABEL: Record<string, string> = {
  teses: 'Tese DCA', momentum: 'Momentum', alpha: 'Alpha',
  wheel: 'Wheel', fiis: 'FIIs', etfs: 'ETFs',
  dividendos: 'Dividendos', renda_fixa: 'Renda Fixa',
}

// ─── Cache de análises em memória (sobrevive close/reopen, limpa no refresh) ──
interface AnaliseCache {
  mensagens: Mensagem[]
  fase: 'analisando' | 'chat'
}
const analiseCache = new Map<number, AnaliseCache>()

// ─── Componente ───────────────────────────────────────────────────────────────
export default function AnaliseModal({
  positionId, ticker, modulo, tese, onClose, onTeseSalva,
}: AnaliseModalProps) {
  const { portfolioAtivo, userId } = useStore()
  const isSimulada = portfolioAtivo?.tipo === 'simulada'
  const isTese = portfolioAtivo?.tipo === 'tese'
  // Restaura do cache se disponível
  const cached = analiseCache.get(positionId)
  const [fase, setFase] = useState<'analisando' | 'chat'>(cached?.fase ?? 'analisando')
  const [mensagens, setMensagens] = useState<Mensagem[]>(cached?.mensagens ?? [])
  const [input, setInput] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const hadCache = useRef(!!cached)

  // Painel de tese
  const [teseAberta, setTeseAberta] = useState(false)
  const [teseTexto, setTeseTexto] = useState(tese || '')
  const [salvandoTese, setSalvandoTese] = useState(false)
  const [teseSalva, setTeseSalva] = useState(false)

  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const cancelRef = useRef(false)

  // ─── Persiste no cache sempre que mensagens mudam (não-streaming) ───────────
  useEffect(() => {
    const hasStreaming = mensagens.some(m => m.streaming)
    if (mensagens.length > 0 && !hasStreaming) {
      analiseCache.set(positionId, { mensagens, fase })
    }
  }, [mensagens, fase, positionId])

  // ─── Fase 1: análise inicial (pula se cache existe) ──────────────────────────
  useEffect(() => {
    if (hadCache.current) return          // já restaurou do cache
    cancelRef.current = false
    let texto = ''
    setMensagens([{ role: 'assistant', content: '', streaming: true }])

    async function fetchStream() {
      try {
        const _headers: Record<string, string> = {}
        if (userId) _headers['x-user-id'] = String(userId)
        const res = await fetch(`${API_BASE}/chat/analisar-posicao/${positionId}`, { headers: _headers })
        if (!res.ok) {
          const j = await res.json().catch(() => ({ detail: 'Erro desconhecido' }))
          setErro(j.detail || 'Erro ao analisar posição')
          setMensagens([])
          return
        }
        const reader = res.body!.getReader()
        const decoder = new TextDecoder('utf-8')

        while (true) {
          const { done, value } = await reader.read()
          if (done || cancelRef.current) break
          texto += decoder.decode(value, { stream: true })
          const snap = texto
          setMensagens([{ role: 'assistant', content: snap, streaming: true }])
        }

        if (!cancelRef.current) {
          setMensagens([{ role: 'assistant', content: texto, streaming: false }])
          setFase('chat')
          setTimeout(() => inputRef.current?.focus(), 100)
        }
      } catch (e: any) {
        if (!cancelRef.current) {
          setErro(e.message || 'Falha na conexão')
          setMensagens([])
        }
      }
    }

    fetchStream()
    return () => { cancelRef.current = true }
  }, [positionId])

  // ─── Fase 2: enviar mensagem do usuário ──────────────────────────────────────
  const enviarMensagem = async () => {
    const texto = input.trim()
    if (!texto || enviando) return

    setInput('')
    setEnviando(true)

    const historicoAtual = mensagens.map(m => ({ role: m.role, content: m.content }))
    const novaMsgUser: Mensagem = { role: 'user', content: texto }
    const novaMsgAI: Mensagem = { role: 'assistant', content: '', streaming: true }
    setMensagens(prev => [...prev, novaMsgUser, novaMsgAI])

    setTimeout(() => {
      if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }, 50)

    try {
      const _chatHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
      if (userId) _chatHeaders['x-user-id'] = String(userId)
      const res = await fetch(`${API_BASE}/chat/`, {
        method: 'POST',
        headers: _chatHeaders,
        body: JSON.stringify({ mensagem: texto, historico: historicoAtual }),
      })

      if (!res.ok) {
        const j = await res.json().catch(() => ({ detail: 'Erro' }))
        setMensagens(prev => {
          const arr = [...prev]
          arr[arr.length - 1] = { role: 'assistant', content: `Erro: ${j.detail}`, streaming: false }
          return arr
        })
        setEnviando(false)
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder('utf-8')
      let resposta = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        resposta += decoder.decode(value, { stream: true })
        const snap = resposta
        setMensagens(prev => {
          const arr = [...prev]
          arr[arr.length - 1] = { role: 'assistant', content: snap, streaming: true }
          return arr
        })
        setTimeout(() => {
          if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
        }, 0)
      }

      setMensagens(prev => {
        const arr = [...prev]
        arr[arr.length - 1] = { role: 'assistant', content: resposta, streaming: false }
        return arr
      })
    } catch (e: any) {
      setMensagens(prev => {
        const arr = [...prev]
        arr[arr.length - 1] = { role: 'assistant', content: `Erro: ${e.message}`, streaming: false }
        return arr
      })
    }

    setEnviando(false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      enviarMensagem()
    }
  }

  // ─── Salvar tese ─────────────────────────────────────────────────────────────
  const salvarTese = async () => {
    if (!teseTexto.trim()) return
    setSalvandoTese(true)
    try {
      await api.patch(`/portfolio/posicoes/${positionId}`, { tese: teseTexto.trim() })
      setTeseSalva(true)
      onTeseSalva?.(teseTexto.trim())
      setTimeout(() => setTeseSalva(false), 2500)
    } catch { /* silent */ }
    setSalvandoTese(false)
  }

  // ─── Download conversa ───────────────────────────────────────────────────────
  const downloadConversa = () => {
    if (mensagens.length === 0) return
    const data = new Date().toLocaleDateString('pt-BR').replace(/\//g, '-')
    const hora = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }).replace(':', 'h')
    let md = `# Análise APEX — ${ticker}\n`
    md += `**Módulo:** ${MODULO_LABEL[modulo] ?? modulo}  \n`
    md += `**Data:** ${data} ${hora}  \n\n---\n\n`
    for (const m of mensagens) {
      if (m.role === 'user') {
        md += `**Você:**\n${m.content}\n\n`
      } else {
        md += `**APEX Manager:**\n${m.content}\n\n`
      }
    }
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `APEX_${ticker}_${data}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      <div
        className="relative flex flex-col rounded-xl shadow-2xl w-full"
        style={{
          maxWidth: '680px',
          height: 'min(82vh, 760px)',
          background: '#0d1117',
          border: '1px solid #1e293b',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0" style={{ borderColor: '#1e293b' }}>
          <div className="flex items-center gap-3">
            {isTese
              ? <Lightbulb className="w-5 h-5" style={{ color: '#AA00FF' }} />
              : isSimulada
              ? <FlaskConical className="w-5 h-5" style={{ color: '#FF9800' }} />
              : <BrainCircuit className="w-5 h-5" style={{ color: '#00E676' }} />
            }
            <div>
              <div className="flex items-center gap-2">
                <p className="font-bold text-white">{ticker}</p>
                {isSimulada && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,152,0,0.12)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.25)' }}>SIMULADA</span>
                )}
                {isTese && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(170,0,255,0.12)', color: '#AA00FF', border: '1px solid rgba(170,0,255,0.25)' }}>TESE</span>
                )}
              </div>
              <p className="text-xs" style={{ color: '#64748b' }}>
                {MODULO_LABEL[modulo] ?? modulo}
                {fase === 'chat' && (
                  <span className="ml-2" style={{ color: isTese ? '#AA00FF' : isSimulada ? '#FF9800' : '#00E676' }}>• chat ativo</span>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {mensagens.length > 0 && (
              <button
                onClick={downloadConversa}
                title="Download da conversa (.md)"
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: '#64748b' }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#00E676'; (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,230,118,0.08)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = '#64748b'; (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
              >
                <Download size={15} />
              </button>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg transition-colors" style={{ color: '#64748b' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Mensagens */}
        <div ref={bodyRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {erro && <p className="text-sm" style={{ color: '#f87171' }}>{erro}</p>}

          {mensagens.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {m.role === 'assistant' && (
                <div
                  className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-0.5"
                  style={{ background: 'rgba(0,230,118,0.1)', border: '1px solid rgba(0,230,118,0.2)' }}
                >
                  <BrainCircuit size={13} style={{ color: '#00E676' }} />
                </div>
              )}
              <div
                className="text-sm leading-relaxed"
                style={{
                  maxWidth: '88%',
                  color: m.role === 'user' ? '#f1f5f9' : '#e2e8f0',
                  ...(m.role === 'user' ? {
                    background: 'rgba(99,102,241,0.12)',
                    border: '1px solid rgba(99,102,241,0.2)',
                    borderRadius: '12px 12px 2px 12px',
                    padding: '10px 14px',
                  } : {}),
                }}
              >
                {m.role === 'assistant' ? (
                  m.content === '' && m.streaming ? (
                    <div className="flex items-center gap-2" style={{ color: '#64748b' }}>
                      <Loader2 size={13} className="animate-spin" />
                      <span>Analisando…</span>
                    </div>
                  ) : (
                    <>
                      <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderMarkdown(m.content)) }} />
                      {m.streaming && (
                        <span
                          className="inline-block w-1.5 h-4 ml-0.5 animate-pulse"
                          style={{ background: '#00E676', verticalAlign: 'text-bottom' }}
                        />
                      )}
                    </>
                  )
                ) : (
                  <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Painel de Tese (colapsável) */}
        <div className="flex-shrink-0 border-t" style={{ borderColor: '#1e293b' }}>
          <button
            onClick={() => setTeseAberta(!teseAberta)}
            className="w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors"
            style={{ color: teseAberta ? '#00E676' : '#64748b' }}
          >
            <div className="flex items-center gap-2">
              <BookText size={13} />
              <span>{teseTexto ? 'Tese registrada' : 'Registrar tese de investimento'}</span>
              {teseTexto && !teseAberta && (
                <span
                  className="px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}
                >
                  {teseTexto.length > 45 ? teseTexto.slice(0, 45) + '…' : teseTexto}
                </span>
              )}
            </div>
            {teseAberta ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>

          {teseAberta && (
            <div className="px-5 pb-3 space-y-2">
              <textarea
                value={teseTexto}
                onChange={e => setTeseTexto(e.target.value)}
                placeholder="Descreva o fundamento desta posição. Ex: empresa com vantagem competitiva durável, valuation atrativo em múltiplos históricos, catalisador esperado em 12–18 meses…"
                className="w-full text-xs resize-none rounded-lg px-3 py-2.5 outline-none"
                rows={3}
                style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid #1e293b',
                  color: '#e2e8f0',
                  lineHeight: '1.6',
                }}
              />
              <div className="flex items-center justify-between">
                <p className="text-xs" style={{ color: '#475569' }}>
                  A tese é usada pela IA em todas as análises desta posição
                </p>
                <button
                  onClick={salvarTese}
                  disabled={salvandoTese || !teseTexto.trim()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                  style={{
                    background: teseSalva ? 'rgba(0,230,118,0.15)' : 'rgba(0,230,118,0.1)',
                    color: '#00E676',
                    border: '1px solid rgba(0,230,118,0.25)',
                    opacity: (!teseTexto.trim() || salvandoTese) ? 0.5 : 1,
                  }}
                >
                  {salvandoTese ? <Loader2 size={11} className="animate-spin" /> : teseSalva ? <Check size={11} /> : null}
                  {teseSalva ? 'Salvo!' : 'Salvar Tese'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Input de chat — fase 2 */}
        {fase === 'chat' && (
          <div className="flex-shrink-0 border-t px-4 py-3" style={{ borderColor: '#1e293b' }}>
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Responda, questione ou justifique seu ponto de vista… (Enter envia)"
                disabled={enviando}
                className="flex-1 text-sm resize-none rounded-xl px-4 py-2.5 outline-none"
                rows={2}
                style={{
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid',
                  borderColor: input ? '#00E676' : '#1e293b',
                  color: '#f1f5f9',
                  transition: 'border-color 0.15s',
                }}
              />
              <button
                onClick={enviarMensagem}
                disabled={!input.trim() || enviando}
                className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-xl transition-all"
                style={{
                  background: input.trim() ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.04)',
                  color: input.trim() ? '#00E676' : '#475569',
                  border: '1px solid',
                  borderColor: input.trim() ? 'rgba(0,230,118,0.3)' : '#1e293b',
                }}
              >
                {enviando ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
              </button>
            </div>
            <p className="text-xs mt-1 ml-1" style={{ color: '#334155' }}>Shift+Enter para nova linha</p>
          </div>
        )}
      </div>
    </div>
  )
}
