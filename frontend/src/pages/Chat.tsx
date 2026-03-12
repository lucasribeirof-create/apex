import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, MessageSquare, Wand2, X, Check, AlertTriangle, Trash2, Zap, Square, Copy, CheckCheck } from 'lucide-react'
import { useStore, ChatMessage, ChatRegularMessage, ChatProposalMessage, ChatProposalAction } from '@/store/useStore'
import api from '@/services/api'
import { useCostEstimates } from '@/hooks/useCostEstimates'

// ─── Usage extraction ────────────────────────────────────────────────────────
interface UsageInfo { in: number; out: number; cost: number; provider: string; model: string }

function extractUsage(text: string): { cleanText: string; usage: UsageInfo | null } {
  const idx = text.lastIndexOf('\n<!-- APEX_USAGE:')
  if (idx === -1) return { cleanText: text, usage: null }
  const jsonStart = idx + '\n<!-- APEX_USAGE:'.length
  const jsonEnd = text.indexOf(' -->', jsonStart)
  if (jsonEnd === -1) return { cleanText: text, usage: null }
  try {
    const usage = JSON.parse(text.slice(jsonStart, jsonEnd))
    return { cleanText: text.slice(0, idx), usage }
  } catch { return { cleanText: text, usage: null } }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

// ─── Copy button ─────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={handleCopy} className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-white/5"
      title="Copiar resposta">
      {copied ? <CheckCheck size={12} style={{ color: '#00E676' }} /> : <Copy size={12} style={{ color: '#64748b' }} />}
    </button>
  )
}

// ─── Markdown renderer (v2 — code blocks, tables, italic, numbered lists) ──

