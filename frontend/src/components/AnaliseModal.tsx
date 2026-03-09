/**
 * Modal de análise de posição com chat contínuo.
 *
 * Fase 1 — streaming da análise inicial via GET /chat/analisar-posicao/{id}
 * Fase 2 — chat: usuário responde, discute, justifica via POST /chat/
 *
 * Painel de Tese: edita e salva a tese via PATCH /portfolio/posicoes/{id}.
 */
import { useEffect, useRef, useState, useMemo, KeyboardEvent } from 'react'
import { X, BrainCircuit, Loader2, Send, BookText, Check, ChevronDown, ChevronUp, FlaskConical, Lightbulb, Download, Zap } from 'lucide-react'
import DOMPurify from 'dompurify'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ─── Rich Section-Aware Renderer ──────────────────────────────────────────────

/** Parse score/tag from section headers like `### MACRO GLOBAL | Score: 58/100 | [MISTO]` */
function parseLayerHeader(line: string): { title: string; score: number | null; tag: string; tagColor: string } | null {
  // Match ### TITLE | Score: NN/100 | [TAG]
  const m = line.match(/^###\s+(.+?)\s*\|\s*Score:\s*(\d+)\/100\s*\|\s*\[(.+?)\]/)
  if (m) {
    const tag = m[3].trim()
    return { title: m[1].trim(), score: parseInt(m[2]), tag, tagColor: scoreTagColor(tag) }
  }
  // Match ### TITLE | [TAG] (no score, e.g. ESTRATÉGIA)
  const m2 = line.match(/^###\s+(.+?)\s*\|\s*\[(.+?)\]/)
  if (m2) {
    return { title: m2[1].trim(), score: null, tag: m2[2].trim(), tagColor: scoreTagColor(m2[2].trim()) }
  }
  // Match ### TITLE (no score, no tag e.g. RESUMO, VEREDICTO, ALOCAÇÃO)
  const m3 = line.match(/^###\s+(.+)/)
  if (m3) {
    return { title: m3[1].trim(), score: null, tag: '', tagColor: '' }
  }
  return null
}

/** Parse module sub-headers like `#### ALPHA | RECOMENDADO | primário` */
function parseModuleHeader(line: string): { name: string; status: string; priority: string } | null {
  const m = line.match(/^####\s+(.+?)\s*\|\s*(RECOMENDADO|VIÁVEL|NÃO RECOMENDADO|N\/A)\s*(?:\|\s*(primário|secundário|—|-))?\s*$/i)
  if (m) return { name: m[1].trim(), status: m[2].trim().toUpperCase(), priority: (m[3] || '—').trim() }
  return null
}

function scoreTagColor(tag: string): string {
  const t = tag.toLowerCase()
  if (t.includes('risk-on forte') || t.includes('alta') || t.includes('saudável') || t.includes('favorecido') || t.includes('compra')) return 'green'
  if (t.includes('risk-off') || t.includes('problemático') || t.includes('desfavorecido') || t.includes('venda')) return 'red'
  return 'yellow'
}

function scoreClass(score: number): string {
  if (score >= 70) return 'apex-score-high'
  if (score >= 50) return 'apex-score-mid'
  return 'apex-score-low'
}

function moduleStatusClass(status: string): string {
  if (status === 'RECOMENDADO') return 'apex-mod-rec'
  if (status === 'VIÁVEL') return 'apex-mod-viable'
  if (status === 'NÃO RECOMENDADO') return 'apex-mod-no'
  return 'apex-mod-na'
}

function moduleIcon(status: string): string {
  if (status === 'RECOMENDADO') return '✅'
  if (status === 'VIÁVEL') return '✅'
  if (status === 'NÃO RECOMENDADO') return '⚠️'
  return '—'
}

/** Render inline markdown (bold, sources, highlights) */
function inlineMd(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#f1f5f9">$1</strong>')
    .replace(/\[([A-Za-zÀ-ú0-9.\s]+)\]/g, '<span style="color:#0EA5E9;font-size:11px;font-weight:600">[$1]</span>')
}

/** Check if line is a data group title (ALL CAPS, no colon, 3-35 chars) */
function isDataGroupTitle(line: string): boolean {
  const t = line.trim()
  return t.length >= 3 && t.length <= 35 && /^[A-ZÁÉÍÓÚÂÊÔÀÃÕÇ\s/&]+$/.test(t) && !t.includes(':')
}

/** Parse "- Label: value → context" into structured data */
function parseDataRow(raw: string): { label: string; value: string; context: string; color: string } | null {
  const line = raw.trim().startsWith('- ') ? raw.trim().slice(2) : raw.trim()
  const ci = line.indexOf(':')
  if (ci < 1 || ci > 40) return null
  const label = line.slice(0, ci).trim()
  const rest = line.slice(ci + 1).trim()
  if (!rest) return null

  let value = rest, context = ''
  const am = rest.match(/^(.+?)\s*[→←]\s*(.+)$/)
  if (am) { value = am[1].trim(); context = am[2].trim() }
  else {
    const wm = rest.match(/^(.+?)\s*(⚠️.+)$/)
    if (wm) { value = wm[1].trim(); context = wm[2].trim() }
  }

  const all = (value + ' ' + context).toLowerCase()
  let color = '#E2E8F0'
  if (/excepcional|excelente|saudável|muito saudável|forte|desconto|bom|competitiv|robusto/.test(all) || /^\+\d/.test(value)) color = '#10B981'
  else if (/⚠️|apertad|atenção|estagnado|vulnerável|moderado/.test(all)) color = '#F59E0B'
  else if (/problemátic|ruim|negativ|piorand|fraco/.test(all) || (/^-\d/.test(value) && !/dív|débito/i.test(label))) color = '#EF4444'

  return { label, value, context, color }
}

/** Render a single data-row as an aligned flex div */
function dataRowHtml(dr: { label: string; value: string; context: string; color: string }): string {
  let h = `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid rgba(100,116,139,0.06);font-size:13px">`
  h += `<span style="color:#64748B">${dr.label}</span>`
  h += `<span style="color:${dr.color};font-weight:600;font-family:'JetBrains Mono',monospace;font-size:12px">${inlineMd(dr.value)}`
  if (dr.context) h += ` <span style="color:#64748B;font-weight:400;font-family:'Plus Jakarta Sans',sans-serif;font-size:12px;margin-left:6px">${inlineMd(dr.context)}</span>`
  h += `</span></div>`
  return h
}

/** Render section body: data groups, data rows, setup boxes, risk tags, prose */
function renderBody(bodyLines: string[]): string {
  const html: string[] = []
  let i = 0
  while (i < bodyLines.length) {
    const trimmed = bodyLines[i].trim()
    if (!trimmed) { i++; continue }

    // Data group title (ALL CAPS line)
    if (isDataGroupTitle(trimmed) && !trimmed.startsWith('SETUP')) {
      html.push(`<div style="margin:10px 0">`)
      html.push(`<div style="font-size:11px;font-weight:700;color:#0EA5E9;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">${trimmed}</div>`)
      i++
      while (i < bodyLines.length) {
        const dl = bodyLines[i].trim()
        if (!dl) { i++; continue }
        if (isDataGroupTitle(dl)) break
        const dr = parseDataRow(bodyLines[i])
        if (dr) { html.push(dataRowHtml(dr)); i++ }
        else break
      }
      html.push(`</div>`)
      continue
    }

    // Standalone data row (- Key: value)
    if (trimmed.startsWith('- ') && trimmed.includes(':')) {
      const dr = parseDataRow(trimmed)
      if (dr) { html.push(dataRowHtml(dr)); i++; continue }
    }

    // SETUP or Entry|Stop|Alvo highlighted box
    if (/^SETUP:|Entrada.*\|.*Stop.*\|.*Alvo/i.test(trimmed)) {
      html.push(`<div style="margin:8px 0;padding:8px 12px;background:rgba(14,165,233,0.06);border:1px solid rgba(14,165,233,0.15);border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:12px;color:#0EA5E9;font-weight:600">${trimmed}</div>`)
      i++; continue
    }

    // Risk tag
    if (trimmed.startsWith('⚠️') && /risco/i.test(trimmed)) {
      html.push(`<div style="display:inline-block;margin-top:10px;font-size:11px;color:#F59E0B;font-weight:700;background:rgba(245,158,11,0.08);padding:4px 10px;border-radius:4px">${inlineMd(trimmed)}</div>`)
      i++; continue
    }

    // Bullet point (non-data)
    if (trimmed.startsWith('- ')) {
      html.push(`<div style="padding-left:12px;position:relative;font-size:13px;color:#94A3B8;line-height:1.8"><span style="color:#10B981;position:absolute;left:0">•</span>${inlineMd(trimmed.slice(2))}</div>`)
      i++; continue
    }

    // Prose text
    html.push(`<div style="font-size:13px;color:#94A3B8;line-height:1.8;margin-top:4px">${inlineMd(trimmed)}</div>`)
    i++
  }
  return html.join('\n')
}

/** Render RESUMO with summary tables */
function renderResumoBody(bodyLines: string[]): string {
  const html: string[] = []
  let tableOpen = false
  let hasGroup = false

  for (const raw of bodyLines) {
    const line = raw.trim()
    if (!line) continue

    // Group header (SCORES, MÓDULOS)
    if (isDataGroupTitle(line)) {
      if (tableOpen) { html.push(`</tbody></table>`); tableOpen = false }
      html.push(`<table style="width:100%;border-collapse:collapse;margin:12px 0"><tbody>`)
      tableOpen = true; hasGroup = true
      continue
    }

    // Bullet → table row
    if (line.startsWith('- ') && (tableOpen || !hasGroup)) {
      if (!tableOpen) {
        html.push(`<table style="width:100%;border-collapse:collapse;margin:8px 0"><tbody>`)
        tableOpen = true
      }
      const content = line.slice(2)
      const m = content.match(/\*\*(.+?)\*\*:\s*(.+)/)
      if (m) {
        const label = m[1]
        const rest = m[2]
        // Score row: "58/100 — Status — Comment"
        const sm = rest.match(/^(\d+)\/100\s*—\s*(.+?)\s*—\s*(.+)$/)
        if (sm) {
          const s = parseInt(sm[1])
          const sc = s >= 70 ? '#10B981' : s >= 50 ? '#F59E0B' : '#EF4444'
          html.push(`<tr><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);color:#94A3B8;font-weight:500">${label}</td><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);font-family:'JetBrains Mono',monospace;font-weight:700;text-align:center;width:40px;color:${sc}">${s}</td><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);color:#94A3B8">${inlineMd(sm[3])}</td></tr>`)
        } else {
          // Module row: "✅/⚠️/— STATUS — Comment"
          const ic = rest.match(/^(✅|⚠️|—)/)
          const iconColor = ic?.[1] === '✅' ? '#10B981' : ic?.[1] === '⚠️' ? '#F59E0B' : '#64748B'
          const restClean = rest.replace(/^(✅|⚠️|—)\s*/, '').replace(/^(RECOMENDADO|VIÁVEL|NÃO RECOMENDADO|N\/A)\s*—?\s*/i, '')
          html.push(`<tr><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);color:#94A3B8;font-weight:500">${label}</td><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);text-align:center;color:${iconColor}">${ic?.[1] || ''}</td><td style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);color:#94A3B8">${inlineMd(restClean)}</td></tr>`)
        }
      } else {
        html.push(`<tr><td colspan="3" style="font-size:12px;padding:8px 10px;border-bottom:1px solid rgba(100,116,139,0.06);color:#94A3B8">${inlineMd(content)}</td></tr>`)
      }
      continue
    }

    // VEREDICTO line
    if (/\*\*VEREDICTO\*\*/i.test(line) || /^VEREDICTO/i.test(line)) {
      if (tableOpen) { html.push(`</tbody></table>`); tableOpen = false }
      html.push(`<div style="margin-top:8px;font-size:13px;font-weight:700;color:#10B981">${inlineMd(line.startsWith('- ') ? line.slice(2) : line)}</div>`)
      continue
    }

    // Non-table content
    if (tableOpen) { html.push(`</tbody></table>`); tableOpen = false }
    html.push(`<div style="font-size:13px;color:#94A3B8;margin-top:4px">${inlineMd(line)}</div>`)
  }

  if (tableOpen) html.push(`</tbody></table>`)
  return html.join('\n')
}

/** Main rich renderer — produces AnaliseWeb-style HTML cards */
function renderRichAnalysis(text: string): string {
  const lines = text.split('\n')
  const html: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const layer = parseLayerHeader(line)

    if (layer) {
      const titleUp = layer.title.toUpperCase()
      const isVeredicto = titleUp.includes('VEREDICTO')
      const isModulos = titleUp.includes('MÓDULO')
      const isResumo = titleUp.includes('RESUMO')
      i++

      // ═══ MÓDULOS section ═══
      if (isModulos) {
        const introLines: string[] = []
        while (i < lines.length && !lines[i].startsWith('#### ') && !lines[i].startsWith('### ')) {
          introLines.push(lines[i]); i++
        }
        html.push(`<div style="background:#0C1220;border:1px solid rgba(100,116,139,0.12);border-radius:10px;padding:16px 20px;margin:12px 0">`)
        html.push(`<div style="font-size:13px;font-weight:700;color:#F1F5F9;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px">${inlineMd(layer.title)}</div>`)
        // Module sub-cards
        while (i < lines.length && lines[i].startsWith('#### ')) {
          const mod = parseModuleHeader(lines[i])
          i++
          const modBody: string[] = []
          while (i < lines.length && !lines[i].startsWith('#### ') && !lines[i].startsWith('### ')) {
            modBody.push(lines[i]); i++
          }
          if (mod) {
            const cls = moduleStatusClass(mod.status)
            const bc = cls === 'apex-mod-rec' ? '#10B981' : cls === 'apex-mod-viable' ? '#0EA5E9' : cls === 'apex-mod-no' ? '#64748B' : 'rgba(100,116,139,0.1)'
            const bg = cls === 'apex-mod-rec' ? 'rgba(16,185,129,0.08)' : cls === 'apex-mod-viable' ? 'rgba(14,165,233,0.08)' : cls === 'apex-mod-no' ? 'rgba(100,116,139,0.04)' : 'transparent'
            const op = cls === 'apex-mod-na' ? '0.5' : '1'
            const priBadge = mod.priority !== '—' && mod.priority !== '-' ? ` <span style="font-size:10px;color:#0EA5E9;font-weight:600;margin-left:6px">(${mod.priority})</span>` : ''
            html.push(`<div style="border-radius:8px;padding:12px 16px;margin-bottom:8px;border-left:3px solid ${bc};background:${bg};opacity:${op}">`)
            html.push(`<div style="font-size:13px;font-weight:700;color:#F1F5F9">${moduleIcon(mod.status)} ${mod.name} — ${mod.status}${priBadge}</div>`)
            const mb = modBody.join('\n').trim()
            if (mb) html.push(`<div style="font-size:12px;color:#94A3B8;margin-top:4px;line-height:1.6">${renderBody(mb.split('\n'))}</div>`)
            html.push(`</div>`)
          }
        }
        html.push(`</div>`)
        continue
      }

      // Collect body until next ###
      const bodyLines: string[] = []
      while (i < lines.length && !lines[i].startsWith('### ')) {
        bodyLines.push(lines[i]); i++
      }

      // ═══ VEREDICTO card ═══
      if (isVeredicto) {
        html.push(`<div style="background:linear-gradient(135deg,rgba(16,185,129,0.06),rgba(14,165,233,0.06));border:1px solid rgba(16,185,129,0.15);border-radius:10px;padding:16px 20px;margin:12px 0">`)
        html.push(`<div style="font-size:14px;font-weight:800;color:#10B981;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">${inlineMd(layer.title)}</div>`)
        html.push(`<div style="font-size:13px;color:#94A3B8;line-height:1.8">${renderBody(bodyLines)}</div>`)
        html.push(`</div>`)
        continue
      }

      // ═══ RESUMO section ═══
      if (isResumo) {
        html.push(`<div style="background:#0C1220;border:1px solid rgba(100,116,139,0.12);border-radius:10px;padding:16px 20px;margin:12px 0">`)
        html.push(`<div style="font-size:13px;font-weight:700;color:#F1F5F9;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px">${inlineMd(layer.title)}</div>`)
        html.push(renderResumoBody(bodyLines))
        html.push(`</div>`)
        continue
      }

      // ═══ Standard section card ═══
      html.push(`<div style="background:#0C1220;border:1px solid rgba(100,116,139,0.12);border-radius:10px;padding:16px 20px;margin:12px 0">`)
      // Header row with score badge + tag
      html.push(`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">`)
      html.push(`<div style="display:flex;align-items:center;gap:8px">`)
      html.push(`<span style="font-size:13px;font-weight:700;color:#F1F5F9;text-transform:uppercase;letter-spacing:0.5px">${inlineMd(layer.title)}</span>`)
      if (layer.tag) {
        const tColors: Record<string, [string, string]> = { green: ['rgba(16,185,129,', '#10B981'], red: ['rgba(239,68,68,', '#EF4444'], yellow: ['rgba(245,158,11,', '#F59E0B'] }
        const [tbg, tc] = tColors[layer.tagColor] || tColors.yellow
        html.push(`<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:3px;background:${tbg}0.08);color:${tc}">${layer.tag}</span>`)
      }
      html.push(`</div>`)
      if (layer.score !== null) {
        const sc = scoreClass(layer.score)
        const sColors: Record<string, [string, string]> = { 'apex-score-high': ['rgba(16,185,129,0.08)', '#10B981'], 'apex-score-mid': ['rgba(245,158,11,0.08)', '#F59E0B'], 'apex-score-low': ['rgba(239,68,68,0.08)', '#EF4444'] }
        const [sbg, sco] = sColors[sc] || sColors['apex-score-mid']
        html.push(`<span style="font-size:12px;font-weight:700;padding:3px 10px;border-radius:4px;font-family:'JetBrains Mono',monospace;background:${sbg};color:${sco}">${layer.score}/100</span>`)
      }
      html.push(`</div>`)
      // Body with data groups/rows/prose
      html.push(`<div style="font-size:13px;color:#94A3B8;line-height:1.8">${renderBody(bodyLines)}</div>`)
      html.push(`</div>`)
      continue
    }

    // Non-section content (preamble, etc.)
    const trimmed = line.trim()
    if (trimmed) {
      html.push(`<div style="font-size:13px;color:#94A3B8;line-height:1.8;margin:4px 0">${inlineMd(trimmed)}</div>`)
    }
    i++
  }

  return html.join('\n')
}

/** Fallback: basic markdown for non-analysis messages (chat follow-ups) */
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

/** Detect if text is a 7-layer analysis (has ### headers with Score patterns) */
function isRichAnalysis(text: string): boolean {
  return /^###\s+.+\|\s*Score:/m.test(text)
}

/** Render: use rich renderer for analysis, basic for chat */
function renderContent(text: string): string {
  return isRichAnalysis(text) ? renderRichAnalysis(text) : renderMarkdown(text)
}

/** During streaming, split at last complete block (\n\n) so stable blocks get
 *  full markdown rendering while the in-progress block stays as plain text.
 *  This prevents layout shifts / flickering from partial markdown tokens. */
function splitStableContent(text: string): { stable: string; pending: string } {
  const idx = text.lastIndexOf('\n\n')
  if (idx === -1) return { stable: '', pending: text }
  return { stable: text.slice(0, idx), pending: text.slice(idx + 2) }
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface UsageInfo {
  in: number
  out: number
  cost: number
  provider: string
  model: string
}

function extractUsage(text: string): { cleanText: string; usage: UsageInfo | null } {
  const idx = text.lastIndexOf('\n<!-- APEX_USAGE:')
  if (idx === -1) return { cleanText: text, usage: null }
  const jsonStart = idx + '\n<!-- APEX_USAGE:'.length
  const jsonEnd = text.indexOf(' -->', jsonStart)
  if (jsonEnd === -1) return { cleanText: text, usage: null }
  try {
    const usage = JSON.parse(text.slice(jsonStart, jsonEnd))
    return { cleanText: text.slice(0, idx), usage }
  } catch {
    return { cleanText: text, usage: null }
  }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

interface Mensagem {
  role: 'assistant' | 'user'
  content: string
  streaming?: boolean
  usage?: UsageInfo | null
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

// ─── Componente ───────────────────────────────────────────────────────────────
export default function AnaliseModal({
  positionId, ticker, modulo, tese, onClose, onTeseSalva,
}: AnaliseModalProps) {
  const { portfolioAtivo, userId, addTokenUsage } = useStore()
  const isSimulada = portfolioAtivo?.tipo === 'simulada'
  const isTese = portfolioAtivo?.tipo === 'tese'
  const [fase, setFase] = useState<'analisando' | 'chat'>('analisando')
  const [mensagens, setMensagens] = useState<Mensagem[]>([])
  const [input, setInput] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  // Painel de tese
  const [teseAberta, setTeseAberta] = useState(false)
  const [teseTexto, setTeseTexto] = useState(tese || '')
  const [salvandoTese, setSalvandoTese] = useState(false)
  const [teseSalva, setTeseSalva] = useState(false)

  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Custo acumulado da sessão
  const totalUsage = useMemo(() => {
    let tokens = 0, cost = 0
    for (const m of mensagens) {
      if (m.usage) { tokens += m.usage.in + m.usage.out; cost += m.usage.cost }
    }
    return { tokens, cost }
  }, [mensagens])

  // ─── Fase 1: análise inicial ─────────────────────────────────────────────────
  useEffect(() => {
    const abort = new AbortController()
    let texto = ''
    let rafId: number | null = null
    let dirty = false
    setMensagens([{ role: 'assistant', content: '', streaming: true }])

    async function fetchStream() {
      try {
        const _headers: Record<string, string> = {}
        if (userId) _headers['x-user-id'] = String(userId)
        const res = await fetch(`${API_BASE}/chat/analisar-posicao/${positionId}`, {
          headers: _headers,
          signal: abort.signal,
        })
        if (!res.ok) {
          const j = await res.json().catch(() => ({ detail: 'Erro desconhecido' }))
          setErro(j.detail || 'Erro ao analisar posição')
          setMensagens([])
          return
        }
        const reader = res.body!.getReader()
        const decoder = new TextDecoder('utf-8')

        function scheduleUpdate() {
          if (!dirty) {
            dirty = true
            rafId = requestAnimationFrame(() => {
              dirty = false
              setMensagens([{ role: 'assistant', content: texto, streaming: true }])
            })
          }
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          texto += decoder.decode(value, { stream: true })
          scheduleUpdate()
        }

        // Final render — complete
        if (rafId) cancelAnimationFrame(rafId)
        const { cleanText, usage } = extractUsage(texto)
        texto = cleanText
        if (usage) addTokenUsage(usage.in, usage.out, usage.cost)
        setMensagens([{ role: 'assistant', content: cleanText, streaming: false, usage }])
        setFase('chat')
        setTimeout(() => inputRef.current?.focus(), 100)

        // Persiste a análise no banco
        try {
          const _saveHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
          if (userId) _saveHeaders['x-user-id'] = String(userId)
          await api.patch(`/portfolio/posicoes/${positionId}`, { analise_ia: texto })
        } catch { /* silent — análise já está visível no chat */ }
      } catch (e: any) {
        if (e.name === 'AbortError') return
        setErro(e.message || 'Falha na conexão')
        setMensagens([])
      }
    }

    fetchStream()
    return () => {
      abort.abort()
      if (rafId) cancelAnimationFrame(rafId)
    }
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
        body: JSON.stringify({ mensagem: texto, historico: historicoAtual, modulo }),
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
      let rafId2: number | null = null
      let dirty2 = false

      function scheduleChat() {
        if (!dirty2) {
          dirty2 = true
          rafId2 = requestAnimationFrame(() => {
            dirty2 = false
            const snap = resposta
            setMensagens(prev => {
              const arr = [...prev]
              arr[arr.length - 1] = { role: 'assistant', content: snap, streaming: true }
              return arr
            })
          })
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        resposta += decoder.decode(value, { stream: true })
        scheduleChat()
      }

      if (rafId2) cancelAnimationFrame(rafId2)

      const { cleanText: respostaLimpa, usage: usageChat } = extractUsage(resposta)
      resposta = respostaLimpa
      if (usageChat) addTokenUsage(usageChat.in, usageChat.out, usageChat.cost)
      setMensagens(prev => {
        const arr = [...prev]
        arr[arr.length - 1] = { role: 'assistant', content: respostaLimpa, streaming: false, usage: usageChat }
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
    let body = ''
    for (const m of mensagens) {
      if (m.role === 'user') {
        body += `<div style="background:#1e1b4b;border:1px solid #3730a3;border-radius:12px;padding:12px 16px;margin:16px 0;margin-left:auto;max-width:85%;color:#e0e7ff"><strong>Você:</strong><br/>${m.content.replace(/\n/g, '<br/>')}</div>`
      } else {
        body += `<div style="margin:16px 0;color:#e2e8f0">${renderContent(m.content)}</div>`
      }
    }
    const tokenInfo = totalUsage.tokens > 0 ? ` • ${formatTokens(totalUsage.tokens)} tokens • $${totalUsage.cost.toFixed(4)}` : ''
    const html = `<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX Analyst — ${ticker}</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root{--bg:#06080F;--surface:#0C1220;--border:rgba(100,116,139,0.12);--text:#E2E8F0;--text2:#94A3B8;--text3:#64748B;--green:#10B981;--blue:#0EA5E9}
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--text);font-family:'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.7;padding:0}
  .container{max-width:800px;margin:0 auto;padding:32px 24px 60px}
  strong{color:#f1f5f9}
  .header{background:linear-gradient(135deg,#0C1220 0%,#0A1628 100%);border-bottom:1px solid rgba(14,165,233,0.15);padding:28px 24px;margin-bottom:32px}
  .header-inner{max-width:800px;margin:0 auto}
  .header-top{display:flex;align-items:center;gap:12px;margin-bottom:4px}
  .header-logo{width:36px;height:36px;background:linear-gradient(135deg,#0EA5E9,#8B5CF6);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:900;color:#fff;font-family:'JetBrains Mono',monospace}
  .ticker{font-size:28px;font-weight:800;color:#F1F5F9;margin-top:12px}
  .date-stamp{font-size:11px;color:var(--text3);font-family:'JetBrains Mono',monospace;margin-top:10px}
  .footer{text-align:center;margin-top:32px;padding-top:20px;border-top:1px solid var(--border);font-size:11px;color:var(--text3)}
</style></head><body>
<div class="header">
  <div class="header-inner">
    <div class="header-top">
      <div class="header-logo">A</div>
      <div>
        <div style="font-size:15px;font-weight:800;color:#F1F5F9">APEX Autonomous Analyst</div>
        <div style="font-size:11px;color:var(--text3);letter-spacing:2px;text-transform:uppercase">Análise 7 Camadas</div>
      </div>
    </div>
    <div class="ticker">${ticker}</div>
    <div class="date-stamp">${data} ${hora} • ${MODULO_LABEL[modulo] ?? modulo}${tokenInfo}</div>
  </div>
</div>
<div class="container">
${body}
<div class="footer">APEX Autonomous Analyst • Dados de fontes públicas • Não constitui recomendação de investimento</div>
</div>
</body></html>`
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `APEX_${ticker}_${data}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ─── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

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
                {totalUsage.tokens > 0 && (
                  <span className="ml-2" style={{ color: '#475569' }}>
                    ⚡ {formatTokens(totalUsage.tokens)} tok
                    {totalUsage.cost > 0 ? ` · $${totalUsage.cost.toFixed(4)}` : ' · grátis'}
                  </span>
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
                  ) : m.streaming ? (
                    <>
                      {(() => {
                        const { stable, pending } = splitStableContent(m.content)
                        return (
                          <>
                            {stable && <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderContent(stable)) }} />}
                            {pending && <span style={{ whiteSpace: 'pre-wrap' }}>{pending}</span>}
                          </>
                        )
                      })()}
                      <span
                        className="inline-block w-1.5 h-4 ml-0.5 animate-pulse"
                        style={{ background: '#00E676', verticalAlign: 'text-bottom' }}
                      />
                    </>
                  ) : (
                    <>
                      <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderContent(m.content)) }} />
                    </>
                  )
                ) : (
                  <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
                )}
                {/* Token usage badge */}
                {m.role === 'assistant' && !m.streaming && m.usage && (
                  <div className="mt-1.5 text-[10px] flex items-center gap-1.5" style={{ color: '#475569' }}>
                    <span>⚡ {formatTokens(m.usage.in + m.usage.out)} tokens</span>
                    <span>•</span>
                    <span>{m.usage.cost > 0 ? `$${m.usage.cost.toFixed(4)}` : 'grátis'}</span>
                    <span>•</span>
                    <span>{m.usage.provider}{m.usage.model ? ` (${m.usage.model.split('/').pop()})` : ''}</span>
                  </div>
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
