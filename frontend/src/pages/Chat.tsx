import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, MessageSquare, Wand2, X, Check, AlertTriangle } from 'lucide-react'
import { useStore } from '@/store/useStore'
import api from '@/services/api'

// â”€â”€â”€ Types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface RegularMessage {
  role: 'user' | 'assistant'
  content: string
}

interface ProposalAction {
  tipo: string
  descricao_curta: string
  nova_estrategia: string | null
  nova_alocacao: Record<string, number>
  pode_aplicar: boolean
  motivo_bloqueio: string | null
}

interface ProposalMessage {
  role: 'proposal'
  analise: string
  acao_proposta: ProposalAction | null
  status: 'pendente' | 'aprovado' | 'cancelado'
}

type ChatMessage = RegularMessage | ProposalMessage

function toHistorico(msgs: ChatMessage[]) {
  return msgs
    .filter((m): m is RegularMessage => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role, content: m.content }))
}

// â”€â”€â”€ ProposalCard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ProposalCard({
  msg,
  onApprove,
  onCancel,
  applying,
}: {
  msg: ProposalMessage
  onApprove: () => void
  onCancel: () => void
  applying: boolean
}) {
  const acao = msg.acao_proposta
  const MODULE_PT: Record<string, string> = {
    etfs: 'ETFs', fiis: 'FIIs', renda_fixa: 'Renda Fixa',
    momentum: 'Momentum', wheel: 'Wheel', alpha: 'Alpha',
    dividendos: 'Dividendos', caixa: 'Caixa',
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
        <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
      </div>
      <div className="flex-1 space-y-3">
        {/* Analysis text */}
        <div className="px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap"
          style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b', color: '#f1f5f9' }}>
          {msg.analise}
        </div>

        {/* Proposal card */}
        {acao && msg.status === 'pendente' && (
          <div className="rounded-xl p-4 space-y-3"
            style={{ background: 'rgba(15,23,42,0.8)', border: `1px solid ${acao.pode_aplicar ? 'rgba(0,230,118,0.3)' : 'rgba(255,152,0,0.3)'}` }}>
            <div className="flex items-start gap-2">
              {acao.pode_aplicar
                ? <Wand2 size={15} style={{ color: '#00E676', marginTop: 2, flexShrink: 0 }} />
                : <AlertTriangle size={15} style={{ color: '#FF9800', marginTop: 2, flexShrink: 0 }} />
              }
              <div>
                <p className="text-sm font-semibold" style={{ color: '#f1f5f9' }}>{acao.descricao_curta}</p>
                {acao.nova_estrategia && (
                  <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                    Nova estratÃ©gia: <span style={{ color: '#00E676' }}>APEX {acao.nova_estrategia}</span>
                  </p>
                )}
                {acao.motivo_bloqueio && (
                  <p className="text-xs mt-1" style={{ color: '#FF9800' }}>{acao.motivo_bloqueio}</p>
                )}
              </div>
            </div>

            {/* Allocation mini-table */}
            {acao.nova_alocacao && Object.keys(acao.nova_alocacao).length > 0 && (
              <div className="grid grid-cols-4 gap-1.5">
                {Object.entries(acao.nova_alocacao)
                  .filter(([, v]) => v > 0)
                  .map(([k, v]) => (
                    <div key={k} className="rounded-lg px-2 py-1.5 text-center"
                      style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid #1e293b' }}>
                      <p className="text-xs" style={{ color: '#64748b' }}>{MODULE_PT[k] ?? k}</p>
                      <p className="text-sm font-bold" style={{ color: '#00E676' }}>{v}%</p>
                    </div>
                  ))}
              </div>
            )}

            {/* Action buttons */}
            {acao.pode_aplicar && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={onApprove}
                  disabled={applying}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                  style={{ background: applying ? '#1e293b' : 'linear-gradient(135deg, #00E676, #00BFA5)', color: applying ? '#64748b' : '#0a0e17', cursor: applying ? 'not-allowed' : 'pointer' }}
                >
                  <Check size={13} />
                  {applying ? 'Aplicando...' : 'Aprovar'}
                </button>
                <button
                  onClick={onCancel}
                  disabled={applying}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                  style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', cursor: applying ? 'not-allowed' : 'pointer' }}
                >
                  <X size={13} />
                  Cancelar
                </button>
              </div>
            )}
          </div>
        )}

        {/* Approved / cancelled state */}
        {acao && msg.status !== 'pendente' && (
          <div className="rounded-xl px-4 py-3 text-sm"
            style={{
              background: msg.status === 'aprovado' ? 'rgba(0,230,118,0.06)' : 'rgba(100,116,139,0.08)',
              border: msg.status === 'aprovado' ? '1px solid rgba(0,230,118,0.15)' : '1px solid #1e293b',
              color: msg.status === 'aprovado' ? '#00E676' : '#64748b',
            }}>
            {msg.status === 'aprovado' ? 'âœ“ MudanÃ§a aplicada com sucesso.' : 'âœ— Proposta cancelada.'}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// â”€â”€â”€ Main page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function ChatPage() {
  const setStrategy = useStore((s) => s.setStrategy)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingText, setStreamingText] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [proposalMode, setProposalMode] = useState(false)
  const [applyingIdx, setApplyingIdx] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  // â”€â”€â”€ Send normal message (streaming) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage: RegularMessage = { role: 'user', content: input }
    const historico = toHistorico([...messages])

    setMessages((m) => [...m, userMessage])
    setInput('')
    setLoading(true)
    setStreamingText('')

    try {
      const resp = await fetch('/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensagem: input, historico }),
      })
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let full = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        full += decoder.decode(value, { stream: true })
        setStreamingText(full)
      }
      setMessages((m) => [...m, { role: 'assistant', content: full }])
    } catch {
      setMessages((m) => [...m, { role: 'assistant', content: 'Erro ao conectar com o gestor.' }])
    } finally {
      setLoading(false)
      setStreamingText('')
    }
  }

  // â”€â”€â”€ Send proposal (non-streaming) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const sendProposal = async () => {
    if (!input.trim() || loading) return

    const userMessage: RegularMessage = { role: 'user', content: `[Proposta] ${input}` }
    setMessages((m) => [...m, userMessage])
    setInput('')
    setLoading(true)
    setProposalMode(false)

    try {
      const { data } = await api.post('/chat/proposta', { descricao: input })
      const propMsg: ProposalMessage = {
        role: 'proposal',
        analise: data.analise,
        acao_proposta: data.acao_proposta,
        status: 'pendente',
      }
      setMessages((m) => [...m, propMsg])
    } catch {
      setMessages((m) => [...m, { role: 'assistant', content: 'Erro ao analisar proposta.' }])
    } finally {
      setLoading(false)
    }
  }

  // â”€â”€â”€ Approve proposal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const approveProposal = async (idx: number) => {
    const msg = messages[idx] as ProposalMessage
    if (!msg.acao_proposta) return
    setApplyingIdx(idx)
    try {
      const payload: Record<string, unknown> = {}
      if (msg.acao_proposta.nova_estrategia) payload.nova_estrategia = msg.acao_proposta.nova_estrategia
      if (msg.acao_proposta.nova_alocacao) payload.nova_alocacao = msg.acao_proposta.nova_alocacao
      await api.patch('/portfolio/alocacao', payload)
      if (msg.acao_proposta.nova_estrategia) {
        setStrategy(msg.acao_proposta.nova_estrategia as any)
      }
      setMessages((m) =>
        m.map((item, i) =>
          i === idx ? { ...(item as ProposalMessage), status: 'aprovado' as const } : item
        )
      )
    } catch {
      setMessages((m) => [...m, { role: 'assistant', content: 'Erro ao aplicar mudanÃ§a. Tente novamente.' }])
    } finally {
      setApplyingIdx(null)
    }
  }

  const cancelProposal = (idx: number) => {
    setMessages((m) =>
      m.map((item, i) =>
        i === idx ? { ...(item as ProposalMessage), status: 'cancelado' as const } : item
      )
    )
  }

  const handleSend = () => (proposalMode ? sendProposal() : sendMessage())

  return (
    <div className="flex flex-col h-screen p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-6 flex-shrink-0">
        <MessageSquare size={18} style={{ color: '#00E676' }} />
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Chat com o Gestor</h1>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="apex-card p-6 text-center"
          >
            <div className="w-12 h-12 rounded-xl mx-auto mb-4 flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="text-xl font-bold" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <h3 className="font-semibold mb-2" style={{ color: '#f1f5f9' }}>Gestor APEX pronto</h3>
            <p className="text-sm" style={{ color: '#64748b' }}>
              Pergunte qualquer coisa sobre seu portfÃ³lio, peÃ§a anÃ¡lise de ativos, discuta estratÃ©gias.
            </p>
            <div className="grid grid-cols-1 gap-2 mt-5 text-left">
              {[
                'Como estÃ¡ meu portfÃ³lio hoje?',
                'Analise PETR4 para mim',
                'Vale a pena comprar BOVA11 agora?',
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-left px-3 py-2.5 rounded-lg text-sm transition-all"
                  style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(0,230,118,0.2)'; e.currentTarget.style.color = '#f1f5f9' }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#1e293b'; e.currentTarget.style.color = '#94a3b8' }}
                >
                  {s}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, i) => {
            if (msg.role === 'proposal') {
              return (
                <ProposalCard
                  key={i}
                  msg={msg}
                  onApprove={() => approveProposal(i)}
                  onCancel={() => cancelProposal(i)}
                  applying={applyingIdx === i}
                />
              )
            }
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                    <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
                  </div>
                )}
                <div
                  className="max-w-[85%] px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap"
                  style={{
                    background: msg.role === 'user' ? 'rgba(0,230,118,0.08)' : 'rgba(15,23,42,0.6)',
                    border: msg.role === 'user' ? '1px solid rgba(0,230,118,0.2)' : '1px solid #1e293b',
                    color: '#f1f5f9',
                  }}
                >
                  {msg.content}
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>

        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
            <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <div className="max-w-[85%] px-4 py-3 rounded-xl text-sm leading-relaxed"
              style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b', color: '#f1f5f9' }}>
              {streamingText ? (
                <span className="whitespace-pre-wrap cursor-blink">{streamingText}</span>
              ) : (
                <div className="flex gap-1">
                  {[0, 1, 2].map((j) => (
                    <div key={j} className="w-1.5 h-1.5 rounded-full animate-bounce"
                      style={{ background: '#00E676', animationDelay: `${j * 0.15}s` }} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Proposal mode banner */}
      <AnimatePresence>
        {proposalMode && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-2 flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
            style={{ background: 'rgba(0,230,118,0.06)', border: '1px solid rgba(0,230,118,0.15)', color: '#00E676' }}
          >
            <Wand2 size={12} />
            Modo proposta â€” descreva a mudanÃ§a que quer fazer no portfÃ³lio para anÃ¡lise da IA.
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <div className="flex gap-2 flex-shrink-0">
        {/* Proposal mode toggle */}
        <button
          onClick={() => setProposalMode((v) => !v)}
          title="Propor mudanÃ§a no portfÃ³lio"
          disabled={loading}
          className="w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0"
          style={{
            background: proposalMode ? 'rgba(0,230,118,0.12)' : 'rgba(30,41,59,0.8)',
            border: proposalMode ? '1px solid rgba(0,230,118,0.3)' : '1px solid #1e293b',
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          <Wand2 size={15} style={{ color: proposalMode ? '#00E676' : '#64748b' }} />
        </button>

        <input
          className="apex-input flex-1"
          placeholder={proposalMode ? 'Descreva a mudanÃ§a que quer fazer...' : 'Pergunte ao gestor APEX...'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
          style={proposalMode ? { borderColor: 'rgba(0,230,118,0.2)' } : {}}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0"
          style={{
            background: input.trim() && !loading ? 'linear-gradient(135deg, #00E676, #00BFA5)' : '#1e293b',
            cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
          }}
        >
          <Send size={16} style={{ color: input.trim() && !loading ? '#0a0e17' : '#64748b' }} />
        </button>
      </div>
    </div>
  )
}

