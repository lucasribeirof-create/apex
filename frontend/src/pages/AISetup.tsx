import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExternalLink, Key, CheckCircle, Loader2, Zap, Brain, Bot } from 'lucide-react'
import api from '@/services/api'

type Provider = 'gemini' | 'anthropic' | 'openai'

const PROVIDERS = [
  {
    id: 'gemini' as Provider,
    name: 'Google Gemini',
    subtitle: 'gemini-2.0-flash',
    badge: 'GRATUITO',
    badgeColor: '#00C853',
    badgeBg: 'rgba(0,200,83,0.12)',
    description: 'Grátis com conta Google. Sem cartão de crédito.',
    keyUrl: 'https://aistudio.google.com/apikey',
    keyLabel: 'Abrir Google AI Studio',
    placeholder: 'AIzaSy...',
    icon: <Zap size={20} />,
    iconColor: '#00C853',
    iconBg: 'rgba(0,200,83,0.1)',
    steps: [
      { text: 'Clique em "Abrir Google AI Studio" abaixo', link: null },
      { text: 'Faça login com sua conta Google', link: null },
      { text: 'Clique em "Create API key"', link: null },
      { text: 'Copie a chave gerada (começa com AIzaSy...)', link: null },
      { text: 'Cole no campo abaixo e clique em Salvar', link: null },
    ],
  },
  {
    id: 'anthropic' as Provider,
    name: 'Claude',
    subtitle: 'claude-sonnet-4-5',
    badge: 'MELHOR QUALIDADE',
    badgeColor: '#FF6B35',
    badgeBg: 'rgba(255,107,53,0.12)',
    description: 'Melhor para análise financeira. Custo muito baixo (~R$0,01 por conversa).',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    keyLabel: 'Abrir Console da Anthropic',
    placeholder: 'sk-ant-...',
    icon: <Brain size={20} />,
    iconColor: '#FF6B35',
    iconBg: 'rgba(255,107,53,0.1)',
    steps: [
      { text: 'Clique em "Abrir Console da Anthropic" abaixo', link: null },
      { text: 'Crie uma conta ou faça login', link: null },
      { text: 'No menu lateral, clique em "API Keys"', link: null },
      { text: 'Clique em "Create Key", dê um nome qualquer', link: null },
      { text: 'Copie a chave (começa com sk-ant-...)', link: null },
      { text: 'Cole no campo abaixo e clique em Salvar', link: null },
    ],
  },
  {
    id: 'openai' as Provider,
    name: 'GPT-4o Mini',
    subtitle: 'gpt-4o-mini',
    badge: 'POPULAR',
    badgeColor: '#00BCD4',
    badgeBg: 'rgba(0,188,212,0.12)',
    description: 'Modelo rápido da OpenAI. Requer crédito mínimo de $5 pré-pago.',
    keyUrl: 'https://platform.openai.com/api-keys',
    keyLabel: 'Abrir Platform OpenAI',
    placeholder: 'sk-proj-...',
    icon: <Bot size={20} />,
    iconColor: '#00BCD4',
    iconBg: 'rgba(0,188,212,0.1)',
    steps: [
      { text: 'Clique em "Abrir Platform OpenAI" abaixo', link: null },
      { text: 'Crie uma conta ou faça login', link: null },
      { text: 'Adicione crédito em Settings → Billing (mín. $5)', link: 'https://platform.openai.com/settings/billing' },
      { text: 'Vá em "API Keys" → "Create new secret key"', link: null },
      { text: 'Copie a chave (começa com sk-proj-...)', link: null },
      { text: 'Cole no campo abaixo e clique em Salvar', link: null },
    ],
  },
]

