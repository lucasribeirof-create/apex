/**
 * Side panel de análise geral da carteira.
 * Streaming do endpoint GET /chat/analisar-carteira?modulo=xxx
 */
import { useRef, useState } from 'react'
import { X, BrainCircuit, Loader2, Copy, Check, Download, Play } from 'lucide-react'
import DOMPurify from 'dompurify'
import { useStore } from '@/store/useStore'
import ThinkingSteps from '@/components/ThinkingSteps'

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
  const { userId, carteiraCache, carteiraModulo, setCarteiraCache, setCarteiraModulo } = useStore()
  const [moduloSelecionado, setModuloSelecionadoLocal] = useState(carteiraModulo)
  const [texto, setTextoLocal] = useState(carteiraCache[carteiraModulo] || '')
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const cancelRef = useRef(false)

  const iniciarAnalise = async (modulo: string) => {
    cancelRef.current = true      // cancela stream anterior se existir
    await new Promise(r => setTimeout(r, 50))
    cancelRef.current = false

    setTextoLocal('')
    setErro(null)
    setLoading(true)
    setStreaming(false)
    setCarteiraCache(modulo, '')

    try {
      const url = `${API_BASE}/chat/analisar-carteira${modulo !== 'todos' ? `?modulo=${modulo}` : ''}`
      const headers: Record<string, string> = {}
      if (userId) headers['x-user-id'] = String(userId)
      const res = await fetch(url, { headers })
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

  // Wrapper: sync local + store per module
  const setTexto = (val: string | ((prev: string) => string)) => {
    setTextoLocal(prev => {
      const next = typeof val === 'function' ? val(prev) : val
      setCarteiraCache(moduloSelecionado, next)
      return next
    })
  }
  const setModuloSelecionado = (id: string) => {
    setModuloSelecionadoLocal(id)
    setCarteiraModulo(id)
    // Restore cached text for this module
    setTextoLocal(carteiraCache[id] || '')
    setErro(null)
  }

  const handleModulo = (id: string) => {
    setModuloSelecionado(id)
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
            <button
              onClick={() => iniciarAnalise(moduloSelecionado)}
              disabled={loading || streaming}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
              style={{
                background: loading || streaming ? 'rgba(0,230,118,0.05)' : 'rgba(0,230,118,0.15)',
                color: loading || streaming ? '#2d6a4f' : '#00E676',
                border: '1px solid rgba(0,230,118,0.3)',
              }}
            >
              {loading || streaming ? <Loader2 size={12} className="animate-spin" /> : <Play size={10} fill="currentColor" />}
              Analisar
            </button>
            {texto && (
              <button
                onClick={() => {
                  const dateStr = new Date().toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' })
                  const htmlBody = texto
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/^### (.+)$/gm, '<h3 style="color:#00E676;font-size:14px;font-weight:bold;margin:16px 0 6px">$1</h3>')
                    .replace(/^## (.+)$/gm, '<h2 style="color:#00E676;font-size:15px;font-weight:bold;margin:20px 0 8px">$1</h2>')
                    .replace(/^# (.+)$/gm, '<h1 style="color:#00E676;font-size:18px;font-weight:bold;margin:20px 0 8px">$1</h1>')
                    .replace(/^- (.+)$/gm, '<li style="margin-left:16px;margin-bottom:4px">$1</li>')
                    .replace(/\n{2,}/g, '</p><p style="margin:0 0 8px">')
                    .replace(/\n/g, '<br/>')
                  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Diagnóstico da Carteira APEX — ${dateStr}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e17; color: #e2e8f0; max-width: 720px; margin: 0 auto; padding: 40px 24px; line-height: 1.7; font-size: 14px; }
    h1 { color: #00E676; font-size: 22px; margin-bottom: 4px; }
    h2 { color: #00E676; font-size: 16px; margin: 20px 0 8px; }
    h3 { color: #00E676; font-size: 14px; margin: 16px 0 6px; }
    strong { color: #f1f5f9; }
    hr { border: none; border-top: 1px solid #1e293b; margin: 20px 0; }
    li { margin-left: 16px; margin-bottom: 4px; }
    .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b; color: #475569; font-size: 11px; text-align: center; }
  </style>
</head>
<body>
  <h1>\u{1F9E0} Diagnóstico da Carteira APEX</h1>
  <div style="color:#64748b;font-size:13px;margin-bottom:24px">${moduloLabel} — ${dateStr}</div>
  <hr>
  <p>${htmlBody}</p>
  <div class="footer">APEX Manager · Gerado automaticamente</div>
</body>
</html>`
                  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `diagnostico-carteira-${dateStr.replace(/\//g, '-')}.html`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all"
                style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}
              >
                <Download size={12} />
                Baixar
              </button>
            )}
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

        {/* Estado vazio */}
        {!loading && !streaming && !texto && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <BrainCircuit className="w-12 h-12 mx-auto mb-4" style={{ color: '#1e293b' }} />
              <p className="text-sm" style={{ color: '#64748b' }}>
                Selecione um módulo e clique em <strong style={{ color: '#00E676' }}>Analisar</strong>
              </p>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
              <span className="text-xl font-bold" style={{ color: '#0a0e17' }}>A</span>
            </div>
            <ThinkingSteps
              steps={[
                'Carregando posições e preços atuais...',
                'Calculando alocação por módulo...',
                'Comparando com a estratégia alvo...',
                'Avaliando concentração e diversificação...',
                'Verificando exposição setorial e correlações...',
                'Analisando performance e P&L de cada posição...',
                'Identificando oportunidades de rebalanceamento...',
                'Escrevendo diagnóstico do Gestor APEX...',
              ]}
              intervalMs={2200}
              color="#00E676"
            />
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
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderMarkdown(texto)) }}
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
