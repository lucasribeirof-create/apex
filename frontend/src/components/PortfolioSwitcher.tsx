import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Plus, Copy, Layers, FlaskConical, Check, Lightbulb, Trash2, Upload } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import api from '@/services/api'
import { useStore, PortfolioInfo } from '@/store/useStore'

interface Props {
  onSwitch?: () => void  // callback para recarregar dados da página atual
}

export default function PortfolioSwitcher({ onSwitch }: Props) {
  const navigate = useNavigate()
  const { portfolioAtivo, portfolios, setPortfolioAtivo, setPortfolios } = useStore()
  const [open, setOpen] = useState(false)
  const [criandoSimulada, setCriandoSimulada] = useState(false)
  const [nomeSimulada, setNomeSimulada] = useState('')
  const [origemSimulada, setOrigemSimulada] = useState<'zero' | 'copia'>('copia')
  const [criandoReal, setCriandoReal] = useState(false)
  const [nomeReal, setNomeReal] = useState('Nova Carteira Real')
  const [origemReal, setOrigemReal] = useState<'ia' | 'manual'>('ia')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  async function carregarPortfolios() {
    try {
      const res = await api.get('/portfolio/listar')
      const lista: PortfolioInfo[] = res.data
      setPortfolios(lista)
      const ativo = lista.find(p => p.ativo) ?? lista[0] ?? null
      if (ativo) setPortfolioAtivo(ativo)
    } catch (e) {
      // silencioso
    }
  }

  useEffect(() => {
    carregarPortfolios()
  }, [])

  // Fecha ao clicar fora
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setCriandoSimulada(false)
        setCriandoReal(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  async function ativar(id: number) {
    setLoading(true)
    try {
      const res = await api.post(`/portfolio/ativar/${id}`)
      const selecionado = portfolios.find(p => p.id === id)
      if (selecionado) setPortfolioAtivo(selecionado)
      await carregarPortfolios()
      setOpen(false)
      onSwitch?.()
      setMsg(`✓ ${res.data.mensagem}`)
      setTimeout(() => setMsg(null), 3000)
    } catch (e) {
      setMsg('Erro ao trocar portfolio.')
      setTimeout(() => setMsg(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  async function criarSimulada() {
    if (!nomeSimulada.trim()) return
    // Origem 'zero' → wizard de perfil dedicado
    if (origemSimulada === 'zero') {
      setOpen(false)
      setCriandoSimulada(false)
      navigate('/setup-simulada')
      return
    }
    setLoading(true)
    try {
      await api.post('/portfolio/criar-simulada', {
        nome: nomeSimulada.trim(),
        origem: origemSimulada,
      })
      await carregarPortfolios()
      setCriandoSimulada(false)
      setNomeSimulada('')
      setOpen(false)
      onSwitch?.()
      setMsg('Carteira simulada criada! Agora ativa.')
      setTimeout(() => setMsg(null), 4000)
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? 'Erro ao criar simulada.')
      setTimeout(() => setMsg(null), 4000)
    } finally {
      setLoading(false)
    }
  }

  async function criarReal() {
    if (!nomeReal.trim()) return
    setLoading(true)
    try {
      await api.post('/portfolio/criar-real', { nome: nomeReal.trim() })
      await carregarPortfolios()
      setCriandoReal(false)
      setNomeReal('Nova Carteira Real')
      setOpen(false)
      if (origemReal === 'ia') {
        navigate('/sugestoes-alocacao')
      } else {
        navigate('/positions')
      }
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? 'Erro ao criar carteira real.')
      setTimeout(() => setMsg(null), 4000)
    } finally {
      setLoading(false)
    }
  }

  async function deletarPortfolio(id: number, nome: string) {
    if (!confirm(`Deletar "${nome}"? Todas as posições e histórico serão removidos permanentemente.`)) return
    setLoading(true)
    try {
      await api.delete(`/portfolio/${id}`)
      await carregarPortfolios()
      onSwitch?.()
      setMsg('Carteira deletada.')
      setTimeout(() => setMsg(null), 4000)
    } catch (e: any) {
      setMsg(e?.response?.data?.detail ?? 'Erro ao deletar carteira.')
      setTimeout(() => setMsg(null), 4000)
    } finally {
      setLoading(false)
    }
  }

  const isSimulada = portfolioAtivo?.tipo === 'simulada'
  const isTese = portfolioAtivo?.tipo === 'tese'
  const badgeColor = isTese ? '#AA00FF' : isSimulada ? '#FF9800' : '#00E676'
  const badgeBg = isTese ? 'rgba(170,0,255,0.10)' : isSimulada ? 'rgba(255,152,0,0.12)' : 'rgba(0,230,118,0.10)'
  const badgeBorder = isTese ? 'rgba(170,0,255,0.28)' : isSimulada ? 'rgba(255,152,0,0.3)' : 'rgba(0,230,118,0.25)'

  return (
    <div ref={ref} className="relative px-4 pb-2">
      {/* Badge ativo */}
      <button
        onClick={() => { setOpen(o => !o); setCriandoSimulada(false) }}
        className="w-full flex items-center justify-between px-3 py-2 rounded-lg transition-all text-left"
        style={{ background: badgeBg, border: `1px solid ${badgeBorder}` }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {isSimulada
            ? <FlaskConical size={13} style={{ color: badgeColor, flexShrink: 0 }} />
            : <Layers size={13} style={{ color: badgeColor, flexShrink: 0 }} />
          }
          <div className="min-w-0">
            <p className="text-xs font-mono truncate" style={{ color: badgeColor }}>
              {portfolioAtivo?.nome ?? 'Carteira'}
            </p>
            <p className="text-[10px]" style={{ color: '#475569' }}>
              {isTese ? 'TESE' : isSimulada ? 'SIMULADA' : 'REAL'}
            </p>
          </div>
        </div>
        <ChevronDown
          size={13}
          style={{ color: '#475569', transform: open ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s', flexShrink: 0 }}
        />
      </button>

      {/* Mensagem flash */}
      {msg && (
        <p className="text-[10px] font-mono mt-1 px-1" style={{ color: '#00E676' }}>{msg}</p>
      )}

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute left-4 right-4 z-50 rounded-xl overflow-hidden shadow-2xl"
            style={{ background: '#0f172a', border: '1px solid #1e293b', top: 'calc(100% + 4px)' }}
          >
            {/* Lista de portfolios */}
            {portfolios.map(p => {
              const cor = p.tipo === 'tese' ? '#AA00FF' : p.tipo === 'simulada' ? '#FF9800' : '#00E676'
              const isAtivo = p.id === portfolioAtivo?.id
              const Icon = p.tipo === 'tese' ? Lightbulb : p.tipo === 'simulada' ? FlaskConical : Layers
              return (
                <button
                  key={p.id}
                  onClick={() => !isAtivo && ativar(p.id)}
                  disabled={isAtivo || loading}
                  className="group w-full flex items-center justify-between px-3 py-2.5 transition-all"
                  style={{
                    background: isAtivo ? 'rgba(255,255,255,0.04)' : 'transparent',
                    cursor: isAtivo ? 'default' : 'pointer',
                  }}
                  onMouseEnter={e => { if (!isAtivo) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.04)' }}
                  onMouseLeave={e => { if (!isAtivo) (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
                >
                  <div className="flex items-center gap-2">
                    <Icon size={12} style={{ color: cor }} />
                    <div className="text-left">
                      <p className="text-xs font-medium" style={{ color: '#e2e8f0' }}>{p.nome}</p>
                      <p className="text-[10px] font-mono" style={{ color: '#475569' }}>{p.tipo.toUpperCase()}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {isAtivo && <Check size={12} style={{ color: cor }} />}
                    {portfolios.length > 1 && (
                      <button
                        onClick={e => { e.stopPropagation(); deletarPortfolio(p.id, p.nome) }}
                        className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ color: '#475569' }}
                        title="Deletar carteira"
                        onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                        onMouseLeave={e => (e.currentTarget.style.color = '#475569')}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                </button>
              )
            })}

            {/* Divider */}
            <div style={{ borderTop: '1px solid #1e293b' }} />

            {/* Criar carteiras */}
            {!criandoSimulada && !criandoReal ? (
              <>
                <button
                  onClick={() => { setCriandoReal(true); setNomeReal('Nova Carteira Real') }}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-xs transition-all"
                  style={{ color: '#64748b' }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#00E676')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
                >
                  <Plus size={12} />
                  Nova carteira real
                </button>
                <button
                  onClick={() => { setCriandoSimulada(true); setNomeSimulada('Carteira Simulada APEX') }}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-xs transition-all"
                  style={{ color: '#64748b' }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#FF9800')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
                >
                  <Plus size={12} />
                  Nova carteira simulada
                </button>
                <button
                  onClick={() => { setOpen(false); navigate('/import') }}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-xs transition-all"
                  style={{ color: '#64748b', borderTop: '1px solid #1e293b' }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#42A5F5')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}
                >
                  <Upload size={12} />
                  Importar
                </button>
              </>
            ) : criandoReal ? (
              <div className="p-3 space-y-2">
                <p className="text-[10px] font-mono uppercase" style={{ color: '#64748b' }}>Nova Carteira Real</p>
                <input
                  value={nomeReal}
                  onChange={e => setNomeReal(e.target.value)}
                  placeholder="Nome da carteira"
                  className="w-full px-2 py-1.5 rounded-lg text-xs outline-none"
                  style={{ background: '#0a0e17', border: '1px solid #334155', color: '#e2e8f0' }}
                  autoFocus
                />
                {/* Como quer começar */}
                <p className="text-[10px]" style={{ color: '#475569' }}>Como quer começar?</p>
                <div className="flex gap-2">
                  {(['ia', 'manual'] as const).map(o => (
                    <button
                      key={o}
                      onClick={() => setOrigemReal(o)}
                      className="flex-1 py-1 rounded text-[10px] font-mono transition-all"
                      style={{
                        background: origemReal === o ? 'rgba(0,230,118,0.12)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${origemReal === o ? 'rgba(0,230,118,0.4)' : '#1e293b'}`,
                        color: origemReal === o ? '#00E676' : '#64748b',
                      }}
                    >
                      {o === 'ia' ? '✦ IA sugere' : '✎ Manual'}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCriandoReal(false)}
                    className="flex-1 py-1.5 rounded text-xs transition-all"
                    style={{ color: '#475569', background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={criarReal}
                    disabled={loading || !nomeReal.trim()}
                    className="flex-1 py-1.5 rounded text-xs font-medium transition-all"
                    style={{ background: 'rgba(0,230,118,0.12)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}
                  >
                    {loading ? '...' : 'Criar'}
                  </button>
                </div>
              </div>
            ) : criandoSimulada ? (
              <div className="p-3 space-y-2">
                <p className="text-[10px] font-mono uppercase" style={{ color: '#64748b' }}>Nova Carteira Simulada</p>
                <input
                  value={nomeSimulada}
                  onChange={e => setNomeSimulada(e.target.value)}
                  placeholder="Nome da carteira"
                  className="w-full px-2 py-1.5 rounded-lg text-xs outline-none"
                  style={{ background: '#0a0e17', border: '1px solid #334155', color: '#e2e8f0' }}
                  autoFocus
                />
                {/* Origem */}
                <div className="flex gap-2">
                  {(['copia', 'zero'] as const).map(o => (
                    <button
                      key={o}
                      onClick={() => setOrigemSimulada(o)}
                      className="flex-1 flex items-center justify-center gap-1 py-1 rounded text-[10px] font-mono transition-all"
                      style={{
                        background: origemSimulada === o ? 'rgba(255,152,0,0.12)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${origemSimulada === o ? 'rgba(255,152,0,0.4)' : '#1e293b'}`,
                        color: origemSimulada === o ? '#FF9800' : '#64748b',
                      }}
                    >
                      {o === 'copia' ? <><Copy size={10} /> Copiar atual</> : <>Do zero</>}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCriandoSimulada(false)}
                    className="flex-1 py-1.5 rounded text-xs transition-all"
                    style={{ color: '#475569', background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={criarSimulada}
                    disabled={loading || !nomeSimulada.trim()}
                    className="flex-1 py-1.5 rounded text-xs font-medium transition-all"
                    style={{ background: 'rgba(255,152,0,0.15)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.3)' }}
                  >
                    {loading ? '...' : 'Criar'}
                  </button>
                </div>
              </div>
            ) : null}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
