import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Trash2, AlertTriangle, X, Bot, CheckCircle, XCircle, Loader2, Zap, DollarSign, Target, ChevronDown, FileText } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'

// ─── Budget input mini-component ─────────────────────────────────────────────
function BudgetInput({ budget, onSave }: { budget: number | null; onSave: (v: number | null) => void }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(budget != null ? String(budget) : '')

  if (!editing) {
    return (
      <button
        onClick={() => { setVal(budget != null ? String(budget) : ''); setEditing(true) }}
        className="text-[11px] px-2 py-1 rounded-md transition-all"
        style={{ background: 'rgba(255,193,7,0.06)', border: '1px solid rgba(255,193,7,0.15)', color: '#FFC107' }}
      >
        <DollarSign size={10} className="inline mr-1" />
        {budget != null ? `Orçamento: $${budget.toFixed(2)} · editar` : 'Definir orçamento'}
      </button>
    )
  }

  const save = () => {
    const n = parseFloat(val)
    onSave(isNaN(n) || n <= 0 ? null : n)
    setEditing(false)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px]" style={{ color: '#94a3b8' }}>$</span>
      <input
        autoFocus
        type="number"
        step="0.01"
        min="0"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && save()}
        className="flex-1 px-2 py-1 rounded-md text-xs font-mono outline-none"
        style={{ background: '#0f172a', border: '1px solid #334155', color: '#f1f5f9', width: 80 }}
        placeholder="10.00"
      />
      <button onClick={save} className="text-[10px] px-2 py-1 rounded-md" style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676' }}>Salvar</button>
      <button onClick={() => setEditing(false)} className="text-[10px] px-2 py-1 rounded-md" style={{ color: '#64748b' }}>✕</button>
    </div>
  )
}

