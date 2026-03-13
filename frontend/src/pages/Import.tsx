import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, FileSpreadsheet, ChevronRight, ChevronDown, CheckCircle, AlertCircle, ArrowLeft, X, Layers, Plug, Building2, Globe, Key, RefreshCw, Trash2, Eye } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import api from '@/services/api'

/* ═══════════════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════════ */

type Method = 'hub' | 'b3' | 'corretora' | 'pluggy'
type Tipo = 'posicao' | 'negociacao' | 'movimentacao'
type Step = 'select' | 'preview' | 'confirming' | 'done'

interface PreviewCorretora {
  nome_curto: string
  posicoes?: any[]
  transacoes?: any[]
  movimentacoes?: any[]
}

interface ArquivoPreview {
  tipo: string
  arquivo?: string
  corretoras: Record<string, PreviewCorretora>
  totais?: any
  resumo?: any
}

interface CombinedPreview {
  arquivos: ArquivoPreview[]
  tipos: string[]
}

interface PluggyItem {
  id: string
  connector: string
  status: string
  connected_at: string
}

const TIPO_LABELS: Record<string, string> = {
  b3_posicao: 'Posição',
  b3_negociacao: 'Negociação',
  b3_movimentacao: 'Movimentação',
}

function tipoToTipo(t: string): Tipo {
  return t.replace('b3_', '') as Tipo
}

/* ═══════════════════════════════════════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ImportPage() {
  const navigate = useNavigate()
  const [method, setMethod] = useState<Method>('hub')

  const goBack = () => setMethod('hub')

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <AnimatePresence mode="wait">
        {method === 'hub' && <HubView key="hub" onSelect={setMethod} />}
        {method === 'b3' && <B3Flow key="b3" onBack={goBack} navigate={navigate} />}
        {method === 'corretora' && <CorretoraFlow key="corretora" onBack={goBack} navigate={navigate} />}
        {method === 'pluggy' && <PluggyFlow key="pluggy" onBack={goBack} navigate={navigate} />}
      </AnimatePresence>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   Hub — Escolher método de importação
   ═══════════════════════════════════════════════════════════════════════════ */

function HubView({ onSelect }: { onSelect: (m: Method) => void }) {
  const methods = [
    {
      id: 'corretora' as Method,
      icon: <Building2 size={22} />,
      title: 'Extrato da Corretora',
      desc: 'Upload do XLSX de posições da corretora (XP, BTG…) + negociações da B3. Combina o melhor das duas fontes.',
      accent: '#00E676',
      tag: 'Recomendado',
    },
    {
      id: 'pluggy' as Method,
      icon: <Plug size={22} />,
      title: 'Pluggy (Open Finance)',
      desc: 'Conexão automática via Open Finance. Puxa posições e transações direto da corretora.',
      accent: '#60A5FA',
      tag: 'Automático',
    },
    {
      id: 'b3' as Method,
      icon: <Globe size={22} />,
      title: 'B3 Área do Investidor',
      desc: 'Upload dos extratos XLSX da B3 (investidor.b3.com.br). Dados consolidados de todas as corretoras.',
      accent: '#FBBF24',
      tag: 'Consolidado',
    },
  ]

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
      <div className="flex items-center gap-3 mb-8">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'rgba(0,230,118,0.1)', border: '1px solid rgba(0,230,118,0.25)' }}>
          <Upload size={16} style={{ color: '#00E676' }} />
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>Importar Dados</h1>
          <p className="text-xs" style={{ color: '#64748b' }}>Escolha como deseja importar suas posições e transações</p>
        </div>
      </div>

      <div className="space-y-3">
        {methods.map(m => (
          <button
            key={m.id}
            onClick={() => onSelect(m.id)}
            className="w-full text-left apex-card p-5 flex items-start gap-4 transition-all group"
            style={{ border: '1px solid #1e293b' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = m.accent + '40'; e.currentTarget.style.background = m.accent + '06' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = '#1e293b'; e.currentTarget.style.background = '' }}
          >
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: m.accent + '15', color: m.accent }}>
              {m.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>{m.title}</span>
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{ background: m.accent + '15', color: m.accent }}>{m.tag}</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>{m.desc}</p>
            </div>
            <ChevronRight size={16} style={{ color: '#334155' }} className="mt-1 flex-shrink-0 group-hover:translate-x-0.5 transition-transform" />
          </button>
        ))}
      </div>
    </motion.div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   B3 Flow — Upload XLSX da B3 (preservado do original)
   ═══════════════════════════════════════════════════════════════════════════ */

