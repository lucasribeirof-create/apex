import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Trash2, AlertTriangle, X, Bot, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

export default function SettingsPage() {
  const { userId, userName, portfolioAtivo, setPortfolioAtivo, setPortfolios, reset } = useStore()
  const navigate = useNavigate()

  // AI provider info
  const [aiInfo, setAiInfo] = useState<{ provider: string; model: string; key_hint: string; configured: boolean } | null>(null)
  const [testingAI, setTestingAI] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const loadAI = () => api.get('/settings/ai').then((r) => setAiInfo(r.data)).catch(() => null)

  useEffect(() => { loadAI() }, [])

  const handleChangeAI = () => {
    window.location.replace('/configurar-ia')
  }

  const handleTestAI = async () => {
    setTestingAI(true)
    setTestResult(null)
    try {
      const r = await api.post('/settings/ai/test-saved')
      setTestResult({ ok: r.data.ok, msg: r.data.ok ? 'Chave válida e funcionando ✓' : (r.data.erro || 'Falhou.') })
    } catch (e: any) {
      setTestResult({ ok: false, msg: e?.response?.data?.detail || 'Erro ao testar.' })
    } finally {
      setTestingAI(false)
    }
  }

  // Nome da carteira (edição) — usa Portfolio.nome, não User.name
  const nomeCarteiraAtual = portfolioAtivo?.nome ?? ''
  const [nameEdit, setNameEdit] = useState(nomeCarteiraAtual)
  const [nameSaving, setNameSaving] = useState(false)
  const [nameError, setNameError] = useState('')
  const [nameSuccess, setNameSuccess] = useState(false)
  useEffect(() => { setNameEdit(portfolioAtivo?.nome ?? '') }, [portfolioAtivo?.nome])

  const handleSaveName = async () => {
    const trimmed = nameEdit.trim()
    if (!trimmed) {
      setNameError('Nome da carteira não pode ser vazio.')
      return
    }
    if (!portfolioAtivo?.id) {
      setNameError('Nenhuma carteira ativa.')
      return
    }
    if (trimmed === nomeCarteiraAtual) {
      setNameError('')
      return
    }
    setNameSaving(true)
    setNameError('')
    setNameSuccess(false)
    try {
      const r = await api.post(`/portfolio/${portfolioAtivo.id}/atualizar-nome`, { nome: trimmed })
      const novoNome = r.data.nome ?? trimmed
      setPortfolioAtivo(portfolioAtivo ? { ...portfolioAtivo, nome: novoNome } : null)
      setPortfolios(useStore.getState().portfolios.map(p => p.id === portfolioAtivo.id ? { ...p, nome: novoNome } : p))
      setNameSuccess(true)
      setTimeout(() => setNameSuccess(false), 2500)
    } catch (e: any) {
      setNameError(e?.response?.data?.detail ?? 'Erro ao atualizar nome. Tente novamente.')
    } finally {
      setNameSaving(false)
    }
  }

  // Step 0 = idle, 1 = first confirm, 2 = type name confirm
  const [deleteStep, setDeleteStep] = useState<0 | 1 | 2>(0)
  const [nameInput, setNameInput] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  // Limpar todas as carteiras (mantém usuário)
  const [clearStep, setClearStep] = useState<0 | 1>(0)
  const [clearing, setClearing] = useState(false)
  const [clearError, setClearError] = useState('')

  const handleClearStart = () => { setClearStep(1); setClearError('') }
  const handleClearCancel = () => { setClearStep(0); setClearError('') }
  const handleClearConfirm = async () => {
    setClearing(true)
    setClearError('')
    try {
      await api.delete('/portfolios/all')
      navigate('/onboarding', { replace: true })
    } catch (e: any) {
      setClearError(e?.response?.data?.detail || 'Erro ao limpar carteiras.')
      setClearing(false)
    }
  }

  const handleDeleteStart = () => {
    setDeleteStep(1)
    setNameInput('')
    setError('')
  }

  const handleDeleteConfirm1 = () => {
    setDeleteStep(2)
  }

  const handleDeleteFinal = async () => {
    if (nameInput.trim().toLowerCase() !== (userName ?? '').toLowerCase()) {
      setError('Nome não confere. Digite exatamente como aparece acima.')
      return
    }
    setDeleting(true)
    setError('')
    try {
      await api.delete(`/onboarding/usuarios/${userId}`)
    } catch (e: any) {
      // 404 = usuário já não existe no banco — trata como sucesso
      if (e?.response?.status !== 404) {
        setError('Erro ao apagar carteira. Tente novamente.')
        setDeleting(false)
        return
      }
    }
    reset()
    navigate('/selecionar', { replace: true })
  }

  const handleCancel = () => {
    setDeleteStep(0)
    setNameInput('')
    setError('')
  }

  return (
    <div className="p-8 max-w-xl">
      {/* Header */}
      <div className="flex items-center gap-2 mb-8">
        <Settings size={18} style={{ color: '#00E676' }} />
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Configurações</h1>
      </div>

      {/* Usuário e carteira ativa */}
      <div className="apex-card p-5 mb-6">
        <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
          Usuário e carteira ativa
        </p>
        <p className="text-sm mb-1" style={{ color: '#94a3b8' }}>
          <span style={{ color: '#64748b' }}>Nome do usuário:</span> <span style={{ color: '#f1f5f9', fontWeight: 500 }}>{userName ?? '—'}</span>
        </p>
        <p className="text-sm mb-0" style={{ color: '#94a3b8' }}>
          <span style={{ color: '#64748b' }}>Carteira ativa:</span> <span style={{ color: '#f1f5f9', fontWeight: 500 }}>{portfolioAtivo?.nome ?? '—'}</span> <span className="font-mono text-xs" style={{ color: '#64748b' }}>· ID #{portfolioAtivo?.id ?? '—'}</span>
        </p>
      </div>

      {/* Nome da carteira (editar) — nome do portfólio, não do usuário */}
      <div className="apex-card p-5 mb-8">
        <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
          Nome da carteira
        </p>
        <p className="text-sm mb-3" style={{ color: '#94a3b8' }}>
          Esse é o nome desta carteira/portfólio (ex.: &quot;Carteira Real&quot;, &quot;Aposentadoria&quot;). Aparece na lista ao selecionar carteira. O nome do usuário ({userName ?? 'você'}) não é alterado aqui.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={nameEdit}
            onChange={(e) => { setNameEdit(e.target.value); setNameError('') }}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
            placeholder="Nome da carteira"
            className="flex-1 min-w-[180px] px-3 py-2 rounded-lg text-sm bg-slate-900/80 border border-slate-600 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-green-500/50"
            disabled={nameSaving}
          />
          <button
            onClick={handleSaveName}
            disabled={nameSaving || !portfolioAtivo?.id || (nameEdit.trim() === nomeCarteiraAtual)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: (nameSaving || nameEdit.trim() !== nomeCarteiraAtual) ? 'rgba(0,230,118,0.15)' : 'rgba(0,230,118,0.2)', color: '#00E676', border: '1px solid rgba(0,230,118,0.35)' }}
          >
            {nameSaving ? <Loader2 size={14} className="animate-spin" /> : nameSuccess ? <CheckCircle size={14} /> : null}
            {nameSaving ? 'Salvando...' : nameSuccess ? 'Salvo' : 'Salvar'}
          </button>
        </div>
        {nameError && <p className="text-sm mt-2" style={{ color: '#ef4444' }}>{nameError}</p>}
      </div>

      {/* AI provider */}
      <div className="apex-card p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Bot size={15} style={{ color: '#64748b' }} />
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Motor de IA</p>
        </div>
        {aiInfo ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold capitalize" style={{ color: '#f1f5f9' }}>
                  {aiInfo.provider === 'gemini' ? 'Google Gemini'
                    : aiInfo.provider === 'anthropic' ? 'Claude — Anthropic'
                    : aiInfo.provider === 'openai' ? 'GPT-4o Mini — OpenAI'
                    : aiInfo.provider === 'groq' ? 'Groq — Llama 3 (Gratuito)'
                    : aiInfo.provider === 'grok' ? 'Grok — xAI'
                    : aiInfo.provider}
                </p>
                <p className="text-xs font-mono mt-0.5" style={{ color: '#475569' }}>
                  {aiInfo.model} · chave {aiInfo.key_hint}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={handleTestAI}
                  disabled={testingAI}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5"
                  style={{ background: 'rgba(0,230,118,0.08)', border: '1px solid rgba(0,230,118,0.2)', color: '#00E676' }}
                >
                  {testingAI ? <Loader2 size={12} className="animate-spin" /> : null}
                  {testingAI ? 'Testando…' : 'Testar'}
                </button>
                <button
                  onClick={handleChangeAI}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#334155' }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#1e293b' }}
                >
                  Trocar IA
                </button>
              </div>
            </div>
            {testResult && (
              <div className="flex items-start gap-2 rounded-lg px-3 py-2 text-xs"
                style={{ background: testResult.ok ? 'rgba(0,230,118,0.06)' : 'rgba(255,82,82,0.06)', border: `1px solid ${testResult.ok ? 'rgba(0,230,118,0.2)' : 'rgba(255,82,82,0.2)'}` }}>
                {testResult.ok
                  ? <CheckCircle size={13} style={{ color: '#00E676', flexShrink: 0, marginTop: 1 }} />
                  : <XCircle size={13} style={{ color: '#FF5252', flexShrink: 0, marginTop: 1 }} />}
                <span style={{ color: testResult.ok ? '#00E676' : '#FF5252' }}>{testResult.msg}</span>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm" style={{ color: '#475569' }}>Carregando...</p>
        )}
      </div>

      {/* Danger zone */}
      <div className="rounded-xl p-5" style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.15)' }}>
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle size={15} style={{ color: '#ef4444' }} />
          <p className="text-sm font-semibold uppercase tracking-wider" style={{ color: '#ef4444' }}>Zona de perigo</p>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: '#f1f5f9' }}>Limpar todas as carteiras</p>
            <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
              Remove todos os portfólios, posições e histórico. O usuário <span className="font-semibold" style={{ color: '#94a3b8' }}>{userName}</span> é mantido e você pode criar uma nova carteira do zero.
            </p>
          </div>
          {clearStep === 0 && (
            <button
              onClick={handleClearStart}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium flex-shrink-0 transition-all"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.15)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
            >
              <Trash2 size={14} />
              Limpar
            </button>
          )}
        </div>

        <AnimatePresence>
          {clearStep === 1 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                <p className="text-sm" style={{ color: '#f1f5f9' }}>
                  Todos os portfólios de <span className="font-semibold" style={{ color: '#ef4444' }}>{userName}</span> serão apagados. O usuário é mantido. Confirmar?
                </p>
                {clearError && <p className="text-xs" style={{ color: '#ef4444' }}>{clearError}</p>}
                <div className="flex gap-2">
                  <button
                    onClick={handleClearConfirm}
                    disabled={clearing}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                    style={{ background: clearing ? '#1e293b' : '#ef4444', color: clearing ? '#475569' : '#fff', cursor: clearing ? 'not-allowed' : 'pointer' }}
                  >
                    <Trash2 size={13} />
                    {clearing ? 'Limpando...' : 'Sim, limpar tudo'}
                  </button>
                  <button
                    onClick={handleClearCancel}
                    disabled={clearing}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="my-4" style={{ height: '1px', background: 'rgba(239,68,68,0.1)' }} />

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: '#f1f5f9' }}>Apagar esta carteira</p>
            <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
              Remove permanentemente o usuário, portfólio, todas as posições e o histórico de briefings.
              Esta ação não pode ser desfeita.
            </p>
          </div>
          {deleteStep === 0 && (
            <button
              onClick={handleDeleteStart}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium flex-shrink-0 transition-all"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.15)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
            >
              <Trash2 size={14} />
              Apagar
            </button>
          )}
        </div>

        {/* Step 1 — first confirmation */}
        <AnimatePresence>
          {deleteStep === 1 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                <p className="text-sm" style={{ color: '#f1f5f9' }}>
                  Tem certeza? Todos os dados de <span className="font-semibold" style={{ color: '#ef4444' }}>{userName}</span> serão apagados para sempre.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteConfirm1}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                    style={{ background: '#ef4444', color: '#fff' }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = '#dc2626' }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = '#ef4444' }}
                  >
                    Sim, continuar
                  </button>
                  <button
                    onClick={handleCancel}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                </div>
              </div>
            </motion.div>
          )}

          {/* Step 2 — type name to confirm */}
          {deleteStep === 2 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
                <p className="text-sm" style={{ color: '#f1f5f9' }}>
                  Para confirmar, digite o nome da carteira:{' '}
                  <span className="font-mono font-semibold" style={{ color: '#ef4444' }}>{userName}</span>
                </p>
                <input
                  autoFocus
                  value={nameInput}
                  onChange={(e) => { setNameInput(e.target.value); setError('') }}
                  onKeyDown={(e) => e.key === 'Enter' && handleDeleteFinal()}
                  placeholder={`Digite "${userName}"`}
                  className="apex-input w-full text-sm"
                  style={{ borderColor: error ? 'rgba(239,68,68,0.5)' : undefined }}
                />
                {error && (
                  <p className="text-xs" style={{ color: '#ef4444' }}>{error}</p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteFinal}
                    disabled={deleting || !nameInput.trim()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                    style={{
                      background: deleting || !nameInput.trim() ? '#1e293b' : '#ef4444',
                      color: deleting || !nameInput.trim() ? '#475569' : '#fff',
                      cursor: deleting || !nameInput.trim() ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <Trash2 size={13} />
                    {deleting ? 'Apagando...' : 'Apagar definitivamente'}
                  </button>
                  <button
                    onClick={handleCancel}
                    disabled={deleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