function inlineFormat(text: string): React.ReactNode {
  // Split by inline code first, then process bold/italic in non-code segments
  const codeParts = text.split(/(`[^`]+`)/g)
  return <>{codeParts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={i} className="px-1.5 py-0.5 rounded text-xs font-mono"
        style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676' }}>{part.slice(1, -1)}</code>
    }
    // Bold + italic
    const segments = part.split(/(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*[^*]+\*)/g)
    return <span key={i}>{segments.map((seg, j) => {
      if (seg.startsWith('***') && seg.endsWith('***'))
        return <strong key={j} style={{ color: '#f1f5f9', fontWeight: 600, fontStyle: 'italic' }}>{seg.slice(3, -3)}</strong>
      if (seg.startsWith('**') && seg.endsWith('**'))
        return <strong key={j} style={{ color: '#f1f5f9', fontWeight: 600 }}>{seg.slice(2, -2)}</strong>
      if (seg.startsWith('*') && seg.endsWith('*') && seg.length > 2)
        return <em key={j} style={{ color: '#cbd5e1' }}>{seg.slice(1, -1)}</em>
      return <span key={j}>{seg}</span>
    })}</span>
  })}</>
}

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let key = 0
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Code block (```)
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      i++ // skip closing ```
      nodes.push(
        <div key={key++} className="my-2 rounded-lg overflow-hidden" style={{ border: '1px solid #1e293b' }}>
          {lang && <div className="px-3 py-1 text-[10px] font-mono" style={{ background: 'rgba(0,0,0,0.4)', color: '#64748b' }}>{lang}</div>}
          <pre className="px-3 py-2 text-xs font-mono overflow-x-auto leading-relaxed" style={{ background: 'rgba(0,0,0,0.3)', color: '#e2e8f0' }}>
            {codeLines.join('\n')}
          </pre>
        </div>
      )
      continue
    }

    // Empty line
    if (!line.trim()) {
      nodes.push(<div key={key++} className="h-2" />)
      i++
      continue
    }

    // Headers
    if (/^#{1,3} /.test(line)) {
      const level = (line.match(/^(#+) /) || ['', '#'])[1].length
      const content = line.replace(/^#+\s/, '')
      const sizes = ['text-base', 'text-sm', 'text-sm']
      nodes.push(
        <p key={key++} className={`font-semibold mt-3 mb-1 ${sizes[Math.min(level - 1, 2)]}`}
          style={{ color: '#00E676' }}>
          {inlineFormat(content)}
        </p>
      )
      i++
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      nodes.push(
        <div key={key++} className="my-1 pl-3 py-1" style={{ borderLeft: '2px solid #00E676', color: '#94a3b8' }}>
          {inlineFormat(line.slice(2))}
        </div>
      )
      i++
      continue
    }

    // Table (detect by |)
    if (line.includes('|') && line.trim().startsWith('|')) {
      const tableRows: string[] = []
      while (i < lines.length && lines[i].includes('|')) {
        const row = lines[i].trim()
        // Skip separator rows like |---|---|
        if (!/^\|[\s-:|]+\|$/.test(row)) {
          tableRows.push(row)
        }
        i++
      }
      if (tableRows.length > 0) {
        const parseRow = (row: string) =>
          row.split('|').filter(c => c.trim()).map(c => c.trim())
        const header = parseRow(tableRows[0])
        const body = tableRows.slice(1).map(parseRow)
        nodes.push(
          <div key={key++} className="my-2 overflow-x-auto rounded-lg" style={{ border: '1px solid #1e293b' }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: 'rgba(0,0,0,0.3)' }}>
                  {header.map((h, hi) => <th key={hi} className="px-3 py-1.5 text-left font-semibold" style={{ color: '#00E676' }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {body.map((row, ri) => (
                  <tr key={ri} style={{ borderTop: '1px solid #1e293b' }}>
                    {row.map((cell, ci) => <td key={ci} className="px-3 py-1.5" style={{ color: '#cbd5e1' }}>{inlineFormat(cell)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      continue
    }

    // Numbered list
    if (/^\d+\.\s/.test(line)) {
      const num = line.match(/^(\d+)\.\s/)![1]
      const content = line.replace(/^\d+\.\s/, '')
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5">
          <span className="text-xs font-mono w-4 text-right flex-shrink-0" style={{ color: '#00E676' }}>{num}.</span>
          <span>{inlineFormat(content)}</span>
        </div>
      )
      i++
      continue
    }

    // Unordered list
    if (/^[-•*] /.test(line)) {
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5">
          <span style={{ color: '#00E676', flexShrink: 0 }}>•</span>
          <span>{inlineFormat(line.replace(/^[-•*] /, ''))}</span>
        </div>
      )
      i++
      continue
    }

    // Regular paragraph
    nodes.push(<p key={key++} className="leading-relaxed">{inlineFormat(line)}</p>)
    i++
  }
  return nodes
}

function MessageText({ content }: { content: string }) {
  return <div className="text-sm space-y-0.5">{renderMarkdown(content)}</div>
}


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

// ChatMessage re-exported from store (types kept local for compatibility)

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
    dividendos: 'Dividendos', teses: 'Teses', caixa: 'Caixa',
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
        <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
      </div>
      <div className="flex-1 space-y-3">
        {/* Analysis text */}
        <div className="px-4 py-3 rounded-xl"
          style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b', color: '#f1f5f9' }}>
          <MessageText content={msg.analise} />
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
  const setStrategy     = useStore((s) => s.setStrategy)
  const messages        = useStore((s) => s.chatMessages)
  const setChatMessages = useStore((s) => s.setChatMessages)
  const clearChat       = useStore((s) => s.clearChat)
  const addTokenUsage   = useStore((s) => s.addTokenUsage)
  const { format: fmtCost } = useCostEstimates()
  const chatCost = fmtCost('chat')
  const [streamingText, setStreamingText] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [proposalMode, setProposalMode] = useState(false)
  const [applyingIdx, setApplyingIdx] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Helper that mirrors the setState(fn) pattern but writes to store
  const setMessages = (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
    const current = useStore.getState().chatMessages
    const next = typeof updater === 'function' ? updater(current) : updater
    setChatMessages(next)
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  // Auto-resize textarea
  const adjustTextarea = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [])

  useEffect(adjustTextarea, [input, adjustTextarea])

  // Stop streaming
  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  // â”€â”€â”€ Send normal message (streaming) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage: RegularMessage = { role: 'user', content: input }
    const historico = toHistorico([...messages])

    setMessages((m) => [...m, userMessage])
    setInput('')
    setLoading(true)
    setStreamingText('')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const resp = await fetch('/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensagem: input, historico }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let full = ''
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          full += decoder.decode(value, { stream: true })
          setStreamingText(full)
        }
      } catch (e: any) {
        if (e.name === 'AbortError') {
          // User stopped generation — save partial text
        } else throw e
      }
      const { cleanText, usage } = extractUsage(full)
      if (usage) addTokenUsage(usage.in, usage.out, usage.cost)
      setMessages((m) => [...m, { role: 'assistant', content: cleanText || full, usage }])
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setMessages((m) => [...m, { role: 'assistant', content: 'Erro ao conectar com o gestor.' }])
      }
    } finally {
      setLoading(false)
      setStreamingText('')
      abortRef.current = null
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
      // Confirmar mudança ao user
      setMessages((m) => [...m, { role: 'assistant', content: '✅ Mudança aplicada com sucesso. O portfólio foi atualizado.' }])
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

  // ─── Dynamic suggestions ─────────────────────────────────────────────────
  const [suggestions, setSuggestions] = useState<string[]>([
    'Como est\u00e1 meu portf\u00f3lio hoje?',
    'Qual a sua leitura de mercado agora?',
    'O que voc\u00ea mudaria no meu portf\u00f3lio?',
  ])

  useEffect(() => {
    const buildSuggestions = async () => {
      try {
        const posRes = await api.get('/portfolio/posicoes')
        const posicoes = Array.isArray(posRes.data) ? posRes.data : posRes.data?.posicoes ?? []
        const teses = posicoes.filter((p: any) => p.modulo === 'teses')

        const sugs: string[] = []

        // Sugest\u00f5es baseadas nas teses cadastradas
        if (teses.length > 0) {
          const t = teses[0]
          sugs.push(`Analise minha tese em ${t.ticker} \u2014 ainda faz sentido?`)
        }
        if (teses.length > 1) {
          sugs.push(`Compare as teses de ${teses[0].ticker} e ${teses[1].ticker}`)
        }

        // Sugest\u00f5es baseadas nos m\u00f3dulos ativos
        const modulos = [...new Set(posicoes.map((p: any) => p.modulo).filter(Boolean))]
        if (modulos.includes('momentum')) sugs.push('Como est\u00e3o minhas posi\u00e7\u00f5es de momentum?')
        if (modulos.includes('fiis')) sugs.push('Os FIIs est\u00e3o sofrendo com os juros?')
        if (modulos.includes('alpha')) sugs.push('Alguma posi\u00e7\u00e3o Alpha em risco hoje?')

        // Sempre inclui esta
        sugs.push('Como est\u00e1 meu portf\u00f3lio hoje?')
        sugs.push('O que voc\u00ea mudaria no meu portf\u00f3lio agora?')

        setSuggestions(sugs.slice(0, 4))
      } catch {
        // mant\u00e9m sugest\u00f5es padr\u00e3o
      }
    }
    buildSuggestions()
  }, [])

  return (
    <div className="flex flex-col h-screen p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-6 flex-shrink-0">
        <MessageSquare size={18} style={{ color: '#00E676' }} />
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Chat com o Gestor</h1>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444' }}
            title="Limpar conversa"
          >
            <Trash2 size={12} />
            Limpar
          </button>
        )}
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
              {suggestions.map((s) => (
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
                className={`flex gap-3 group ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-1" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
                    <span className="text-xs font-bold" style={{ color: '#0a0e17' }}>A</span>
                  </div>
                )}
                <div
                  className="max-w-[85%] px-4 py-3 rounded-xl text-sm leading-relaxed"
                  style={{
                    background: msg.role === 'user' ? 'rgba(0,230,118,0.08)' : 'rgba(15,23,42,0.6)',
                    border: msg.role === 'user' ? '1px solid rgba(0,230,118,0.2)' : '1px solid #1e293b',
                    color: '#f1f5f9',
                  }}
                >
                  {msg.role === 'user'
                    ? <span className="whitespace-pre-wrap">{msg.content}</span>
                    : <MessageText content={msg.content} />}
                  {msg.role === 'assistant' && (
                    <div className="mt-1.5 flex items-center gap-2">
                      {(msg as ChatRegularMessage).usage && (
                        <div className="text-[10px] flex items-center gap-1.5" style={{ color: '#475569' }}>
                          <Zap size={9} />
                          <span>{formatTokens((msg as ChatRegularMessage).usage!.in + (msg as ChatRegularMessage).usage!.out)} tokens</span>
                          <span>•</span>
                          <span>{(msg as ChatRegularMessage).usage!.cost > 0 ? `$${(msg as ChatRegularMessage).usage!.cost.toFixed(4)}` : 'grátis'}</span>
                          <span>•</span>
                          <span>{(msg as ChatRegularMessage).usage!.provider}</span>
                        </div>
                      )}
                      <CopyButton text={msg.content} />
                    </div>
                  )}
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
                <MessageText content={streamingText} />
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
      <div className="flex gap-2 flex-shrink-0 items-end">
        {/* Proposal mode toggle */}
        <button
          onClick={() => setProposalMode((v) => !v)}
          title="Propor mudança no portfólio"
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

        <textarea
          ref={textareaRef}
          className="apex-input flex-1 resize-none"
          placeholder={proposalMode ? 'Descreva a mudança que quer fazer...' : 'Pergunte ao gestor APEX...'}
          value={input}
          rows={1}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          style={{
            ...(proposalMode ? { borderColor: 'rgba(0,230,118,0.2)' } : {}),
            maxHeight: 160,
            minHeight: 44,
          }}
        />

        {/* Stop or Send button */}
        {loading ? (
          <button
            onClick={stopStreaming}
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0"
            style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', cursor: 'pointer' }}
            title="Parar geração"
          >
            <Square size={14} style={{ color: '#ef4444' }} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0"
            style={{
              background: input.trim() ? 'linear-gradient(135deg, #00E676, #00BFA5)' : '#1e293b',
              cursor: input.trim() ? 'pointer' : 'not-allowed',
            }}
          >
            <Send size={16} style={{ color: input.trim() ? '#0a0e17' : '#64748b' }} />
          </button>
        )}
        {chatCost && <span style={{ fontSize: 10, color: '#475569', flexShrink: 0 }}>{chatCost}</span>}
      </div>
    </div>
  )
}