function B3Flow({ onBack, navigate }: { onBack: () => void; navigate: (p: string) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('select')
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<CombinedPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [dragOver, setDragOver] = useState(false)
  const [selectedCorretoras, setSelectedCorretoras] = useState<Set<string>>(new Set())

  const addFiles = (newFiles: FileList | null) => {
    if (!newFiles) return
    const valid: File[] = []
    for (let i = 0; i < newFiles.length; i++) {
      const f = newFiles[i]
      if (!f.name.toLowerCase().endsWith('.xlsx')) { setError('Apenas arquivos .xlsx são aceitos.'); return }
      if (f.size > 50 * 1024 * 1024) { setError(`Arquivo "${f.name}" muito grande (máx 50MB).`); return }
      if (!files.some(existing => existing.name === f.name)) valid.push(f)
    }
    if (valid.length === 0) return
    setError(null)
    setFiles(prev => [...prev, ...valid].slice(0, 3))
  }

  const removeFile = (name: string) => setFiles(prev => prev.filter(f => f.name !== name))

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files)
  }, [files])

  const handleUpload = async () => {
    if (files.length === 0) return
    setUploading(true); setError(null)
    try {
      const fd = new FormData()
      files.forEach(f => fd.append('files', f))
      const res = await api.post('/import/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setPreview(res.data)
      const allC = new Set<string>()
      for (const arq of res.data.arquivos) Object.keys(arq.corretoras).forEach(k => allC.add(k))
      setSelectedCorretoras(allC)
      setStep('preview')
    } catch (e: any) { setError(e?.response?.data?.detail ?? 'Erro ao processar arquivos.') }
    finally { setUploading(false) }
  }

  const allCorretoras = preview ? [...new Set(preview.arquivos.flatMap(arq => Object.keys(arq.corretoras)))] : []

  const handleConfirm = async () => {
    if (selectedCorretoras.size === 0) { setError('Selecione pelo menos uma corretora.'); return }
    setStep('confirming'); setError(null)
    try {
      const res = await api.post('/import/confirm', { corretoras_selecionadas: [...selectedCorretoras] })
      setResult(res.data); setStep('done')
    } catch (e: any) { setError(e?.response?.data?.detail ?? 'Erro ao confirmar importação.'); setStep('preview') }
  }

  const reset = () => { setStep('select'); setFiles([]); setPreview(null); setError(null); setResult(null); setSelectedCorretoras(new Set()) }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
      <FlowHeader icon={<Globe size={16} />} title="Importar da B3" subtitle="Arraste os arquivos .xlsx da B3 Área do Investidor" accent="#FBBF24" onBack={step === 'select' ? onBack : reset} />

      <StepIndicator steps={['Arquivos', 'Preview', 'Confirmação']} current={step === 'select' ? 0 : step === 'preview' ? 1 : 2} />

      <AnimatePresence mode="wait">
        {step === 'select' && (
          <motion.div key="sel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {/* Passo a passo */}
            <div className="apex-card p-4 mb-4">
              <p className="text-[10px] font-mono uppercase mb-3" style={{ color: '#FBBF24' }}>Passo a passo</p>
              <div className="space-y-2">
                {[
                  'Acesse investidor.b3.com.br → Login com conta gov.br (CPF + senha gov.br)',
                  'Posição: menu "Extratos" → "Posição" → selecione data de referência → "Exportar por .xlsx" (foto da carteira em todas as corretoras)',
                  'Negociação: menu "Extratos" → "Negociação" → selecione período → "Exportar por .xlsx" (cada compra/venda individual)',
                  'Movimentação: menu "Extratos" → "Movimentação" → selecione período → "Exportar por .xlsx" (proventos, bonificações, etc)',
                  'Arraste até 3 arquivos .xlsx aqui abaixo — o tipo é detectado automaticamente',
                ].map((text, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <span className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold" style={{ background: 'rgba(251,191,36,0.12)', border: '1px solid rgba(251,191,36,0.3)', color: '#FBBF24' }}>{i + 1}</span>
                    <p className="text-xs leading-relaxed pt-0.5" style={{ color: '#94a3b8' }}>{text}</p>
                  </div>
                ))}
              </div>
            </div>

            <DropZone fileRef={fileRef} files={files} dragOver={dragOver} setDragOver={setDragOver} onDrop={handleDrop} addFiles={addFiles} removeFile={removeFile} maxFiles={3} hint="Baixe em investidor.b3.com.br → Extratos e Informativos" />
            <input ref={fileRef} type="file" accept=".xlsx" multiple className="hidden" onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
            {error && <ErrorMsg msg={error} />}
            <ActionButton onClick={handleUpload} disabled={files.length === 0 || uploading} loading={uploading} label={`Processar ${files.length > 0 ? `${files.length} arquivo${files.length > 1 ? 's' : ''}` : 'arquivos'}`} loadingLabel={`Processando ${files.length} arquivo${files.length > 1 ? 's' : ''}...`} />
          </motion.div>
        )}

        {step === 'preview' && preview && (
          <motion.div key="prev" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="flex flex-wrap gap-2 mb-4">
              {preview.arquivos.map((arq, idx) => (
                <span key={idx} className="text-[10px] font-mono px-2.5 py-1 rounded-lg flex items-center gap-1.5" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                  <FileSpreadsheet size={11} />{TIPO_LABELS[arq.tipo] ?? arq.tipo}
                  {arq.arquivo && <span style={{ color: '#475569' }}>— {arq.arquivo}</span>}
                </span>
              ))}
            </div>
            <BrokerSelector corretoras={allCorretoras} selected={selectedCorretoras} setSelected={setSelectedCorretoras} preview={preview} />
            <FilePreviewCards preview={preview} selectedCorretoras={selectedCorretoras} />
            {error && <ErrorMsg msg={error} />}
            <ActionButton onClick={handleConfirm} disabled={selectedCorretoras.size === 0} label={`Importar ${selectedCorretoras.size} corretora${selectedCorretoras.size !== 1 ? 's' : ''}`} />
          </motion.div>
        )}

        {step === 'confirming' && <LoadingStep key="conf" />}
        {step === 'done' && result && <DoneStep key="done" result={result} onReset={reset} onDashboard={() => navigate('/dashboard')} />}
      </AnimatePresence>
    </motion.div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   Corretora Flow — Upload individual por corretora
   ═══════════════════════════════════════════════════════════════════════════ */

function CorretoraFlow({ onBack, navigate }: { onBack: () => void; navigate: (p: string) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('select')
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<CombinedPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [dragOver, setDragOver] = useState(false)
  const [selectedCorretoras, setSelectedCorretoras] = useState<Set<string>>(new Set())

  const addFiles = (newFiles: FileList | null) => {
    if (!newFiles) return
    const valid: File[] = []
    for (let i = 0; i < newFiles.length; i++) {
      const f = newFiles[i]
      if (!f.name.toLowerCase().endsWith('.xlsx')) { setError('Apenas arquivos .xlsx são aceitos.'); return }
      if (f.size > 50 * 1024 * 1024) { setError(`Arquivo "${f.name}" muito grande (máx 50MB).`); return }
      if (!files.some(existing => existing.name === f.name)) valid.push(f)
    }
    if (valid.length === 0) return
    setError(null)
    setFiles(prev => [...prev, ...valid].slice(0, 3))
  }

  const removeFile = (name: string) => setFiles(prev => prev.filter(f => f.name !== name))

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files)
  }, [files])

  const handleUpload = async () => {
    if (files.length === 0) return
    setUploading(true); setError(null)
    try {
      const fd = new FormData()
      files.forEach(f => fd.append('files', f))
      const res = await api.post('/import/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setPreview(res.data)
      // Smart pre-selection: only select corretoras that appear in posição files
      const posCorretoras = new Set<string>()
      const allC = new Set<string>()
      for (const arq of (res.data as CombinedPreview).arquivos) {
        const keys = Object.keys(arq.corretoras)
        keys.forEach(k => allC.add(k))
        if (arq.tipo === 'b3_posicao') keys.forEach(k => posCorretoras.add(k))
      }
      // If we have posição files, only pre-select those corretoras; otherwise select all
      setSelectedCorretoras(posCorretoras.size > 0 ? posCorretoras : allC)
      setStep('preview')
    } catch (e: any) { setError(e?.response?.data?.detail ?? 'Erro ao processar arquivos.') }
    finally { setUploading(false) }
  }

  const allCorretoras = preview ? [...new Set(preview.arquivos.flatMap(arq => Object.keys(arq.corretoras)))] : []

  const handleConfirm = async () => {
    if (selectedCorretoras.size === 0) { setError('Selecione pelo menos uma corretora.'); return }
    setStep('confirming'); setError(null)
    try {
      const res = await api.post('/import/confirm', { corretoras_selecionadas: [...selectedCorretoras] })
      setResult(res.data); setStep('done')
    } catch (e: any) { setError(e?.response?.data?.detail ?? 'Erro ao confirmar importação.'); setStep('preview') }
  }

  const reset = () => { setStep('select'); setFiles([]); setPreview(null); setError(null); setResult(null); setSelectedCorretoras(new Set()) }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
      <FlowHeader icon={<Building2 size={16} />} title="Extrato da Corretora" subtitle="Posições da corretora + Negociações da B3 — até 3 arquivos .xlsx" accent="#00E676" onBack={step === 'select' ? onBack : reset} />

      <StepIndicator steps={['Arquivos', 'Preview', 'Confirmação']} current={step === 'select' ? 0 : step === 'preview' ? 1 : 2} />

      <AnimatePresence mode="wait">
        {step === 'select' && (
          <motion.div key="sel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {/* Guia por corretora */}
            <BrokerGuide />

            <DropZone fileRef={fileRef} files={files} dragOver={dragOver} setDragOver={setDragOver} onDrop={handleDrop} addFiles={addFiles} removeFile={removeFile} maxFiles={3} hint="Exporte os relatórios da sua corretora em .xlsx" />
            <input ref={fileRef} type="file" accept=".xlsx" multiple className="hidden" onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
            {error && <ErrorMsg msg={error} />}
            <ActionButton onClick={handleUpload} disabled={files.length === 0 || uploading} loading={uploading} label={`Processar ${files.length > 0 ? `${files.length} arquivo${files.length > 1 ? 's' : ''}` : 'arquivos'}`} loadingLabel={`Processando ${files.length} arquivo${files.length > 1 ? 's' : ''}...`} />
          </motion.div>
        )}

        {step === 'preview' && preview && (
          <motion.div key="prev" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="flex flex-wrap gap-2 mb-4">
              {preview.arquivos.map((arq, idx) => (
                <span key={idx} className="text-[10px] font-mono px-2.5 py-1 rounded-lg flex items-center gap-1.5" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                  <FileSpreadsheet size={11} />{TIPO_LABELS[arq.tipo] ?? arq.tipo}
                  {arq.arquivo && <span style={{ color: '#475569' }}>— {arq.arquivo}</span>}
                </span>
              ))}
            </div>
            {/* Info: explain why some corretoras are pre-selected */}
            {preview.arquivos.some(a => a.tipo === 'b3_posicao') && allCorretoras.length > selectedCorretoras.size && (
              <div className="apex-card p-3 mb-4 flex items-start gap-2" style={{ background: 'rgba(251,191,36,0.05)', border: '1px solid rgba(251,191,36,0.2)' }}>
                <AlertCircle size={14} className="mt-0.5 flex-shrink-0" style={{ color: '#FBBF24' }} />
                <p className="text-xs" style={{ color: '#94a3b8' }}>
                  Pré-selecionamos apenas as corretoras do arquivo de posição. Marque outras se quiser importar também.
                </p>
              </div>
            )}
            <BrokerSelector corretoras={allCorretoras} selected={selectedCorretoras} setSelected={setSelectedCorretoras} preview={preview} />
            <FilePreviewCards preview={preview} selectedCorretoras={selectedCorretoras} />
            {error && <ErrorMsg msg={error} />}
            <ActionButton onClick={handleConfirm} disabled={selectedCorretoras.size === 0} label={`Importar ${selectedCorretoras.size} corretora${selectedCorretoras.size !== 1 ? 's' : ''}`} />
          </motion.div>
        )}

        {step === 'confirming' && <LoadingStep key="conf" />}
        {step === 'done' && result && <DoneStep key="done" result={result} onReset={reset} onDashboard={() => navigate('/dashboard')} />}
      </AnimatePresence>
    </motion.div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   Pluggy Flow — Open Finance automático
   ═══════════════════════════════════════════════════════════════════════════ */

function PluggyFlow({ onBack, navigate }: { onBack: () => void; navigate: (p: string) => void }) {
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [items, setItems] = useState<PluggyItem[]>([])
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [syncResult, setSyncResult] = useState<any>(null)
  const [previewData, setPreviewData] = useState<any>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)

  const loadSettings = async () => {
    try {
      const res = await api.get('/pluggy/settings')
      setConfigured(res.data.configured)
      setItems(res.data.items || [])
    } catch { setConfigured(false) }
  }

  useEffect(() => { loadSettings() }, [])

  const handleTest = async () => {
    setTesting(true); setTestResult(null)
    try {
      const res = await api.post('/pluggy/settings/test', { client_id: clientId, client_secret: clientSecret })
      setTestResult({ ok: res.data.ok, msg: res.data.message })
    } catch (e: any) { setTestResult({ ok: false, msg: e?.response?.data?.detail || 'Erro ao testar' }) }
    finally { setTesting(false) }
  }

  const handleSave = async () => {
    setSaving(true); setError(null)
    try {
      await api.post('/pluggy/settings', { client_id: clientId, client_secret: clientSecret })
      setConfigured(true); setClientId(''); setClientSecret('')
    } catch (e: any) { setError(e?.response?.data?.detail || 'Erro ao salvar') }
    finally { setSaving(false) }
  }

  const handleConnect = async () => {
    setError(null)
    try {
      const res = await api.post('/pluggy/connect-token')
      const token = res.data.accessToken
      // Open Pluggy Connect Widget in a new window
      const url = `https://connect.pluggy.ai/?connect_token=${encodeURIComponent(token)}`
      const popup = window.open(url, 'pluggy_connect', 'width=500,height=700,scrollbars=yes')
      // Listen for message from popup (Pluggy sends postMessage)
      const handler = async (ev: MessageEvent) => {
        if (ev.data?.event === 'pluggy-connect-success' || ev.data?.item?.id) {
          const itemId = ev.data?.item?.id || ev.data?.itemId
          if (itemId) {
            try { await api.post('/pluggy/item-connected', { item_id: itemId }) } catch {}
            loadSettings()
          }
          popup?.close()
        }
        if (ev.data?.event === 'pluggy-connect-close' || ev.data?.event === 'close') {
          popup?.close()
        }
      }
      window.addEventListener('message', handler)
      // Cleanup: poll for popup close
      const interval = setInterval(() => {
        if (!popup || popup.closed) {
          clearInterval(interval)
          window.removeEventListener('message', handler)
          loadSettings()
        }
      }, 1000)
    } catch (e: any) { setError(e?.response?.data?.detail || 'Erro ao iniciar conexão') }
  }

  const handleSync = async (itemId: string) => {
    setSyncing(itemId); setSyncResult(null); setError(null)
    try {
      const res = await api.post(`/pluggy/sync/${itemId}`)
      setSyncResult(res.data)
    } catch (e: any) { setError(e?.response?.data?.detail || 'Erro ao sincronizar') }
    finally { setSyncing(null) }
  }

  const handlePreview = async (itemId: string) => {
    setPreviewing(itemId); setPreviewData(null)
    try {
      const res = await api.get(`/pluggy/preview/${itemId}`)
      setPreviewData(res.data)
    } catch (e: any) { setError(e?.response?.data?.detail || 'Erro ao buscar preview') }
    finally { setPreviewing(null) }
  }

  const handleDisconnect = async (itemId: string) => {
    if (!confirm('Desconectar esta corretora?')) return
    try {
      await api.delete(`/pluggy/item/${itemId}`)
      loadSettings()
    } catch (e: any) { setError(e?.response?.data?.detail || 'Erro ao desconectar') }
  }

  if (configured === null) return <div className="flex justify-center py-20"><Spinner /></div>

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
      <FlowHeader icon={<Plug size={16} />} title="Pluggy — Open Finance" subtitle="Conexão automática com suas corretoras via Open Finance" accent="#60A5FA" onBack={onBack} />

      {!configured ? (
        /* ─── Setup credentials ─── */
        <div className="apex-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Key size={16} style={{ color: '#60A5FA' }} />
            <p className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>Configurar Pluggy</p>
          </div>
          {/* Passo a passo */}
          <div className="mb-4 p-3 rounded-lg" style={{ background: 'rgba(96,165,250,0.04)', border: '1px solid rgba(96,165,250,0.12)' }}>
            <p className="text-[10px] font-mono uppercase mb-2.5" style={{ color: '#60A5FA' }}>Passo a passo</p>
            <div className="space-y-2">
              {[
                'Acesse pluggy.ai e crie uma conta gratuita (plano Starter)',
                'No Dashboard do Pluggy, vá em API Keys',
                'Copie o Client ID e o Client Secret',
                'Cole aqui abaixo e clique em "Testar" para validar',
                'Clique em "Salvar" — depois é só conectar suas corretoras!',
              ].map((text, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 text-[9px] font-bold" style={{ background: 'rgba(96,165,250,0.15)', border: '1px solid rgba(96,165,250,0.3)', color: '#60A5FA' }}>{i + 1}</span>
                  <p className="text-[11px] leading-relaxed pt-px" style={{ color: '#94a3b8' }}>{text}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <input
              value={clientId} onChange={e => setClientId(e.target.value)}
              placeholder="Client ID"
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{ border: '1px solid #1e293b', color: '#e2e8f0' }}
            />
            <input
              value={clientSecret} onChange={e => setClientSecret(e.target.value)}
              placeholder="Client Secret" type="password"
              className="w-full px-3 py-2 rounded-lg text-sm bg-transparent outline-none"
              style={{ border: '1px solid #1e293b', color: '#e2e8f0' }}
            />
          </div>
          {testResult && (
            <div className="flex items-center gap-2 mt-3 px-1">
              {testResult.ok ? <CheckCircle size={13} style={{ color: '#00E676' }} /> : <AlertCircle size={13} style={{ color: '#ef4444' }} />}
              <p className="text-xs" style={{ color: testResult.ok ? '#00E676' : '#ef4444' }}>{testResult.msg}</p>
            </div>
          )}
          {error && <ErrorMsg msg={error} />}
          <div className="flex gap-2 mt-4">
            <button onClick={handleTest} disabled={!clientId || !clientSecret || testing}
              className="flex-1 py-2 rounded-xl text-xs font-medium transition-all flex items-center justify-center gap-1"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b', color: '#94a3b8' }}>
              {testing ? <Spinner size={12} /> : null} Testar
            </button>
            <button onClick={handleSave} disabled={!clientId || !clientSecret || saving}
              className="flex-1 py-2 rounded-xl text-xs font-medium transition-all flex items-center justify-center gap-1"
              style={{ background: 'rgba(96,165,250,0.12)', border: '1px solid rgba(96,165,250,0.3)', color: '#60A5FA' }}>
              {saving ? <Spinner size={12} /> : null} Salvar
            </button>
          </div>
        </div>
      ) : (
        /* ─── Connected state ─── */
        <div className="space-y-4">
          {/* Connect new */}
          <button
            onClick={handleConnect}
            className="w-full apex-card p-4 flex items-center gap-3 transition-all"
            style={{ border: '1px solid rgba(96,165,250,0.2)' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.4)'; e.currentTarget.style.background = 'rgba(96,165,250,0.04)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.2)'; e.currentTarget.style.background = '' }}
          >
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(96,165,250,0.1)' }}>
              <Plug size={14} style={{ color: '#60A5FA' }} />
            </div>
            <div className="text-left flex-1">
              <p className="text-sm font-medium" style={{ color: '#e2e8f0' }}>Conectar Nova Corretora</p>
              <p className="text-[10px]" style={{ color: '#64748b' }}>Abre o Pluggy Connect para autenticar com uma corretora</p>
            </div>
            <ChevronRight size={14} style={{ color: '#475569' }} />
          </button>

          {/* Connected items */}
          {items.length > 0 && (
            <div>
              <p className="text-[10px] font-mono uppercase mb-2 px-1" style={{ color: '#475569' }}>Corretoras conectadas</p>
              <div className="space-y-2">
                {items.map(item => (
                  <div key={item.id} className="apex-card p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Building2 size={14} style={{ color: '#60A5FA' }} />
                        <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>{item.connector}</span>
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                          style={{ background: item.status === 'UPDATED' ? 'rgba(0,230,118,0.1)' : 'rgba(255,152,0,0.1)', color: item.status === 'UPDATED' ? '#00E676' : '#FF9800' }}>
                          {item.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={() => handlePreview(item.id)} title="Preview"
                          className="p-1.5 rounded-lg transition-all" style={{ color: '#475569' }}
                          onMouseEnter={e => (e.currentTarget.style.color = '#94a3b8')} onMouseLeave={e => (e.currentTarget.style.color = '#475569')}>
                          {previewing === item.id ? <Spinner size={13} /> : <Eye size={13} />}
                        </button>
                        <button onClick={() => handleSync(item.id)} title="Sincronizar"
                          className="p-1.5 rounded-lg transition-all" style={{ color: '#475569' }}
                          onMouseEnter={e => (e.currentTarget.style.color = '#60A5FA')} onMouseLeave={e => (e.currentTarget.style.color = '#475569')}>
                          {syncing === item.id ? <Spinner size={13} /> : <RefreshCw size={13} />}
                        </button>
                        <button onClick={() => handleDisconnect(item.id)} title="Desconectar"
                          className="p-1.5 rounded-lg transition-all" style={{ color: '#475569' }}
                          onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')} onMouseLeave={e => (e.currentTarget.style.color = '#475569')}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                    <p className="text-[10px]" style={{ color: '#475569' }}>
                      Conectado em {new Date(item.connected_at).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sync result */}
          {syncResult && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={14} style={{ color: '#00E676' }} />
                <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>Sincronização concluída</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <StatBox label="Carteira" value={syncResult.portfolio?.nome || '—'} />
                <StatBox label="Criadas" value={syncResult.created} />
                <StatBox label="Atualizadas" value={syncResult.updated} />
              </div>
              <button onClick={() => navigate('/positions')} className="w-full mt-3 py-2 rounded-xl text-xs font-medium"
                style={{ background: 'rgba(0,230,118,0.12)', border: '1px solid rgba(0,230,118,0.3)', color: '#00E676' }}>
                Ver Posições
              </button>
            </motion.div>
          )}

          {/* Preview data */}
          {previewData && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Eye size={14} style={{ color: '#60A5FA' }} />
                  <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>Preview — {previewData.connector}</span>
                </div>
                <button onClick={() => setPreviewData(null)} className="p-1 rounded" style={{ color: '#475569' }}><X size={12} /></button>
              </div>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <StatBox label="Posições" value={previewData.total} />
                <StatBox label="Valor Total" value={`R$ ${Number(previewData.total_value).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`} />
              </div>
              <div className="overflow-x-auto max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ borderBottom: '1px solid #1e293b' }}>
                      <Th>Ticker</Th><Th>Tipo</Th><Th align="right">Qtd</Th><Th align="right">Valor</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.positions?.map((p: any, i: number) => (
                      <tr key={i} style={{ borderBottom: '1px solid rgba(30,41,59,0.5)' }}>
                        <Td bold>{p.ticker}</Td>
                        <Td><span className="font-mono text-[10px] px-1 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b' }}>{p.tipo}</span></Td>
                        <Td align="right">{formatNum(p.quantidade)}</Td>
                        <Td align="right">{formatBRL(p.valor_atualizado)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {error && <ErrorMsg msg={error} />}
        </div>
      )}
    </motion.div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   BrokerGuide — Expandable per-broker navigation paths
   ═══════════════════════════════════════════════════════════════════════════ */

const BROKER_GUIDES: { name: string; color: string; steps: string[] }[] = [
  {
    name: 'XP Investimentos',
    color: '#FFD700',
    steps: [
      '📸 POSIÇÃO ATUAL (XP): Acesse hub.xpi.com.br → Login → menu "Carteira" → "Meus Investimentos" → botão "Exportar" (Excel) → salve o PosicaoDetalhada.xlsx',
      '↳ Este arquivo cria sua carteira completa com preço médio real, FIIs, ETFs, Ações, BDRs, Renda Fixa e Fundos',
      '📊 NEGOCIAÇÕES (B3): Acesse investidor.b3.com.br → Login gov.br → "Extratos" → "Negociação" → selecione período → "Exportar por .xlsx"',
      '↳ Este arquivo traz cada compra/venda individual de TODAS as suas corretoras (XP, BTG, etc)',
      '🔄 FLUXO: Importe os 2 arquivos juntos aqui abaixo. Posição da XP = foto da carteira hoje. Negociação B3 = histórico de trades.',
      '💡 DICA: Repita a cada 7 dias baixando só a Negociação da B3 para manter os trades atualizados',
    ],
  },
  {
    name: 'BTG Pactual',
    color: '#00A3FF',
    steps: [
      '📸 POSIÇÃO ATUAL (BTG): Acesse btgpactualdigital.com → Login → "Investimentos" → "Minha Carteira" → ícone ⬇ → "Exportar Excel"',
      '📊 NEGOCIAÇÕES (B3): Acesse investidor.b3.com.br → Login gov.br → "Extratos" → "Negociação" → selecione período → "Exportar por .xlsx"',
      '↳ O arquivo da B3 já inclui trades de TODAS as corretoras (BTG, XP, Clear, etc)',
      '🔄 Importe os 2 arquivos juntos. Posição BTG = carteira atual. Negociação B3 = histórico de trades.',
      '⚠️ Parser BTG em breve — por enquanto use apenas a Negociação da B3 para BTG',
    ],
  },
  {
    name: 'Clear / Rico / Genial / Ágora / Inter / Nu',
    color: '#FF6B00',
    steps: [
      '📊 Por enquanto, use a B3 Área do Investidor (opção "B3" na tela anterior) para importar posições e negociações',
      'Acesse investidor.b3.com.br → Login gov.br → "Extratos" → baixe Posição, Negociação e Movimentação',
      '↳ O arquivo da B3 já inclui dados de TODAS as corretoras vinculadas ao seu CPF',
      '💡 Parsers específicos para essas corretoras serão adicionados em breve',
    ],
  },
]

function BrokerGuide() {
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div className="apex-card p-4 mb-4">
      <p className="text-[10px] font-mono uppercase mb-3" style={{ color: '#00E676' }}>
        Selecione sua corretora para ver o caminho exato
      </p>
      <div className="space-y-1.5">
        {BROKER_GUIDES.map(broker => {
          const isOpen = open === broker.name
          return (
            <div key={broker.name}>
              <button
                onClick={() => setOpen(isOpen ? null : broker.name)}
                className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-all"
                style={{
                  background: isOpen ? `${broker.color}12` : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${isOpen ? `${broker.color}40` : 'rgba(255,255,255,0.06)'}`,
                }}
              >
                <span className="text-xs font-medium" style={{ color: isOpen ? broker.color : '#94A3B8' }}>
                  {broker.name}
                </span>
                {isOpen ? <ChevronDown size={14} style={{ color: broker.color }} /> : <ChevronRight size={14} style={{ color: '#475569' }} />}
              </button>
              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="pl-3 pr-2 pt-2 pb-1 space-y-1.5">
                      {broker.steps.map((step, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="text-[10px] font-bold mt-0.5 shrink-0" style={{ color: broker.color }}>{i + 1}.</span>
                          <span className="text-xs" style={{ color: '#CBD5E1' }}>{step}</span>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════════
   Shared Components
   ═══════════════════════════════════════════════════════════════════════════ */

function FlowHeader({ icon, title, subtitle, accent, onBack }: { icon: React.ReactNode; title: string; subtitle: string; accent: string; onBack: () => void }) {
  return (
    <>
      <button onClick={onBack} className="flex items-center gap-1 text-xs mb-4 transition-colors" style={{ color: '#64748b' }}
        onMouseEnter={e => (e.currentTarget.style.color = '#94a3b8')} onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}>
        <ArrowLeft size={12} /> Voltar
      </button>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: accent + '15', border: `1px solid ${accent}40`, color: accent }}>
          {icon}
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>{title}</h1>
          <p className="text-xs" style={{ color: '#64748b' }}>{subtitle}</p>
        </div>
      </div>
    </>
  )
}

function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {steps.map((s, i) => {
        const active = i <= current
        return (
          <div key={s} className="flex items-center gap-2">
            {i > 0 && <div className="w-8 h-px" style={{ background: active ? '#00E676' : '#1e293b' }} />}
            <div className="flex items-center gap-1.5">
              <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{ background: active ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.03)', border: `1px solid ${active ? 'rgba(0,230,118,0.4)' : '#1e293b'}`, color: active ? '#00E676' : '#475569' }}>
                {i + 1}
              </div>
              <span className="text-[11px] font-mono" style={{ color: active ? '#94a3b8' : '#334155' }}>{s}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DropZone({ fileRef, files, dragOver, setDragOver, onDrop, addFiles, removeFile, maxFiles, hint }: {
  fileRef: React.RefObject<HTMLInputElement | null>; files: File[]; dragOver: boolean; setDragOver: (v: boolean) => void;
  onDrop: (e: React.DragEvent) => void; addFiles: (f: FileList | null) => void; removeFile: (n: string) => void; maxFiles: number; hint: string;
}) {
  return (
    <div
      className="apex-card p-8 mb-4 flex flex-col items-center justify-center cursor-pointer transition-all"
      style={{
        border: dragOver ? '2px dashed rgba(0,230,118,0.5)' : files.length > 0 ? '2px solid rgba(0,230,118,0.25)' : '2px dashed #1e293b',
        background: dragOver ? 'rgba(0,230,118,0.04)' : undefined, minHeight: 140,
      }}
      onClick={() => fileRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      {files.length > 0 ? (
        <div className="w-full space-y-2">
          {files.map(f => (
            <div key={f.name} className="flex items-center gap-3 px-3 py-2 rounded-lg" style={{ background: 'rgba(0,230,118,0.04)' }}>
              <FileSpreadsheet size={18} style={{ color: '#00E676' }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: '#e2e8f0' }}>{f.name}</p>
                <p className="text-[10px]" style={{ color: '#64748b' }}>{(f.size / 1024).toFixed(0)} KB</p>
              </div>
              <button onClick={e => { e.stopPropagation(); removeFile(f.name) }} className="p-1 rounded transition-colors" style={{ color: '#475569' }}
                onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')} onMouseLeave={e => (e.currentTarget.style.color = '#475569')}>
                <X size={14} />
              </button>
            </div>
          ))}
          {files.length < maxFiles && (
            <p className="text-[10px] text-center pt-1" style={{ color: '#475569' }}>
              Clique ou arraste para adicionar mais ({maxFiles - files.length} restante{maxFiles - files.length > 1 ? 's' : ''})
            </p>
          )}
        </div>
      ) : (
        <>
          <Upload size={28} style={{ color: '#334155' }} className="mb-3" />
          <p className="text-sm" style={{ color: '#64748b' }}>Arraste os arquivos .xlsx aqui ou clique para selecionar</p>
          <p className="text-[10px] mt-1" style={{ color: '#475569' }}>Até {maxFiles} arquivos — tipo detectado automaticamente</p>
          <p className="text-[10px] mt-0.5" style={{ color: '#334155' }}>{hint}</p>
        </>
      )}
    </div>
  )
}

function BrokerSelector({ corretoras, selected, setSelected, preview }: {
  corretoras: string[]; selected: Set<string>; setSelected: (s: Set<string>) => void; preview: CombinedPreview;
}) {
  return (
    <div className="apex-card p-4 mb-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-mono uppercase" style={{ color: '#64748b' }}>Selecione as corretoras para importar</p>
        <button onClick={() => selected.size === corretoras.length ? setSelected(new Set()) : setSelected(new Set(corretoras))}
          className="text-[10px] font-mono transition-colors" style={{ color: '#64748b' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#00E676')} onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}>
          {selected.size === corretoras.length ? 'Desmarcar todas' : 'Selecionar todas'}
        </button>
      </div>
      <div className="space-y-1.5">
        {corretoras.map(key => {
          let nome = key
          for (const arq of preview.arquivos) { if (arq.corretoras[key]) { nome = arq.corretoras[key].nome_curto ?? key; break } }
          const checked = selected.has(key)
          let itemCount = 0
          for (const arq of preview.arquivos) { const c = arq.corretoras[key]; if (c) itemCount += (c.posicoes?.length ?? 0) + (c.transacoes?.length ?? 0) + (c.movimentacoes?.length ?? 0) }
          return (
            <label key={key} className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-all"
              style={{ background: checked ? 'rgba(0,230,118,0.05)' : 'rgba(255,255,255,0.01)', border: `1px solid ${checked ? 'rgba(0,230,118,0.2)' : '#1e293b'}` }}
              onClick={() => { const next = new Set(selected); if (next.has(key)) next.delete(key); else next.add(key); setSelected(next) }}>
              <div className="w-4 h-4 rounded flex items-center justify-center flex-shrink-0 transition-all"
                style={{ background: checked ? 'rgba(0,230,118,0.2)' : 'transparent', border: `1.5px solid ${checked ? '#00E676' : '#475569'}` }}>
                {checked && <CheckCircle size={10} style={{ color: '#00E676' }} />}
              </div>
              <div className="flex-1 min-w-0"><p className="text-sm font-medium" style={{ color: checked ? '#e2e8f0' : '#64748b' }}>{nome}</p></div>
              <span className="text-[10px] font-mono" style={{ color: '#475569' }}>{itemCount} itens</span>
            </label>
          )
        })}
      </div>
    </div>
  )
}

function FilePreviewCards({ preview, selectedCorretoras }: { preview: CombinedPreview; selectedCorretoras: Set<string> }) {
  return (
    <>
      {preview.arquivos.map((arq, idx) => {
        const tipo = tipoToTipo(arq.tipo)
        const filteredEntries = Object.entries(arq.corretoras).filter(([key]) => selectedCorretoras.has(key))
        if (filteredEntries.length === 0) return null
        return (
          <div key={idx} className="mb-6">
            <div className="apex-card p-4 mb-3">
              <p className="text-xs font-mono uppercase mb-3" style={{ color: '#64748b' }}>{TIPO_LABELS[arq.tipo] ?? arq.tipo}</p>
              <div className="grid grid-cols-3 gap-3">
                <StatBox label="Corretoras" value={filteredEntries.length} />
                {arq.totais?.posicoes != null && <StatBox label="Posições" value={arq.totais.posicoes} />}
                {arq.totais?.valor_total != null && <StatBox label="Valor total" value={`R$ ${Number(arq.totais.valor_total).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`} />}
                {arq.totais?.transacoes != null && <StatBox label="Transações" value={arq.totais.transacoes} />}
                {arq.totais?.compras != null && <StatBox label="Compras" value={arq.totais.compras} />}
                {arq.totais?.vendas != null && <StatBox label="Vendas" value={arq.totais.vendas} />}
                {arq.resumo?.proventos != null && <StatBox label="Proventos" value={arq.resumo.proventos} />}
                {arq.resumo?.eventos != null && <StatBox label="Eventos" value={arq.resumo.eventos} />}
              </div>
            </div>
            {filteredEntries.map(([key, corr]) => (
              <CorretoraCard key={`${idx}-${key}`} nome={corr.nome_curto ?? key} data={corr} tipo={tipo} />
            ))}
          </div>
        )
      })}
    </>
  )
}

function CorretoraCard({ nome, data, tipo }: { nome: string; data: PreviewCorretora; tipo: Tipo }) {
  const [expanded, setExpanded] = useState(false)
  const items = data.posicoes ?? data.transacoes ?? data.movimentacoes ?? []
  const count = items.length
  return (
    <div className="apex-card mb-3 overflow-hidden">
      <button onClick={() => setExpanded(e => !e)} className="w-full flex items-center justify-between p-4 transition-all" style={{ background: 'transparent' }}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
        <div className="flex items-center gap-2">
          <Layers size={14} style={{ color: '#00E676' }} />
          <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>{nome}</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b' }}>
            {count} {tipo === 'posicao' ? 'posições' : tipo === 'negociacao' ? 'transações' : 'movimentações'}
          </span>
        </div>
        <ChevronRight size={14} style={{ color: '#475569', transform: expanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.2s' }} />
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.15 }} className="overflow-hidden">
            <div className="px-4 pb-4">
              {tipo === 'posicao' && <PosicaoTable items={items} />}
              {tipo === 'negociacao' && <NegociacaoTable items={items} />}
              {tipo === 'movimentacao' && <MovimentacaoTable items={items} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ActionButton({ onClick, disabled, loading, label, loadingLabel }: { onClick: () => void; disabled?: boolean; loading?: boolean; label: string; loadingLabel?: string }) {
  return (
    <button onClick={onClick} disabled={disabled || loading}
      className="w-full py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all mt-4"
      style={{ background: !disabled ? 'rgba(0,230,118,0.12)' : 'rgba(255,255,255,0.03)', border: `1px solid ${!disabled ? 'rgba(0,230,118,0.3)' : '#1e293b'}`, color: !disabled ? '#00E676' : '#334155', cursor: !disabled ? 'pointer' : 'not-allowed' }}>
      {loading ? <><Spinner size={14} /> {loadingLabel || label}</> : <>{label} <ChevronRight size={14} /></>}
    </button>
  )
}

function LoadingStep() {
  return (
    <motion.div key="confirming" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center py-16 gap-4">
      <Spinner size={32} />
      <p className="text-sm" style={{ color: '#94a3b8' }}>Importando dados...</p>
      <p className="text-[11px]" style={{ color: '#475569' }}>Esse processo pode levar alguns segundos, aguarde.</p>
    </motion.div>
  )
}

function DoneStep({ result, onReset, onDashboard }: { result: any; onReset: () => void; onDashboard: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
      <div className="apex-card p-6 text-center">
        <CheckCircle size={40} style={{ color: '#00E676' }} className="mx-auto mb-4" />
        <h2 className="text-lg font-bold mb-2" style={{ color: '#f1f5f9' }}>Importação concluída!</h2>
        <p className="text-sm mb-4" style={{ color: '#64748b' }}>{result.mensagem}</p>
        {result.portfolios_criados?.length > 0 && (
          <div className="mb-4">
            <p className="text-[10px] font-mono uppercase mb-2" style={{ color: '#475569' }}>Carteiras criadas</p>
            <div className="flex flex-wrap justify-center gap-2">
              {result.portfolios_criados.map((p: any) => (
                <span key={p.id} className="text-xs font-mono px-3 py-1 rounded-lg" style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                  <Layers size={10} className="inline mr-1" />{p.nome}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-3 mt-6">
          <button onClick={onReset} className="flex-1 py-2.5 rounded-xl text-xs font-medium" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b', color: '#94a3b8' }}>
            Importar outro
          </button>
          <button onClick={onDashboard} className="flex-1 py-2.5 rounded-xl text-xs font-medium" style={{ background: 'rgba(0,230,118,0.12)', border: '1px solid rgba(0,230,118,0.3)', color: '#00E676' }}>
            Ir para Dashboard
          </button>
        </div>
      </div>
    </motion.div>
  )
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="flex items-center gap-2 mb-4 mt-2 px-1">
      <AlertCircle size={13} style={{ color: '#ef4444' }} />
      <p className="text-xs" style={{ color: '#ef4444' }}>{msg}</p>
    </div>
  )
}

function Spinner({ size = 16 }: { size?: number }) {
  return <div className="border-2 border-t-transparent rounded-full animate-spin" style={{ width: size, height: size, borderColor: '#00E676 transparent transparent transparent' }} />
}

/* ─── Table Components ─────────────────────────────────────────────────────── */

function PosicaoTable({ items }: { items: any[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr style={{ borderBottom: '1px solid #1e293b' }}>
      <Th>Ticker</Th><Th>Tipo</Th><Th align="right">Qtd</Th><Th align="right">Preço</Th><Th align="right">Valor</Th>
    </tr></thead><tbody>{items.map((p, i) => (
      <tr key={i} style={{ borderBottom: '1px solid rgba(30,41,59,0.5)' }}>
        <Td bold>{p.ticker}</Td><Td><span className="font-mono text-[10px] px-1 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b' }}>{p.subtipo ?? p.tipo}</span></Td>
        <Td align="right">{formatNum(p.quantidade)}</Td><Td align="right">{formatBRL(p.preco_fechamento)}</Td><Td align="right">{formatBRL(p.valor_atualizado)}</Td>
      </tr>))}</tbody></table></div>
  )
}

function NegociacaoTable({ items }: { items: any[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr style={{ borderBottom: '1px solid #1e293b' }}>
      <Th>Data</Th><Th>Ticker</Th><Th>Tipo</Th><Th align="right">Qtd</Th><Th align="right">Preço</Th><Th align="right">Valor</Th>
    </tr></thead><tbody>{items.slice(0, 50).map((t, i) => (
      <tr key={i} style={{ borderBottom: '1px solid rgba(30,41,59,0.5)' }}>
        <Td>{t.data}</Td><Td bold>{t.ticker}</Td>
        <Td><span className="text-[10px] font-mono px-1 py-0.5 rounded" style={{ background: t.tipo === 'compra' ? 'rgba(0,230,118,0.08)' : 'rgba(239,68,68,0.08)', color: t.tipo === 'compra' ? '#00E676' : '#ef4444' }}>{t.tipo}</span></Td>
        <Td align="right">{formatNum(t.quantidade)}</Td><Td align="right">{formatBRL(t.preco)}</Td><Td align="right">{formatBRL(t.valor)}</Td>
      </tr>))}</tbody></table>
    {items.length > 50 && <p className="text-[10px] text-center mt-2" style={{ color: '#475569' }}>Mostrando 50 de {items.length} transações</p>}</div>
  )
}

function MovimentacaoTable({ items }: { items: any[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr style={{ borderBottom: '1px solid #1e293b' }}>
      <Th>Data</Th><Th>Produto</Th><Th>Tipo</Th><Th align="right">Valor</Th>
    </tr></thead><tbody>{items.slice(0, 50).map((m, i) => (
      <tr key={i} style={{ borderBottom: '1px solid rgba(30,41,59,0.5)' }}>
        <Td>{m.data}</Td><Td>{m.produto?.slice(0, 30)}</Td>
        <Td><span className="text-[10px] font-mono px-1 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b' }}>{m.categoria}</span></Td>
        <Td align="right"><span style={{ color: m.direcao === 'Credito' ? '#00E676' : '#ef4444' }}>{m.direcao === 'Credito' ? '+' : '-'}{formatBRL(m.valor)}</span></Td>
      </tr>))}</tbody></table>
    {items.length > 50 && <p className="text-[10px] text-center mt-2" style={{ color: '#475569' }}>Mostrando 50 de {items.length} movimentações</p>}</div>
  )
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return <th className="py-2 px-2 font-mono text-[10px] uppercase" style={{ color: '#475569', textAlign: align }}>{children}</th>
}

function Td({ children, bold, align = 'left' }: { children: React.ReactNode; bold?: boolean; align?: 'left' | 'right' }) {
  return <td className="py-1.5 px-2" style={{ color: bold ? '#e2e8f0' : '#94a3b8', fontWeight: bold ? 600 : 400, textAlign: align }}>{children}</td>
}

function formatBRL(v: any): string {
  const n = Number(v); if (!v && v !== 0) return '—'
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatNum(v: any): string {
  const n = Number(v); if (!v && v !== 0) return '—'
  return n.toLocaleString('pt-BR')
}

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg p-2.5" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid #1e293b' }}>
      <p className="text-[10px] font-mono uppercase" style={{ color: '#475569' }}>{label}</p>
      <p className="text-sm font-bold mt-0.5" style={{ color: '#e2e8f0' }}>{value}</p>
    </div>
  )
}