export default function AISetupPage() {
  const [selected, setSelected] = useState<Provider>('gemini')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // provedores já configurados: { gemini: {configured, key_hint}, ... }
  const [savedProviders, setSavedProviders] = useState<Record<string, { configured: boolean; key_hint: string; model: string }>>({})

  // Carrega provedores já salvos ao abrir a tela
  useEffect(() => {
    api.get('/settings/ai')
      .then((r) => { if (r.data.all_providers) setSavedProviders(r.data.all_providers) })
      .catch(() => null)
  }, [])

  const provider = PROVIDERS.find((p) => p.id === selected)!
  const alreadySaved = savedProviders[selected]?.configured === true

  // Troca para provedor já configurado — sem digitar chave
  const handleSwitch = async () => {
    setLoading(true)
    setError('')
    try {
      await api.patch('/settings/ai/ativo', { provider: selected })
      window.location.replace('/selecionar')
    } catch {
      setError('Erro ao trocar provedor.')
    } finally {
      setLoading(false)
    }
  }

  // Salva nova chave para este provedor
  const handleSave = async () => {
    if (!apiKey.trim()) { setError('Cole a chave de API antes de continuar.'); return }
    setLoading(true)
    setError('')
    try {
      await api.post('/settings/ai', { provider: selected, api_key: apiKey.trim(), model: provider.subtitle })
      window.location.replace('/selecionar')
    } catch {
      setError('Não foi possível salvar. Verifique se a chave está correta.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: '#0a0e17' }}>
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <span className="text-lg font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <div>
            <h1 className="font-bold text-xl tracking-tight" style={{ color: '#f1f5f9' }}>APEX</h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>Manager</p>
          </div>
        </div>

        {/* Header */}
        <div className="mb-8 text-center">
          <h2 className="text-xl font-bold mb-2" style={{ color: '#f1f5f9' }}>Escolha o motor de IA</h2>
          <p className="text-sm" style={{ color: '#64748b' }}>
            A IA será o seu gestor — analisa, explica e propõe estratégias para a sua carteira.
          </p>
        </div>

        {/* Provider cards */}
        <div className="space-y-3 mb-6">
          {PROVIDERS.map((p, i) => {
            const isActive = selected === p.id
            const saved = savedProviders[p.id]
            return (
              <motion.button
                key={p.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                onClick={() => { setSelected(p.id); setApiKey(''); setError('') }}
                className="w-full text-left p-4 rounded-xl flex items-start gap-4 transition-all"
                style={{
                  background: isActive ? 'rgba(15,23,42,0.9)' : 'rgba(15,23,42,0.5)',
                  border: isActive ? `1.5px solid ${p.iconColor}55` : '1px solid #1e293b',
                  boxShadow: isActive ? `0 0 16px ${p.iconColor}18` : 'none',
                }}
              >
                {/* Icon */}
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ background: p.iconBg, color: p.iconColor }}
                >
                  {p.icon}
                </div>

                {/* Text */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm" style={{ color: '#f1f5f9' }}>{p.name}</span>
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded font-bold"
                      style={{ background: p.badgeBg, color: p.badgeColor }}>
                      {p.badge}
                    </span>
                    {saved?.configured && (
                      <span className="text-xs font-mono px-1.5 py-0.5 rounded font-bold"
                        style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676' }}>
                        ✓ CONFIGURADO
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono mt-0.5 mb-1" style={{ color: '#475569' }}>
                    {p.subtitle}{saved?.key_hint ? ` · chave ${saved.key_hint}` : ''}
                  </p>
                  <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
                    {p.description}
                  </p>
                </div>

                {/* Check */}
                {isActive && (
                  <CheckCircle size={18} className="flex-shrink-0 mt-0.5" style={{ color: p.iconColor }} />
                )}
              </motion.button>
            )
          })}
        </div>

        {/* Steps + API Key input — só mostra se não estiver configurado */}
        <AnimatePresence mode="wait">
          {alreadySaved ? (
            <motion.div
              key={`saved-${selected}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="rounded-xl p-4 mb-4 flex items-center gap-3"
              style={{ background: 'rgba(0,230,118,0.05)', border: '1px solid rgba(0,230,118,0.2)' }}
            >
              <CheckCircle size={18} style={{ color: '#00E676', flexShrink: 0 }} />
              <div>
                <p className="text-sm font-semibold" style={{ color: '#f1f5f9' }}>Chave já configurada</p>
                <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                  Chave {savedProviders[selected]?.key_hint} salva. Clique em "Usar esta IA" para ativar.
                </p>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key={`new-${selected}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="rounded-xl p-4 mb-4"
              style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid #1e293b' }}
            >
              {/* Step-by-step instructions */}
              <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
                Como obter a chave de API
              </p>
              <ol className="space-y-2 mb-4">
                {provider.steps.map((step, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5"
                      style={{ background: provider.iconBg, color: provider.iconColor }}>
                      {i + 1}
                    </span>
                    {step.link ? (
                      <a href={step.link} target="_blank" rel="noopener noreferrer"
                        className="text-xs leading-relaxed hover:underline"
                        style={{ color: provider.iconColor }}>
                        {step.text} <ExternalLink size={10} className="inline" />
                      </a>
                    ) : (
                      <span className="text-xs leading-relaxed" style={{ color: '#94a3b8' }}>{step.text}</span>
                    )}
                  </li>
                ))}
              </ol>

              {/* Button to open the site */}
              <a href={provider.keyUrl} target="_blank" rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2 rounded-lg text-xs font-semibold mb-4 transition-all"
                style={{ background: provider.iconBg, border: `1px solid ${provider.iconColor}33`, color: provider.iconColor }}>
                <ExternalLink size={13} />
                {provider.keyLabel}
              </a>

              {/* Divider */}
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1 h-px" style={{ background: '#1e293b' }} />
                <span className="text-xs" style={{ color: '#334155' }}>cole a chave aqui</span>
                <div className="flex-1 h-px" style={{ background: '#1e293b' }} />
              </div>

              {/* Input */}
              <div className="relative">
                <Key size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#475569' }} />
                <input
                  type="text"
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setError('') }}
                  placeholder={provider.placeholder}
                  onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                  className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm font-mono outline-none transition-all"
                  style={{ background: '#0f172a', border: '1px solid #334155', color: '#cbd5e1' }}
                  onFocus={(e) => { e.target.style.borderColor = provider.iconColor + '88' }}
                  onBlur={(e) => { e.target.style.borderColor = '#334155' }}
                />
              </div>

              {error && <p className="text-xs mt-2" style={{ color: '#f87171' }}>{error}</p>}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action button */}
        {alreadySaved ? (
          <button
            onClick={handleSwitch}
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-all"
            style={{ background: `linear-gradient(135deg, ${provider.iconColor}, ${provider.iconColor}cc)`, color: '#0a0e17' }}
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : `Usar ${provider.name} →`}
          </button>
        ) : (
          <button
            onClick={handleSave}
            disabled={loading || !apiKey.trim()}
            className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-all"
            style={{
              background: apiKey.trim() ? `linear-gradient(135deg, ${provider.iconColor}, ${provider.iconColor}cc)` : '#1e293b',
              color: apiKey.trim() ? '#0a0e17' : '#475569',
              cursor: apiKey.trim() ? 'pointer' : 'not-allowed',
            }}
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : 'Salvar e continuar →'}
          </button>
        )}
      </div>
    </div>
  )
}