export default function SettingsPage() {
  const { userId, userName, portfolioAtivo, setPortfolioAtivo, setPortfolios, reset, tokenUsage, tokenBudget, setTokenBudget, tokenSpentAll } = useStore()
  const navigate = useNavigate()

  // AI provider info
  const [aiInfo, setAiInfo] = useState<{
    provider: string; model: string; key_hint: string; configured: boolean;
    limits?: { tier: string; req_min: number | null; req_day: number | null; tokens_min: number | null; context_window: number | null; pricing_input: number; pricing_output: number; nota: string } | null
  } | null>(null)
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

  // ── Racional da Carteira ───────────────────────────────────────────────────
  const [racional, setRacional] = useState('')
  const [racionalOriginal, setRacionalOriginal] = useState('')
  const [racionalSaving, setRacionalSaving] = useState(false)
  const [racionalSuccess, setRacionalSuccess] = useState(false)
  const [racionalError, setRacionalError] = useState('')

  useEffect(() => {
    if (!portfolioAtivo?.id) return
    api.get(`/portfolio/${portfolioAtivo.id}/alocacao-alvo`)
      .then(r => {
        const rac = r.data?.racional ?? ''
        setRacional(rac)
        setRacionalOriginal(rac)
      })
      .catch(() => {})
  }, [portfolioAtivo?.id])

  const handleRacionalSave = async () => {
    if (!portfolioAtivo?.id) return
    setRacionalSaving(true)
    setRacionalError('')
    setRacionalSuccess(false)
    try {
      await api.patch('/portfolio/racional', { racional: racional })
      setRacionalOriginal(racional)
      setRacionalSuccess(true)
      setTimeout(() => setRacionalSuccess(false), 2500)
    } catch (e: any) {
      setRacionalError(e?.response?.data?.detail ?? 'Erro ao salvar racional.')
    } finally {
      setRacionalSaving(false)
    }
  }

  // ── Alocação Alvo ──────────────────────────────────────────────────────────
  const MODULOS = [
    { key: 'etfs', label: 'ETFs', color: '#00E676' },
    { key: 'fiis', label: 'FIIs', color: '#00BFA5' },
    { key: 'renda_fixa', label: 'Renda Fixa', color: '#1DE9B6' },
    { key: 'momentum', label: 'Momentum', color: '#64FFDA' },
    { key: 'wheel', label: 'Wheel', color: '#00B0FF' },
    { key: 'alpha', label: 'Alpha', color: '#AA00FF' },
    { key: 'dividendos', label: 'Dividendos', color: '#FFD740' },
    { key: 'teses', label: 'Teses', color: '#FF6D00' },
    { key: 'caixa', label: 'Caixa', color: '#475569' },
  ] as const

  const [alvo, setAlvo] = useState<Record<string, number>>({})
  const [alvoOriginal, setAlvoOriginal] = useState<Record<string, number>>({})
  const [alvoLoading, setAlvoLoading] = useState(true)
  const [alvoSaving, setAlvoSaving] = useState(false)
  const [alvoSuccess, setAlvoSuccess] = useState(false)
  const [alvoError, setAlvoError] = useState('')

  const loadAlvo = () => {
    if (!portfolioAtivo?.id) return
    setAlvoLoading(true)
    api.get(`/portfolio/${portfolioAtivo.id}/alocacao-alvo`)
      .then(r => { setAlvo(r.data); setAlvoOriginal(r.data) })
      .catch(() => setAlvoError('Erro ao carregar metas'))
      .finally(() => setAlvoLoading(false))
  }
  useEffect(() => { loadAlvo() }, [portfolioAtivo?.id])

  const alvoTotal = Object.values(alvo).reduce((s, v) => s + (v || 0), 0)
  const alvoDirty = JSON.stringify(alvo) !== JSON.stringify(alvoOriginal)
  const alvoValid = Math.abs(alvoTotal - 100) <= 0.5

  const handleAlvoChange = (key: string, val: string) => {
    const n = parseFloat(val)
    setAlvo(prev => ({ ...prev, [key]: isNaN(n) ? 0 : Math.max(0, Math.min(100, n)) }))
    setAlvoError('')
  }

  const handleAlvoSave = async () => {
    if (!portfolioAtivo?.id || !alvoValid) return
    setAlvoSaving(true)
    setAlvoError('')
    setAlvoSuccess(false)
    try {
      const r = await api.put(`/portfolio/${portfolioAtivo.id}/alocacao-alvo`, alvo)
      if (r.data.ok) {
        setAlvoOriginal({ ...alvo })
        setAlvoSuccess(true)
        setTimeout(() => setAlvoSuccess(false), 2500)
      }
    } catch (e: any) {
      setAlvoError(e?.response?.data?.detail ?? 'Erro ao salvar metas.')
    } finally {
      setAlvoSaving(false)
    }
  }

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

  // Apagar carteira individual
  const [delPortStep, setDelPortStep] = useState<0 | 1 | 2>(0)
  const [delPortId, setDelPortId] = useState<number | null>(null)
  const [delPortConfirm, setDelPortConfirm] = useState('')
  const [delPortLoading, setDelPortLoading] = useState(false)
  const [delPortError, setDelPortError] = useState('')
  const allPortfolios = useStore(s => s.portfolios)
  const delPortSelected = allPortfolios.find(p => p.id === delPortId) ?? null

  // Carrega lista de portfólios
  useEffect(() => {
    api.get('/portfolio/listar').then(r => setPortfolios(r.data)).catch(() => {})
  }, [])

  const handleDelPortStart = () => {
    setDelPortStep(1)
    setDelPortId(null)
    setDelPortConfirm('')
    setDelPortError('')
  }
  const handleDelPortCancel = () => {
    setDelPortStep(0)
    setDelPortId(null)
    setDelPortConfirm('')
    setDelPortError('')
  }
  const handleDelPortFinal = async () => {
    if (!delPortSelected) return
    if (delPortConfirm.trim().toLowerCase() !== delPortSelected.nome.toLowerCase()) {
      setDelPortError('Nome não confere. Digite exatamente como aparece acima.')
      return
    }
    setDelPortLoading(true)
    setDelPortError('')
    try {
      const r = await api.delete(`/portfolio/${delPortSelected.id}`)
      // Atualiza store
      const updated = allPortfolios.filter(p => p.id !== delPortSelected.id)
      setPortfolios(updated)
      // Se era a ativa, atualiza para a nova ativa
      if (portfolioAtivo?.id === delPortSelected.id) {
        const novoAtivoId = r.data.novo_ativo_id
        const nova = updated.find(p => p.id === novoAtivoId) ?? updated[0] ?? null
        setPortfolioAtivo(nova)
        window.dispatchEvent(new Event('portfolio-changed'))
      }
      setDelPortStep(0)
    } catch (e: any) {
      setDelPortError(e?.response?.data?.detail ?? 'Erro ao apagar carteira.')
    } finally {
      setDelPortLoading(false)
    }
  }

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

      {/* Racional da Carteira */}
      <div className="apex-card p-5 mb-8">
        <div className="flex items-center gap-2 mb-3">
          <FileText size={15} style={{ color: '#00E676' }} />
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Racional da Carteira</p>
        </div>
        <p className="text-xs mb-3" style={{ color: '#64748b' }}>
          Descreva o racional da sua carteira — filosofia geral e por que de cada módulo. O APEX Brain usa este texto para entender suas decisões. Escreva por seções (ex: &quot;ETFs: ...&quot;, &quot;FIIs: ...&quot;).
        </p>
        <textarea
          value={racional}
          onChange={(e) => { setRacional(e.target.value); setRacionalError('') }}
          placeholder={"Filosofia geral: ...\nETFs: por que tenho ETFs, qual o objetivo...\nFIIs: renda passiva, quais critérios...\nTeses: convicções de longo prazo, por que cada uma...\nMomentum: trades táticos, critérios de entrada...\nRenda Fixa: proteção, % do CDI que busco..."}
          rows={6}
          className="w-full px-3 py-2 rounded-lg text-sm bg-slate-900/80 border border-slate-600 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-green-500/50 resize-y"
          disabled={racionalSaving}
        />
        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={handleRacionalSave}
            disabled={racionalSaving || racional === racionalOriginal}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.35)' }}
          >
            {racionalSaving ? <Loader2 size={14} className="animate-spin" /> : racionalSuccess ? <CheckCircle size={14} /> : null}
            {racionalSaving ? 'Salvando...' : racionalSuccess ? 'Salvo' : 'Salvar'}
          </button>
          <span className="text-xs font-mono" style={{ color: '#475569' }}>{racional.length}/2000</span>
        </div>
        {racionalError && <p className="text-sm mt-2" style={{ color: '#ef4444' }}>{racionalError}</p>}
      </div>

      {/* Alocação Alvo */}
      <div className="apex-card p-5 mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Target size={15} style={{ color: '#00E676' }} />
          <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Alocação Alvo (Metas)</p>
        </div>
        <p className="text-xs mb-4" style={{ color: '#64748b' }}>
          Defina a porcentagem-alvo de cada módulo. A soma deve totalizar 100%.
        </p>

        {alvoLoading ? (
          <div className="flex items-center gap-2 py-4">
            <Loader2 size={14} className="animate-spin" style={{ color: '#64748b' }} />
            <span className="text-xs" style={{ color: '#64748b' }}>Carregando metas...</span>
          </div>
        ) : (
          <>
            <div className="space-y-2.5">
              {MODULOS.map(m => (
                <div key={m.key} className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: m.color }} />
                  <span className="text-sm w-24 flex-shrink-0" style={{ color: '#cbd5e1' }}>{m.label}</span>
                  <div className="flex-1 relative">
                    <input
                      type="range"
                      min={0} max={100} step={0.5}
                      value={alvo[m.key] ?? 0}
                      onChange={e => handleAlvoChange(m.key, e.target.value)}
                      className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
                      style={{
                        background: `linear-gradient(to right, ${m.color} 0%, ${m.color} ${alvo[m.key] ?? 0}%, #1e293b ${alvo[m.key] ?? 0}%, #1e293b 100%)`,
                        accentColor: m.color,
                      }}
                    />
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <input
                      type="number"
                      min={0} max={100} step={0.5}
                      value={alvo[m.key] ?? 0}
                      onChange={e => handleAlvoChange(m.key, e.target.value)}
                      className="w-14 px-1.5 py-1 rounded text-xs font-mono text-right outline-none"
                      style={{ background: '#0f172a', border: '1px solid #334155', color: '#f1f5f9' }}
                    />
                    <span className="text-[10px]" style={{ color: '#475569' }}>%</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Total + Save */}
            <div className="flex items-center justify-between mt-4 pt-3" style={{ borderTop: '1px solid #1e293b' }}>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono" style={{ color: '#64748b' }}>Total:</span>
                <span className="text-sm font-bold font-mono" style={{
                  color: alvoValid ? '#00E676' : '#FF5252'
                }}>
                  {alvoTotal.toFixed(1)}%
                </span>
                {!alvoValid && <span className="text-[10px]" style={{ color: '#FF5252' }}>Deve somar 100%</span>}
              </div>
              <button
                onClick={handleAlvoSave}
                disabled={alvoSaving || !alvoDirty || !alvoValid}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.35)' }}
              >
                {alvoSaving ? <Loader2 size={14} className="animate-spin" /> : alvoSuccess ? <CheckCircle size={14} /> : null}
                {alvoSaving ? 'Salvando...' : alvoSuccess ? 'Salvo' : 'Salvar metas'}
              </button>
            </div>
            {alvoError && <p className="text-xs mt-2" style={{ color: '#ef4444' }}>{alvoError}</p>}
          </>
        )}
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

            {/* Token usage — simple */}
            {aiInfo.limits && (() => {
              const isFree = aiInfo.limits!.tier === 'free'
              const today = new Date().toISOString().slice(0, 10)
              const usedToday = tokenUsage?.date === today ? (tokenUsage.totalIn + tokenUsage.totalOut) : 0
              const costToday = tokenUsage?.date === today ? tokenUsage.totalCost : 0
              const budgetPerMin = aiInfo.limits!.tokens_min || 0
              const fmtK = (n: number) => n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + 'M' : n >= 1_000 ? (n / 1_000).toFixed(1) + 'K' : String(n)
              const saldo = tokenBudget != null ? Math.max(0, tokenBudget - tokenSpentAll) : null

              return (
                <div className="rounded-lg px-3 py-2.5 space-y-2" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid #1e293b' }}>
                  {/* Tier badge */}
                  <div className="flex items-center gap-2">
                    <Zap size={13} style={{ color: isFree ? '#00E676' : '#FFC107' }} />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
                      style={{
                        background: isFree ? 'rgba(0,230,118,0.1)' : 'rgba(255,193,7,0.1)',
                        color: isFree ? '#00E676' : '#FFC107',
                        border: `1px solid ${isFree ? 'rgba(0,230,118,0.25)' : 'rgba(255,193,7,0.25)'}`,
                      }}>
                      {isFree ? 'GRÁTIS' : 'PAGO'}
                    </span>
                    {isFree && budgetPerMin > 0 && (
                      <span className="text-[10px]" style={{ color: '#64748b' }}>
                        {fmtK(budgetPerMin)} tok/min
                      </span>
                    )}
                  </div>

                  {/* Saldo (paid only) */}
                  {!isFree && (
                    <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid #1e293b' }}>
                      {saldo != null ? (
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-[10px] uppercase tracking-wider" style={{ color: '#64748b' }}>Saldo disponível</p>
                            <p className="text-lg font-bold font-mono" style={{ color: saldo > 1 ? '#00E676' : saldo > 0 ? '#FFC107' : '#FF5252' }}>
                              ${saldo.toFixed(2)}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-[10px]" style={{ color: '#475569' }}>Gasto total</p>
                            <p className="text-xs font-mono" style={{ color: '#94a3b8' }}>${tokenSpentAll.toFixed(4)}</p>
                          </div>
                        </div>
                      ) : (
                        <p className="text-[11px]" style={{ color: '#64748b' }}>
                          Defina um orçamento abaixo para acompanhar seu saldo
                        </p>
                      )}
                      {saldo != null && tokenBudget! > 0 && (
                        <div className="mt-1.5 w-full h-1.5 rounded-full overflow-hidden" style={{ background: '#1e293b' }}>
                          <div className="h-full rounded-full transition-all" style={{
                            width: `${Math.min(100, (tokenSpentAll / tokenBudget!) * 100)}%`,
                            background: saldo > 1 ? '#00E676' : saldo > 0 ? '#FFC107' : '#FF5252',
                          }} />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Budget input (paid only) */}
                  {!isFree && (
                    <BudgetInput budget={tokenBudget} onSave={setTokenBudget} />
                  )}

                  {/* Today stats */}
                  <div className="flex items-center justify-between text-[11px]">
                    <span style={{ color: '#64748b' }}>
                      Hoje: <span style={{ color: '#f1f5f9' }}>{fmtK(usedToday)} tokens</span>
                    </span>
                    {!isFree && (
                      <span style={{ color: '#64748b' }}>
                        Custo hoje: <span style={{ color: '#f1f5f9' }}>${costToday.toFixed(4)}</span>
                      </span>
                    )}
                  </div>

                  {aiInfo.limits!.nota && (
                    <p className="text-[10px]" style={{ color: '#475569' }}>{aiInfo.limits!.nota}</p>
                  )}
                </div>
              )
            })()}
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

        {/* Apagar carteira individual */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: '#f1f5f9' }}>Apagar uma carteira</p>
            <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
              Escolha qual carteira deletar. Remove o portfólio, posições e histórico.
              {allPortfolios.length <= 1 && <span style={{ color: '#ef4444' }}> Você precisa ter mais de uma carteira para usar esta opção.</span>}
            </p>
          </div>
          {delPortStep === 0 && (
            <button
              onClick={handleDelPortStart}
              disabled={allPortfolios.length <= 1}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium flex-shrink-0 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444' }}
              onMouseEnter={(e) => { if (allPortfolios.length > 1) e.currentTarget.style.background = 'rgba(239,68,68,0.15)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)' }}
            >
              <Trash2 size={14} />
              Apagar
            </button>
          )}
        </div>

        <AnimatePresence>
          {delPortStep >= 1 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 overflow-hidden"
            >
              <div className="rounded-lg p-4 space-y-3"
                style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>

                {/* Seletor de carteira */}
                <p className="text-sm" style={{ color: '#f1f5f9' }}>Selecione a carteira a apagar:</p>
                <div className="relative">
                  <select
                    value={delPortId ?? ''}
                    onChange={e => { setDelPortId(Number(e.target.value) || null); setDelPortConfirm(''); setDelPortError(''); setDelPortStep(1) }}
                    className="w-full appearance-none px-3 py-2 pr-8 rounded-lg text-sm outline-none cursor-pointer"
                    style={{ background: '#0f172a', border: '1px solid #334155', color: '#f1f5f9' }}
                  >
                    <option value="">— Escolha —</option>
                    {allPortfolios.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.nome} ({p.tipo}){p.id === portfolioAtivo?.id ? ' ← ativa' : ''}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#64748b' }} />
                </div>

                {/* Confirmação por nome */}
                {delPortId && delPortStep >= 1 && (
                  <>
                    <button
                      onClick={() => setDelPortStep(2)}
                      disabled={!delPortId}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                      style={{ background: '#ef4444', color: '#fff', display: delPortStep === 2 ? 'none' : undefined }}
                    >
                      Continuar
                    </button>
                  </>
                )}

                {delPortStep === 2 && delPortSelected && (
                  <>
                    <p className="text-sm" style={{ color: '#f1f5f9' }}>
                      Para confirmar, digite o nome da carteira:{' '}
                      <span className="font-mono font-semibold" style={{ color: '#ef4444' }}>{delPortSelected.nome}</span>
                    </p>
                    <input
                      autoFocus
                      value={delPortConfirm}
                      onChange={e => { setDelPortConfirm(e.target.value); setDelPortError('') }}
                      onKeyDown={e => e.key === 'Enter' && handleDelPortFinal()}
                      placeholder={`Digite "${delPortSelected.nome}"`}
                      className="apex-input w-full text-sm"
                      style={{ borderColor: delPortError ? 'rgba(239,68,68,0.5)' : undefined }}
                    />
                    {delPortError && <p className="text-xs" style={{ color: '#ef4444' }}>{delPortError}</p>}
                    <div className="flex gap-2">
                      <button
                        onClick={handleDelPortFinal}
                        disabled={delPortLoading || !delPortConfirm.trim()}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all"
                        style={{
                          background: delPortLoading || !delPortConfirm.trim() ? '#1e293b' : '#ef4444',
                          color: delPortLoading || !delPortConfirm.trim() ? '#475569' : '#fff',
                          cursor: delPortLoading || !delPortConfirm.trim() ? 'not-allowed' : 'pointer',
                        }}
                      >
                        <Trash2 size={13} />
                        {delPortLoading ? 'Apagando...' : 'Apagar definitivamente'}
                      </button>
                      <button
                        onClick={handleDelPortCancel}
                        disabled={delPortLoading}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                        style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                      >
                        <X size={13} />
                        Cancelar
                      </button>
                    </div>
                  </>
                )}

                {delPortStep === 1 && !delPortId && (
                  <button
                    onClick={handleDelPortCancel}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid #1e293b', color: '#94a3b8' }}
                  >
                    <X size={13} />
                    Cancelar
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="my-4" style={{ height: '1px', background: 'rgba(239,68,68,0.1)' }} />

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: '#f1f5f9' }}>Apagar conta completa</p>
            <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
              Remove permanentemente o usuário <span className="font-semibold" style={{ color: '#94a3b8' }}>{userName}</span>, todos os portfólios, posições e histórico.
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
