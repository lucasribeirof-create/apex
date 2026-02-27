/**
 * Side panel de análise geral da carteira.
 * Streaming do endpoint GET /chat/analisar-carteira?modulo=xxx
 */
import { useRef, useState } from 'react'
import { X, BrainCircuit, Loader2, Copy, Check } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Markdown simples ─────────────────────────────────────────────────────────
function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<span class="block text-green-400 font-bold text-sm mt-4">$1</span>')
    .replace(/^## (.+)$/gm, '<span class="block text-green-400 font-bold mt-4">$1</span>')
    .replace(/^# (.+)$/gm, '<span class="block text-green-300 font-bold text-base mt-4">$1</span>')
    .replace(/^- (.+)$/gm, '<span class="block pl-4 before:content-[\'•\'] before:text-green-400 before:mr-2">$1</span>')
    .replace(/\n{2,}/g, '</p><p class="mt-3">')
    .replace(/\n/g, '<br/>')
}

// ─── Módulos disponíveis ──────────────────────────────────────────────────────
const MODULOS = [
  { id: 'todos', label: 'Toda a Carteira' },
  { id: 'teses', label: 'Teses' },
  { id: 'momentum', label: 'Momentum' },
  { id: 'alpha', label: 'Alpha' },
  { id: 'fiis', label: 'FIIs' },
  { id: 'etfs', label: 'ETFs' },
  { id: 'dividendos', label: 'Dividendos' },
  { id: 'wheel', label: 'Wheel' },
]

// ─── Props ────────────────────────────────────────────────────────────────────
interface CarteiraPanelProps {
  onClose: () => void
}

// ─── Componente ───────────────────────────────────────────────────────────────
export default function CarteiraPanel({ onClose }: CarteiraPanelProps) {
  const [moduloSelecionado, setModuloSelecionado] = useState('todos')
  const [texto, setTexto] = useState('')
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const cancelRef = useRef(false)

  const iniciarAnalise = async (modulo: string) => {
    cancelRef.current = true      // cancela stream anterior se existir
    await new Promise(r => setTimeout(r, 50))
    cancelRef.current = false

    setTexto('')
    setErro(null)
    setLoading(true)
    setStreaming(false)

    try {
      const url = `${API_BASE}/chat/analisar-carteira${modulo !== 'todos' ? `?modulo=${modulo}` : ''}`
      const res = await fetch(url)
      if (!res.ok) {
        const j = await res.json().catch(() => ({ detail: 'Erro desconhecido' }))
        setErro(j.detail || 'Erro ao analisar carteira')
        setLoading(false)
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder('utf-8')
      setLoading(false)
      setStreaming(true)

      while (true) {
        const { done, value } = await reader.read()
        if (done || cancelRef.current) break
        const chunk = decoder.decode(value, { stream: true })
        setTexto(prev => prev + chunk)
      }
      setStreaming(false)
    } catch (e: any) {
      if (!cancelRef.current) {
        setErro(e.message || 'Falha na conexão')
        setLoading(false)
        setStreaming(false)
      }
    }
  }

  const handleModulo = (id: string) => {
    setModuloSelecionado(id)
    iniciarAnalise(id)
  }

  const handleCopiar = () => {
    navigator.clipboard.writeText(texto)
    setCopiado(true)
    setTimeout(() => setCopiado(false), 2000)
  }

  const moduloLabel = MODULOS.find(m => m.id === moduloSelecionado)?.label ?? moduloSelecionado

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed right-0 top-0 bottom-0 z-50 flex flex-col shadow-2xl"
        style={{ width: 'min(680px, 95vw)', background: '#0d1117', borderLeft: '1px solid #1e293b' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#1e293b' }}>
          <div className="flex items-center gap-3">
            <BrainCircuit className="w-5 h-5" style={{ color: '#00E676' }} />
            <div>
              <p className="font-bold text-white">Diagnóstico da Carteira</p>
              <p className="text-xs" style={{ color: '#64748b' }}>{moduloLabel}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {texto && (
              <button
                onClick={handleCopiar}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all"
                style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}
              >
                {copiado ? <Check size={12} /> : <Copy size={12} />}
                {copiado ? 'Copiado' : 'Copiar'}
              </button>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg transition-colors" style={{ color: '#64748b' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Filtros de módulo */}
        <div className="flex items-center gap-2 px-5 py-3 border-b overflow-x-auto" style={{ borderColor: '#1e293b' }}>
          {MODULOS.map(m => (
            <button
              key={m.id}
              onClick={() => handleModulo(m.id)}
              disabled={loading || streaming}
              className="flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={moduloSelecionado === m.id ? {
                background: 'rgba(0,230,118,0.15)',
                color: '#00E676',
                border: '1px solid rgba(0,230,118,0.3)',
              } : {
                background: 'rgba(255,255,255,0.04)',
                color: '#64748b',
                border: '1px solid transparent',
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Botão iniciar (estado inicial) */}
        {!loading && !streaming && !texto && !erro && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <BrainCircuit className="w-12 h-12 mx-auto mb-4" style={{ color: '#1e293b' }} />
              <p className="text-sm mb-4" style={{ color: '#64748b' }}>
                Selecione um filtro acima ou analise toda a carteira
              </p>
              <button
                onClick={() => iniciarAnalise('todos')}
                className="px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
                style={{ background: 'rgba(0,230,118,0.12)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
              >
                Analisar Carteira Completa
              </button>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-3" style={{ color: '#64748b' }}>
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Analisando carteira…</span>
            </div>
          </div>
        )}

        {/* Erro */}
        {erro && (
          <div className="flex-1 flex items-center justify-center px-6">
            <p className="text-sm text-center" style={{ color: '#f87171' }}>{erro}</p>
          </div>
        )}

        {/* Conteúdo streaming */}
        {(texto || streaming) && !loading && (
          <div className="flex-1 overflow-y-auto px-5 py-4 text-sm leading-relaxed" style={{ color: '#e2e8f0' }}>
            {streaming && (
              <div className="flex items-center gap-2 mb-4" style={{ color: '#64748b' }}>
                <Loader2 className="w-3 h-3 animate-spin" />
                <span className="text-xs">Gerando análise…</span>
              </div>
            )}
            <div
              dangerouslySetInnerHTML={{ __html: renderMarkdown(texto) }}
            />
            {streaming && (
              <span className="inline-block w-1.5 h-4 ml-0.5 animate-pulse" style={{ background: '#00E676', verticalAlign: 'text-bottom' }} />
            )}
          </div>
        )}
      </div>
    </>
  )
}
