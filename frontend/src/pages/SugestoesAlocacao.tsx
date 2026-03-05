/**
 * SugestoesAlocacao — Tela de aprovação de portfólio sugerido pela IA.
 * Fluxo em 2 fases:
 *   Fase 1 (estrategia) — Análise rápida + 3 cenários → investidor escolhe
 *   Fase 2 (carteira)   — Motores + CEO geram carteira alinhada ao cenário
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BrainCircuit, Check, X, ChevronRight, Loader2,
  FlaskConical, AlertTriangle, RefreshCw, TrendingUp,
  ShieldAlert, Sparkles, ArrowRightLeft, ChevronDown, ArrowLeft,
  PartyPopper, CheckCircle2, BarChart3, MinusCircle, PlusCircle,
  ArrowRight, LogOut, FileDown, Clock, RotateCcw,
} from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import ThinkingSteps from '@/components/ThinkingSteps'

interface Sugestao {
  modulo: string
  ticker: string
  nome: string
  tipo: string
  quantidade: number
  preco_atual: number
  valor_total: number
  justificativa: string
  score?: number
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dados_extras?: Record<string, any>
}

interface PosicaoAtual {
  ticker: string
  nome: string
  tipo: string
  modulo: string
  quantidade: number
  preco_medio: number
  preco_atual: number
  valor_atual: number
  pl_percentual: number
  stop_loss: number | null
  data_entrada: string | null
}

interface GestorAnalise {
  analise: string
  alertas: string[]
  ajustes_realizados: string[]
  score_portfolio: number
  usou_ia: boolean
  regime: string
}

// Componente de badges com dados operacionais extras por módulo
function DadosExtrasCard({ modulo, extras }: { modulo: string; extras?: Record<string, unknown> }) {
  if (!extras) return null

  const badge = (label: string, value: string, cor = '#64748b') => (
    <span key={label} className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded"
      style={{ background: `${cor}18`, color: cor, border: `1px solid ${cor}28` }}>
      <span style={{ color: '#475569' }}>{label}</span>
      <span style={{ color: cor, fontWeight: 600 }}>{value}</span>
    </span>
  )

  const badges: React.ReactNode[] = []

  if (modulo === 'momentum') {
    if (extras.alvo)  badges.push(badge('ALVO',  `R$${Number(extras.alvo).toFixed(2)}`,  '#00E676'))
    if (extras.stop)  badges.push(badge('STOP',  `R$${Number(extras.stop).toFixed(2)}`,  '#FF5252'))
    if (extras.rr)    badges.push(badge('R/R',   `${extras.rr}:1`,                        '#FF9800'))
    if (extras.rsi)   badges.push(badge('RSI',   `${Number(extras.rsi).toFixed(0)}`,      '#64FFDA'))
    if (extras.dist_mm200 !== undefined) badges.push(badge('MM200', `${Number(extras.dist_mm200) >= 0 ? '+' : ''}${Number(extras.dist_mm200).toFixed(1)}%`, '#94a3b8'))
  }

  if (modulo === 'wheel') {
    if (extras.opcao_sugerida) badges.push(badge('OPÇÃO',  String(extras.opcao_sugerida),                   '#AA00FF'))
    if (extras.strike)         badges.push(badge('STRIKE', `R$${Number(extras.strike).toFixed(2)}`,          '#AA00FF'))
    if (extras.vencimento)     badges.push(badge('VENC',   String(extras.vencimento),                       '#94a3b8'))
    if (extras.premio)         badges.push(badge('PRÊMIO', `R$${Number(extras.premio).toFixed(2)}`,          '#00E676'))
    if (extras.retorno_anual)  badges.push(badge('RET/ANO',`${extras.retorno_anual}%`,                      '#FF9800'))
    if (extras.multiplo_cdi)   badges.push(badge('CDI',    `${extras.multiplo_cdi}×`,                       '#64FFDA'))
    if (extras.timing_veredito) {
      const cor = String(extras.timing_veredito) === 'FAVORÁVEL' ? '#00E676' : String(extras.timing_veredito) === 'NEUTRO' ? '#FF9800' : '#FF5252'
      badges.push(badge('TIMING', String(extras.timing_veredito), cor))
    }
  }

  if (modulo === 'fiis') {
    if (extras.dy_estimado)          badges.push(badge('DY/ANO', `${extras.dy_estimado}%`,          '#00BFA5'))
    if (extras.p_vp)                 badges.push(badge('P/VP',  `${extras.p_vp}`,                   Number(extras.p_vp) >= 1 ? '#FF9800' : '#00E676'))
    if (extras.segmento)             badges.push(badge('SEG',   String(extras.segmento).replace('_',' '), '#64FFDA'))
    if (extras.renda_mensal_estimada) badges.push(badge('RENDA/MÊS', `R$${Number(extras.renda_mensal_estimada).toFixed(0)}`, '#F06292'))
  }

  if (modulo === 'dividendos') {
    if (extras.dy_12m)               badges.push(badge('DY/ANO',    `${extras.dy_12m}%`,            '#F06292'))
    if (extras.payout_ratio)         badges.push(badge('PAYOUT',    `${extras.payout_ratio}%`,      '#94a3b8'))
    if (extras.setor)                badges.push(badge('SETOR',     String(extras.setor),            '#64FFDA'))
    if (extras.renda_mensal_estimada) badges.push(badge('RENDA/MÊS', `R$${Number(extras.renda_mensal_estimada).toFixed(0)}`, '#F06292'))
  }

  if (modulo === 'alpha') {
    if (extras.pl)                    badges.push(badge('P/L',      `${extras.pl}×`,                 Number(extras.pl) < 12 ? '#00E676' : '#FF9800'))
    if (extras.p_vp)                  badges.push(badge('P/VP',     `${extras.p_vp}`,                Number(extras.p_vp) < 1 ? '#00E676' : '#94a3b8'))
    if (extras.crescimento_receita !== undefined) badges.push(badge('RECEITA', `${Number(extras.crescimento_receita) >= 0 ? '+' : ''}${extras.crescimento_receita}%`, '#64FFDA'))
    if (extras.upside_estimado_pct)   badges.push(badge('UPSIDE',   `+${extras.upside_estimado_pct}%`, '#00E676'))
  }

  if (modulo === 'renda_fixa') {
    if (extras.taxa_referencia_aa)    badges.push(badge('TAXA/ANO', `${extras.taxa_referencia_aa}%`, '#4FC3F7'))
    if (extras.rendimento_mensal_est) badges.push(badge('RENDA/MÊS', `R$${Number(extras.rendimento_mensal_est).toFixed(0)}`, '#4FC3F7'))
    if (extras.liquidez)              badges.push(badge('LIQ', String(extras.liquidez).split(' ')[0], '#94a3b8'))
  }

  if (modulo === 'etfs') {
    if (extras.peso_alocacao_pct) badges.push(badge('PESO',    `${extras.peso_alocacao_pct}%`, '#64FFDA'))
    if (extras.taxa_adm_aa)       badges.push(badge('TAXA ADM', `${extras.taxa_adm_aa}%/ano`,  '#94a3b8'))
  }

  if (badges.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {badges}
    </div>
  )
}

interface SugestaoState {
  item: Sugestao
  aprovada: boolean
}

const MODULO_COLORS: Record<string, string> = {
  etfs: '#64FFDA', fiis: '#00BFA5', renda_fixa: '#4FC3F7',
  momentum: '#FF9800', wheel: '#AA00FF', alpha: '#00E676',
  dividendos: '#F06292', teses: '#FFD740', caixa: '#90A4AE',
}
const MODULO_LABELS: Record<string, string> = {
  etfs: 'ETFs', fiis: 'FIIs', renda_fixa: 'Renda Fixa',
  momentum: 'Momentum · Trade Técnico', wheel: 'Wheel · Opções', alpha: 'Alpha · Valor com Stop',
  dividendos: 'Dividendos', teses: 'Teses · Convicção DCA', caixa: 'Caixa',
}

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtK(v: number) {
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace('.0', '')}k`
  return v.toFixed(0)
}

// Cores e labels por ação do CEO
const ACAO_CONFIG: Record<string, { label: string; color: string; bg: string; icon: typeof Check }> = {
  MANTER:  { label: 'MANTER',  color: '#64748b', bg: 'rgba(100,116,139,0.10)', icon: Check },
  ENTRAR:  { label: 'NOVO',    color: '#2979FF', bg: 'rgba(41,121,255,0.10)',  icon: PlusCircle },
  AUMENTAR:{ label: 'AUMENTAR',color: '#FFD740', bg: 'rgba(255,215,64,0.10)',  icon: TrendingUp },
  REDUZIR: { label: 'REDUZIR', color: '#FF9800', bg: 'rgba(255,152,0,0.10)',   icon: MinusCircle },
  SAIR:    { label: 'SAÍDA',   color: '#FF5252', bg: 'rgba(255,82,82,0.10)',   icon: LogOut },
}

export default function SugestoesAlocacao() {
  const navigate = useNavigate()
  const location = useLocation()
  const {
    portfolioAtivo,
    setPortfolios, setPortfolioAtivo,
    ultimoPlanoEstrategico, setUltimoPlanoEstrategico,
    cenarioEscolhido: cenarioStore, setCenarioEscolhido: setCenarioStore,
    ultimoRebalanceamento, setUltimoRebalanceamento, clearUltimoRebalanceamento,
  } = useStore()

  // Recebe portfolio_id e modo via state de navegação
  const { portfolioId, modo = 'inicial', forceRefresh: navForceRefresh = false } = (location.state as {
    portfolioId: number
    modo?: 'inicial' | 'rebalanceamento'
    forceRefresh?: boolean
  }) ?? {}

  // Flag para saber se restauramos do cache
  const [restauradoDoCache, setRestauradoDoCache] = useState(false)
  const [cacheTimestamp, setCacheTimestamp] = useState<number | null>(null)

  // ── Fase do fluxo ──────────────────────────────────────────────────────────
  // Rebalanceamento pula direto pra carteira (não precisa escolher cenário)
  type Etapa = 'estrategia' | 'carteira' | 'sucesso'
  const [etapa, setEtapa] = useState<Etapa>(modo === 'rebalanceamento' ? 'carteira' : 'estrategia')

  // ── Estado compartilhado ───────────────────────────────────────────────────
  const [carregando, setCarregando] = useState(true)
  const [erroCarregamento, setErroCarregamento] = useState<string | null>(null)
  const [gestorAnalise, setGestorAnalise] = useState<GestorAnalise | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [planoEstrategico, setPlanoEstrategico] = useState<any>(ultimoPlanoEstrategico ?? null)
  const [planoExpandido, setPlanoExpandido] = useState(true)
  const [cenarioSelecionado, setCenarioSelecionado] = useState<string | null>(cenarioStore)
  const [segundosCarregando, setSegundosCarregando] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Estado Fase 2 (carteira) ───────────────────────────────────────────────
  const [sugestoes, setSugestoes] = useState<SugestaoState[]>([])
  const [capitalTotal, setCapitalTotal] = useState(0)
  const [capitalRestante, setCapitalRestante] = useState(0)
  const [observacao, setObservacao] = useState('')
  const [aplicando, setAplicando] = useState(false)
  const [erroAplicar, setErroAplicar] = useState<string | null>(null)
  const [posicoesAtuais, setPosicoesAtuais] = useState<PosicaoAtual[]>([])
  const [comparacaoExpandida, setComparacaoExpandida] = useState(false)

  // ── Trava anti-swap (React StrictMode chama useEffect 2x) ─────────────────
  const jaChamouRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  // ── Fase 1: Análise estratégica (rápida, ~30-60s) ─────────────────────────
  const carregarEstrategia = useCallback(async (forceRefresh = false) => {
    setCarregando(true)
    setErroCarregamento(null)
    try {
      const res = await api.post('/portfolio/analisar-estrategia', {
        portfolio_id: portfolioId,
        force_refresh: forceRefresh,
      })
      const data = res.data
      setGestorAnalise(data.gestor_analise ?? null)
      if (data.plano_estrategico) {
        setPlanoEstrategico(data.plano_estrategico)
        setUltimoPlanoEstrategico(data.plano_estrategico)
      }
    } catch (e: any) {
      setErroCarregamento(e?.response?.data?.detail ?? 'Erro ao gerar análise estratégica. Tente novamente.')
    }
    setCarregando(false)
  }, [portfolioId, setUltimoPlanoEstrategico])

  // ── Fase 2: Carteira completa (com motores, ~2-4 min) ─────────────────────
  const carregarCarteira = useCallback(async (forceRefresh = false) => {
    setCarregando(true)
    setErroCarregamento(null)
    try {
      const res = await api.post('/portfolio/sugerir-portfolio', {
        portfolio_id: portfolioId,
        force_refresh: forceRefresh,
        modo: modo,
        cenario_escolhido: cenarioSelecionado || 'Recomendado',
      })
      const data = res.data
      setCapitalTotal(data.capital_total)
      setCapitalRestante(data.capital_restante)
      setObservacao(data.observacao)
      // Atualiza gestor_analise da Fase 2 (mais completo, com ajustes_realizados)
      setGestorAnalise(data.gestor_analise ?? null)
      if (data.plano_estrategico) {
        setPlanoEstrategico(data.plano_estrategico)
        setUltimoPlanoEstrategico(data.plano_estrategico)
      }
      const sugestoesState = data.sugestoes.map((s: Sugestao) => ({ item: s, aprovada: true }))
      setSugestoes(sugestoesState)
      if (data.posicoes_atuais) setPosicoesAtuais(data.posicoes_atuais)

      // ── Persistir snapshot no Zustand para não perder ao navegar ──
      if (modo === 'rebalanceamento' && portfolioId) {
        setUltimoRebalanceamento({
          sugestoes: sugestoesState.map((s: SugestaoState) => ({ ...s.item, aprovada: s.aprovada })),
          posicoesAtuais: data.posicoes_atuais || [],
          capitalTotal: data.capital_total,
          capitalRestante: data.capital_restante,
          observacao: data.observacao || '',
          gestorAnalise: data.gestor_analise ?? null,
          planoEstrategico: data.plano_estrategico ?? null,
          cenarioSelecionado: cenarioSelecionado || 'Recomendado',
          portfolioId,
          modo,
          etapa: 'carteira',
          timestamp: Date.now(),
        })
      }
      setRestauradoDoCache(false)
    } catch (e: any) {
      setErroCarregamento(e?.response?.data?.detail ?? 'Erro ao gerar sugestões. Tente novamente.')
    }
    setCarregando(false)
  }, [portfolioId, modo, cenarioSelecionado, setUltimoPlanoEstrategico, setUltimoRebalanceamento])

  // ── Boot: carrega fase adequada com trava anti-swap ───────────────────────
  useEffect(() => {
    if (!portfolioId) {
      navigate('/briefing')
      return
    }
    // Trava: se o StrictMode já chamou esta função, ignora a segunda chamada
    if (jaChamouRef.current) return
    jaChamouRef.current = true

    if (etapa === 'estrategia') {
      carregarEstrategia()
    } else {
      // ── Tentar restaurar do cache (se não é forceRefresh) ──
      if (
        modo === 'rebalanceamento' &&
        !navForceRefresh &&
        ultimoRebalanceamento &&
        ultimoRebalanceamento.portfolioId === portfolioId
      ) {
        // Restaurar estado do snapshot
        const cache = ultimoRebalanceamento
        setSugestoes(cache.sugestoes.map(s => ({ item: s, aprovada: s.aprovada })))
        setPosicoesAtuais(cache.posicoesAtuais as PosicaoAtual[])
        setCapitalTotal(cache.capitalTotal)
        setCapitalRestante(cache.capitalRestante)
        setObservacao(cache.observacao)
        setGestorAnalise(cache.gestorAnalise)
        if (cache.planoEstrategico) {
          setPlanoEstrategico(cache.planoEstrategico)
        }
        setCenarioSelecionado(cache.cenarioSelecionado)
        setRestauradoDoCache(true)
        setCacheTimestamp(cache.timestamp)
        setCarregando(false)
      } else {
        carregarCarteira(modo === 'rebalanceamento')
      }
    }

    return () => {
      // Cleanup: cancela controller se desmontou
      if (abortRef.current) abortRef.current.abort()
    }
  }, [portfolioId])

  // Cronômetro — ativo apenas enquanto carregando
  useEffect(() => {
    if (carregando) {
      setSegundosCarregando(0)
      timerRef.current = setInterval(() => setSegundosCarregando(s => s + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [carregando])

  // ── Ação: investidor escolheu cenário e clicou "Gerar Carteira" ───────────
  function gerarCarteiraComCenario() {
    if (!cenarioSelecionado) return
    setCenarioStore(cenarioSelecionado)
    setEtapa('carteira')
    jaChamouRef.current = false               // reset trava pra nova fase
    carregarCarteira()
  }

  // ── Ação: voltar da Fase 2 para Fase 1 ────────────────────────────────────
  function voltarParaEstrategia() {
    setEtapa('estrategia')
    setSugestoes([])
    jaChamouRef.current = true // Não precisa recarregar — já temos os dados
    setCarregando(false)
  }

  function toggleAprovar(idx: number) {
    setSugestoes(prev => prev.map((s, i) => i === idx ? { ...s, aprovada: !s.aprovada } : s))
  }

  function aprovarTodas() {
    setSugestoes(prev => prev.map(s => ({ ...s, aprovada: true })))
  }
  function rejeitarTodas() {
    setSugestoes(prev => prev.map(s => ({ ...s, aprovada: false })))
  }

  // Capital em caixa = capital restante + capital das sugestões rejeitadas
  const capitalRejeitado = sugestoes
    .filter(s => !s.aprovada)
    .reduce((acc, s) => acc + s.item.valor_total, 0)
  const capitalCaixa = capitalRestante + capitalRejeitado
  const totalAprovado = sugestoes
    .filter(s => s.aprovada)
    .reduce((acc, s) => acc + s.item.valor_total, 0)
  const qtdAprovadas = sugestoes.filter(s => s.aprovada).length

  // ── Contadores por ação (rebalanceamento) ───────────────────────────────
  const isRebal = modo === 'rebalanceamento'
  const acaoCounts = isRebal ? sugestoes.reduce<Record<string, number>>((acc, s) => {
    const a = (s.item.dados_extras?.acao_ceo as string) || 'MANTER'
    acc[a] = (acc[a] || 0) + 1
    return acc
  }, {}) : {}

  // Saídas extraídas de ajustes_realizados
  const saidasExtraidas: { ticker: string; motivo: string }[] = []
  if (isRebal && gestorAnalise?.ajustes_realizados) {
    for (const ajuste of gestorAnalise.ajustes_realizados) {
      const match = ajuste.match(/SA[IÍ]DA\s+([A-Z0-9]+)\s*[—–-]\s*(.+)/i)
      if (match) {
        const ticker = match[1].trim()
        if (!sugestoes.some(s => s.item.ticker === ticker)) {
          saidasExtraidas.push({ ticker, motivo: match[2].trim() })
        }
      }
    }
  }

  // Mapa de posições atuais por ticker
  const posAtualMap = posicoesAtuais.reduce<Record<string, PosicaoAtual>>((m, p) => {
    m[p.ticker] = p
    return m
  }, {})

  // Agrupar por módulo
  const porModulo = sugestoes.reduce<Record<string, SugestaoState[]>>((acc, s) => {
    const m = s.item.modulo
    if (!acc[m]) acc[m] = []
    acc[m].push(s)
    return acc
  }, {})

  const isCarteiraReal = portfolioAtivo?.tipo === 'real'

  // ── Dados para tabela de comparação ativo por ativo (rebalanceamento) ───────
  interface ComparacaoRow {
    ticker: string
    nome: string
    modulo: string
    acao: string
    antesQtd: number
    antesValor: number
    depoisQtd: number
    depoisValor: number
    deltaReais: number
    deltaPct: number
  }

  const comparacaoRows = useMemo<ComparacaoRow[]>(() => {
    if (!isRebal || (posicoesAtuais.length === 0 && sugestoes.length === 0)) return []

    const tickerSet = new Set<string>()
    const rows: ComparacaoRow[] = []

    // Sugestões propostas
    for (const s of sugestoes) {
      const t = s.item.ticker
      if (t === 'TESES') continue
      tickerSet.add(t)
      const pa = posAtualMap[t]
      const acao = (s.item.dados_extras?.acao_ceo as string) || (pa ? 'MANTER' : 'ENTRAR')
      rows.push({
        ticker: t,
        nome: s.item.nome,
        modulo: s.item.modulo,
        acao,
        antesQtd: pa?.quantidade ?? 0,
        antesValor: pa?.valor_atual ?? 0,
        depoisQtd: s.item.quantidade,
        depoisValor: s.item.valor_total,
        deltaReais: s.item.valor_total - (pa?.valor_atual ?? 0),
        deltaPct: pa?.valor_atual ? ((s.item.valor_total - pa.valor_atual) / pa.valor_atual) * 100 : 100,
      })
    }

    // Saídas (não estão nas sugestões)
    for (const saida of saidasExtraidas) {
      if (tickerSet.has(saida.ticker)) continue
      tickerSet.add(saida.ticker)
      const pa = posAtualMap[saida.ticker]
      rows.push({
        ticker: saida.ticker,
        nome: pa?.nome ?? saida.ticker,
        modulo: pa?.modulo ?? '',
        acao: 'SAIR',
        antesQtd: pa?.quantidade ?? 0,
        antesValor: pa?.valor_atual ?? 0,
        depoisQtd: 0,
        depoisValor: 0,
        deltaReais: -(pa?.valor_atual ?? 0),
        deltaPct: -100,
      })
    }

    // Posições atuais não mencionadas (se houver)
    for (const p of posicoesAtuais) {
      if (tickerSet.has(p.ticker)) continue
      tickerSet.add(p.ticker)
      rows.push({
        ticker: p.ticker,
        nome: p.nome,
        modulo: p.modulo,
        acao: 'MANTER',
        antesQtd: p.quantidade,
        antesValor: p.valor_atual,
        depoisQtd: p.quantidade,
        depoisValor: p.valor_atual,
        deltaReais: 0,
        deltaPct: 0,
      })
    }

    // Ordenar: SAIR → REDUZIR → AUMENTAR → ENTRAR → MANTER
    const ordemAcao: Record<string, number> = { SAIR: 0, REDUZIR: 1, AUMENTAR: 2, ENTRAR: 3, MANTER: 4 }
    rows.sort((a, b) => (ordemAcao[a.acao] ?? 5) - (ordemAcao[b.acao] ?? 5))
    return rows
  }, [isRebal, sugestoes, posicoesAtuais, posAtualMap, saidasExtraidas])

  const comparacaoTotalAntes = comparacaoRows.reduce((s, r) => s + r.antesValor, 0)
  const comparacaoTotalDepois = comparacaoRows.reduce((s, r) => s + r.depoisValor, 0)

  // ── Função: rebalancear novamente (limpa cache e força atualização) ───
  function rebalancearNovamente() {
    clearUltimoRebalanceamento()
    setRestauradoDoCache(false)
    jaChamouRef.current = false
    carregarCarteira(true)
  }

  // ── Preparar payload de rebalanceamento (compartilhado entre real e simulada) ──
  function _buildRebalPayload() {
    const ativos = sugestoes.filter(s => s.aprovada && s.item.ticker !== 'TESES').map(s => ({
      ticker: s.item.ticker,
      nome: s.item.nome,
      tipo: s.item.tipo,
      modulo: s.item.modulo,
      quantidade: s.item.quantidade,
      preco_atual: s.item.preco_atual,
      valor_total: s.item.valor_total,
      acao: (s.item.dados_extras?.acao_ceo as string) || 'MANTER',
      justificativa: s.item.justificativa || null,
      stop_loss: s.item.dados_extras?.stop ?? s.item.dados_extras?.stop_loss ?? null,
      alvo_1: s.item.dados_extras?.alvo ?? s.item.dados_extras?.alvo_1 ?? null,
      alvo_2: s.item.dados_extras?.alvo_2 ?? null,
      apex_score: s.item.score ? Math.round(s.item.score * 100) : null,
      // Dados antes (para PDF)
      quantidade_atual: posAtualMap[s.item.ticker]?.quantidade ?? null,
      valor_atual_antes: posAtualMap[s.item.ticker]?.valor_atual ?? null,
    }))

    const saidas: { ticker: string; motivo: string; quantidade?: number; valor_atual?: number }[] = []
    if (gestorAnalise?.ajustes_realizados) {
      for (const ajuste of gestorAnalise.ajustes_realizados) {
        const match = ajuste.match(/SA[IÍ]DA\s+([A-Z0-9]+)\s*[—–-]\s*(.+)/i)
        if (match) {
          const ticker = match[1].trim()
          if (!ativos.some(a => a.ticker === ticker)) {
            const pa = posAtualMap[ticker]
            saidas.push({
              ticker,
              motivo: match[2].trim(),
              quantidade: pa?.quantidade,
              valor_atual: pa?.valor_atual,
            })
          }
        }
      }
    }
    return { ativos, saidas }
  }

  // ── Baixar PDF do plano (carteira real) ──
  async function baixarPlanoPDF() {
    const { ativos, saidas } = _buildRebalPayload()
    setAplicando(true)
    setErroAplicar(null)
    try {
      const res = await api.post('/portfolio/gerar-plano-rebalanceamento', {
        portfolio_id: portfolioId,
        nome_carteira: portfolioAtivo?.nome || 'Carteira',
        ativos,
        saidas,
        capital_caixa: Math.round(capitalCaixa * 100) / 100,
      }, { responseType: 'blob' })

      // Trigger download
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `APEX_Plano_Rebalanceamento.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      setCenarioStore(null)
      setEtapa('sucesso')
      clearUltimoRebalanceamento()
    } catch (e: any) {
      setErroAplicar(e?.response?.data?.detail ?? 'Erro ao gerar PDF do plano.')
    }
    setAplicando(false)
  }

  async function confirmar() {
    if (modo === 'rebalanceamento') {
      // ── Carteira REAL → apenas gerar PDF, não alterar posições ──
      if (isCarteiraReal) {
        await baixarPlanoPDF()
        return
      }

      // ── Carteira SIMULADA → aplicar automaticamente ──
      const { ativos, saidas } = _buildRebalPayload()

      if (ativos.length === 0 && saidas.length === 0 && capitalCaixa <= 0) {
        navigate('/briefing')
        return
      }

      setAplicando(true)
      setErroAplicar(null)
      try {
        await api.post('/portfolio/aplicar-rebalanceamento', {
          portfolio_id: portfolioId,
          ativos,
          saidas,
          capital_caixa: Math.round(capitalCaixa * 100) / 100,
        })
        const rl = await api.get('/portfolio/listar')
        setPortfolios(rl.data)
        const ativo = rl.data.find((p: any) => p.ativo) ?? rl.data[0]
        if (ativo) setPortfolioAtivo(ativo)
        setCenarioStore(null)
        setEtapa('sucesso')
        clearUltimoRebalanceamento()
      } catch (e: any) {
        setErroAplicar(e?.response?.data?.detail ?? 'Erro ao aplicar rebalanceamento.')
        setAplicando(false)
      }
      return
    }

    // ── Modo inicial: usa endpoint original ──
    const aprovadas = sugestoes.filter(s => s.aprovada).map(s => ({
      ticker: s.item.ticker,
      nome: s.item.nome,
      tipo: s.item.tipo,
      modulo: s.item.modulo,
      quantidade: s.item.quantidade,
      preco_atual: s.item.preco_atual,
      justificativa: s.item.justificativa || null,
      stop_loss: s.item.dados_extras?.stop ?? s.item.dados_extras?.stop_loss ?? null,
      alvo_1: s.item.dados_extras?.alvo ?? s.item.dados_extras?.alvo_1 ?? null,
      alvo_2: s.item.dados_extras?.alvo_2 ?? null,
      apex_score: s.item.score ? Math.round(s.item.score * 100) : null,
    }))

    if (aprovadas.length === 0 && capitalCaixa <= 0) {
      navigate('/briefing')
      return
    }

    setAplicando(true)
    setErroAplicar(null)
    try {
      await api.post('/portfolio/aplicar-sugestoes', {
        portfolio_id: portfolioId,
        sugestoes: aprovadas,
        capital_caixa: Math.round(capitalCaixa * 100) / 100,
      })
      // Atualiza store com carteiras atualizadas
      const rl = await api.get('/portfolio/listar')
      setPortfolios(rl.data)
      const ativo = rl.data.find((p: any) => p.ativo) ?? rl.data[0]
      if (ativo) setPortfolioAtivo(ativo)
      setCenarioStore(null)  // limpa cenário após aplicar
      setEtapa('sucesso')    // mostra tela de celebração
      clearUltimoRebalanceamento()
    } catch (e: any) {
      setErroAplicar(e?.response?.data?.detail ?? 'Erro ao aplicar sugestões.')
      setAplicando(false)
    }
  }

  // ─── Tela de carregamento ─────────────────────────────────────────────────
  if (carregando) {
    const isEstrategia = etapa === 'estrategia'
    const isInicial = modo === 'inicial'
    const STEPS = isEstrategia ? [
      'Coletando dados macro: VIX, Treasury, Selic, dólar...',
      'Determinando regime de mercado (BULL / MISTO / BEAR)...',
      'Analisando perfil do investidor e objetivos...',
      'Gestor gerando diagnóstico estratégico...',
      'Construindo 3 cenários de investimento...',
    ] : isInicial ? [
      'Motor ETFs: selecionando fundos por perfil...',
      'Motor FIIs: analisando DY real e P/VP...',
      'Motor Renda Fixa: calibrando Selic vs IPCA Focus...',
      'Motor Momentum: filtrando ativos em tendência...',
      'Motor Dividendos: verificando consistência de proventos...',
      'Motor Wheel: escolhendo opções com melhor prêmio...',
      'Eliminando duplicatas entre módulos...',
      `Gestor Geral montando carteira ${cenarioSelecionado || 'Recomendado'}...`,
    ] : [
      'Lendo regime de mercado e dados macro...',
      'Coletando candidatos dos motores especializados...',
      'Verificando perfil de risco e estratégia...',
      'Identificando e resolvendo duplicatas entre módulos...',
      'Calculando alocações e balanço de caixa...',
      'Gestor Geral assinando o portfólio final...',
    ]
    const mins = Math.floor(segundosCarregando / 60)
    const secs = segundosCarregando % 60
    const tempoStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
    const tempoAviso = isEstrategia ? '30 segundos a 1 minuto' : '2 a 4 minutos'
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 p-8" style={{ background: '#0a0e17' }}>
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
          style={{ background: 'rgba(255,152,0,0.1)', border: '1px solid rgba(255,152,0,0.25)' }}>
          <BrainCircuit size={28} style={{ color: '#FF9800' }} className="animate-pulse" />
        </div>
        <div className="text-center">
          <p className="text-lg font-semibold mb-1" style={{ color: '#f1f5f9' }}>
            {isEstrategia
              ? 'Gestor analisando estratégia...'
              : 'Gestor montando sua carteira...'}
          </p>
          <p className="text-sm font-mono" style={{ color: '#475569' }}>
            Analisando há <span style={{ color: '#FF9800' }}>{tempoStr}</span>
          </p>
        </div>
        <div className="rounded-xl px-5 py-3 max-w-sm text-center"
          style={{ background: 'rgba(255,152,0,0.04)', border: '1px solid rgba(255,152,0,0.15)' }}>
          <p className="text-xs leading-relaxed" style={{ color: '#64748b' }}>
            {isEstrategia
              ? <>A <strong style={{ color: '#94a3b8' }}>análise estratégica</strong> avalia o cenário macro e seu perfil. Costuma levar <strong style={{ color: '#FF9800' }}>{tempoAviso}</strong>.</>
              : <>A <strong style={{ color: '#94a3b8' }}>montagem da carteira</strong> roda 7 motores especializados + IA. Costuma levar <strong style={{ color: '#FF9800' }}>{tempoAviso}</strong> — é normal.</>
            }
          </p>
        </div>
        <ThinkingSteps steps={STEPS} intervalMs={isEstrategia ? 3000 : 3500} color="#FF9800" />
      </div>
    )
  }

  // ─── Tela de erro ─────────────────────────────────────────────────────────
  if (erroCarregamento) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 p-8" style={{ background: '#0a0e17' }}>
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
          style={{ background: 'rgba(255,82,82,0.1)', border: '1px solid rgba(255,82,82,0.25)' }}>
          <AlertTriangle size={28} style={{ color: '#FF5252' }} />
        </div>
        <div className="text-center max-w-sm">
          <p className="text-lg font-semibold mb-2" style={{ color: '#f1f5f9' }}>
            {etapa === 'estrategia' ? 'Erro na análise estratégica' : 'Erro ao gerar sugestões'}
          </p>
          <p className="text-sm mb-6" style={{ color: '#64748b' }}>{erroCarregamento}</p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => {
                jaChamouRef.current = false
                if (etapa === 'estrategia') carregarEstrategia()
                else carregarCarteira()
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium"
              style={{ background: 'rgba(255,152,0,0.12)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.3)' }}
            >
              <RefreshCw size={14} /> Tentar novamente
            </button>
            <button
              onClick={() => navigate('/positions')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm"
              style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid #1e293b' }}
            >
              Ir para posições
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ─── Tela principal ───────────────────────────────────────────────────────
  return (
    <div className="min-h-screen p-6 md:p-10 max-w-3xl mx-auto" style={{ background: '#0a0e17' }}>

      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(255,152,0,0.12)', border: '1px solid rgba(255,152,0,0.3)' }}>
            <FlaskConical size={18} style={{ color: '#FF9800' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>
              {modo === 'rebalanceamento'
                ? 'Sugestão de Rebalanceamento'
                : etapa === 'estrategia'
                  ? 'Análise Estratégica'
                  : 'Carteira Sugerida'
              }
            </h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>
              {modo === 'rebalanceamento'
                ? 'Aprovação de ajustes sugeridos pela IA'
                : etapa === 'estrategia'
                  ? 'Fase 1 — Escolha seu cenário de investimento'
                  : `Fase 2 — Carteira ${cenarioSelecionado || 'Recomendado'}`
              }
            </p>
          </div>
          <button
            onClick={() => {
              jaChamouRef.current = false
              if (etapa === 'estrategia') carregarEstrategia(true)
              else carregarCarteira(true)
            }}
            title="Recalcular com dados atuais"
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
            style={{ background: 'rgba(255,152,0,0.08)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.2)' }}
          >
            <RefreshCw size={12} /> Atualizar
          </button>
        </div>

        {/* Indicador de etapas */}
        {modo !== 'rebalanceamento' && (
          <div className="flex items-center gap-2 mt-3">
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{ background: 'rgba(255,152,0,0.2)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.4)' }}>1</div>
              <span className="text-[10px] font-mono" style={{ color: etapa === 'estrategia' ? '#FF9800' : '#475569' }}>Estratégia</span>
            </div>
            <div className="w-8 h-px" style={{ background: '#1e293b' }} />
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{
                  background: etapa === 'carteira' ? 'rgba(0,230,118,0.2)' : 'rgba(255,255,255,0.03)',
                  color: etapa === 'carteira' ? '#00E676' : '#475569',
                  border: `1px solid ${etapa === 'carteira' ? 'rgba(0,230,118,0.4)' : '#1e293b'}`,
                }}>2</div>
              <span className="text-[10px] font-mono" style={{ color: etapa === 'carteira' ? '#00E676' : '#475569' }}>Carteira</span>
            </div>
          </div>
        )}
      </motion.div>

      {/* Gestor Geral — card CEO */}
      {gestorAnalise && (
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
          className="rounded-2xl mb-6 overflow-hidden"
          style={{ background: 'rgba(255,152,0,0.04)', border: '1px solid rgba(255,152,0,0.2)' }}
        >
          {/* Header CEO */}
          <div className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid rgba(255,152,0,0.15)', background: 'rgba(255,152,0,0.06)' }}>
            <div className="flex items-center gap-2">
              <BrainCircuit size={15} style={{ color: '#FF9800' }} />
              <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#FF9800' }}>
                Gestor Geral
              </span>
              {gestorAnalise.usou_ia
                ? <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                    style={{ background: 'rgba(170,0,255,0.12)', color: '#AA00FF', border: '1px solid rgba(170,0,255,0.25)' }}>IA</span>
                : <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                    style={{ background: 'rgba(100,116,139,0.12)', color: '#64748b', border: '1px solid rgba(100,116,139,0.2)' }}>Algorítmico</span>
              }
              <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                style={{ background: 'rgba(100,116,139,0.08)', color: '#64748b', border: '1px solid #1e293b' }}>
                {gestorAnalise.regime}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono" style={{ color: '#475569' }}>SCORE</span>
              <span className="text-sm font-bold font-mono" style={{
                color: gestorAnalise.score_portfolio >= 75 ? '#00E676'
                  : gestorAnalise.score_portfolio >= 50 ? '#FF9800'
                  : '#FF5252'
              }}>
                {gestorAnalise.score_portfolio}/100
              </span>
            </div>
          </div>

          {gestorAnalise.analise && (
            <div className="px-5 pt-4 pb-3">
              <div className="text-sm leading-relaxed" style={{ color: '#94a3b8' }}>
                {gestorAnalise.analise.split('\n\n').map((para, i) => {
                  if (!para.trim()) return null
                  // Dentro de cada parágrafo, processa quebras simples e negrito
                  const lines = para.split('\n').filter(l => l.trim())
                  return (
                    <p key={i} className={i > 0 ? 'mt-4' : ''}>
                      {lines.map((line, li) => {
                        const parts = line.split(/\*\*(.*?)\*\*/g)
                        return (
                          <span key={li}>
                            {li > 0 && <br />}
                            {parts.map((part, j) =>
                              j % 2 === 1
                                ? <strong key={j} style={{ color: '#e2e8f0' }}>{part}</strong>
                                : part
                            )}
                          </span>
                        )
                      })}
                    </p>
                  )
                })}
              </div>
            </div>
          )}

          {gestorAnalise.alertas.length > 0 && (
            <div className="px-4 py-2 space-y-1">
              {gestorAnalise.alertas.map((alerta, i) => (
                <div key={i} className="flex items-start gap-2">
                  <ShieldAlert size={11} style={{ color: '#FF5252', flexShrink: 0, marginTop: 2 }} />
                  <span className="text-[11px] leading-snug" style={{ color: '#ef4444' }}>{alerta}</span>
                </div>
              ))}
            </div>
          )}

          {gestorAnalise.ajustes_realizados?.length > 0 && (
            <div className="px-4 pb-3 pt-1 space-y-1"
              style={{ borderTop: '1px solid rgba(255,152,0,0.1)', marginTop: 4 }}>
              <p className="text-[10px] font-mono uppercase tracking-wider mb-1.5" style={{ color: '#475569' }}>Ajustes realizados</p>
              {gestorAnalise.ajustes_realizados.map((ajuste, i) => (
                <div key={i} className="flex items-start gap-2">
                  <ArrowRightLeft size={10} style={{ color: '#64748b', flexShrink: 0, marginTop: 2 }} />
                  <span className="text-[11px] leading-snug" style={{ color: '#64748b' }}>{ajuste}</span>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* Plano Estratégico */}
      {planoEstrategico && (
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}
          className="rounded-2xl mb-6 overflow-hidden"
          style={{ background: 'rgba(0,230,118,0.03)', border: '1px solid rgba(0,230,118,0.15)' }}
        >
          <button
            onClick={() => setPlanoExpandido(v => !v)}
            className="w-full px-4 py-3 flex items-center gap-2 text-left"
            style={{ borderBottom: planoExpandido ? '1px solid rgba(0,230,118,0.1)' : 'none', background: 'rgba(0,230,118,0.05)' }}
          >
            <Sparkles size={14} style={{ color: '#00E676' }} />
            <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#00E676' }}>
              Análise Estratégica
            </span>
            {planoEstrategico.fase_atual && (
              <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                style={{ background: 'rgba(0,230,118,0.1)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                {planoEstrategico.fase_atual}
              </span>
            )}
            <ChevronRight
              size={14}
              className="ml-auto transition-transform"
              style={{ color: '#475569', transform: planoExpandido ? 'rotate(90deg)' : 'rotate(0deg)' }}
            />
          </button>

          {planoExpandido && (
            <>
              {planoEstrategico.diagnostico && (
                <div className="px-5 pt-4 pb-3">
                  <div className="text-sm leading-relaxed" style={{ color: '#f1f5f9' }}>
                    {planoEstrategico.diagnostico.split('\n\n').map((para: string, i: number) => {
                      if (!para.trim()) return null
                      const lines = para.split('\n').filter((l: string) => l.trim())
                      return (
                        <p key={i} className={i > 0 ? 'mt-4' : ''}>
                          {lines.map((line: string, li: number) => {
                            const parts = line.split(/\*\*(.*?)\*\*/g)
                            return (
                              <span key={li}>
                                {li > 0 && <br />}
                                {parts.map((part: string, j: number) =>
                                  j % 2 === 1
                                    ? <strong key={j} style={{ color: '#00E676' }}>{part}</strong>
                                    : part
                                )}
                              </span>
                            )
                          })}
                        </p>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Cenários — CLICÁVEIS na Fase 1 */}
              {planoEstrategico.cenarios?.length > 0 && (
                <div className="px-5 pb-4">
                  <p className="text-[10px] font-mono uppercase tracking-wider mb-3" style={{ color: '#475569' }}>
                    {etapa === 'estrategia' ? 'Escolha um cenário' : 'Cenários'}
                  </p>
                  <div className="space-y-3">
                    {planoEstrategico.cenarios.map((c: any, i: number) => {
                      const colorMap: Record<number, string> = { 0: '#3B82F6', 1: '#00E676', 2: '#FF9800' }
                      const accent = colorMap[i] || '#64748b'
                      const isRec = c.nome?.toLowerCase().includes('recomendado')
                      const isSelected = cenarioSelecionado === c.nome
                      const isClickable = etapa === 'estrategia'
                      return (
                        <div
                          key={i}
                          onClick={isClickable ? () => setCenarioSelecionado(c.nome) : undefined}
                          className={`rounded-xl relative transition-all ${isClickable ? 'cursor-pointer hover:scale-[1.005]' : ''}`}
                          style={{
                            background: isSelected ? `${accent}12` : isRec ? `${accent}06` : 'rgba(30,41,59,0.25)',
                            border: isSelected
                              ? `2px solid ${accent}`
                              : isRec ? `2px solid ${accent}30` : '1px solid #1e293b',
                            boxShadow: isSelected ? `0 0 24px ${accent}20` : 'none',
                          }}
                        >
                          {/* Header row — nome + badges + retorno */}
                          <div className="flex items-center gap-3 px-4 pt-3 pb-2">
                            {/* Radio indicator */}
                            <div className="w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                              style={{
                                borderColor: isSelected ? accent : '#334155',
                                background: isSelected ? accent : 'transparent',
                              }}>
                              {isSelected && <Check size={11} style={{ color: '#0a0e17' }} />}
                            </div>

                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-bold" style={{ color: isSelected ? accent : '#f1f5f9' }}>{c.nome}</span>
                                {isRec && !isSelected && (
                                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase"
                                    style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}>
                                    Recomendado
                                  </span>
                                )}
                                {isSelected && (
                                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase"
                                    style={{ background: `${accent}20`, color: accent, border: `1px solid ${accent}40` }}>
                                    Selecionado
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Retorno destaque */}
                            <div className="text-right flex-shrink-0">
                              <div className="text-xs font-bold font-mono" style={{ color: accent }}>{c.rentabilidade_esperada}</div>
                              <div className="text-[9px] font-mono" style={{ color: '#475569' }}>retorno esperado</div>
                            </div>
                          </div>

                          {/* Description */}
                          <div className="px-4 pb-2.5 pl-12">
                            <p className="text-[11px] leading-relaxed" style={{ color: '#94a3b8' }}>{c.descricao}</p>
                          </div>

                          {/* Stats row */}
                          <div className="flex items-center gap-4 px-4 pb-3 pl-12 flex-wrap">
                            {c.alocacao_resumo && (
                              <div className="flex items-center gap-1.5 text-[10px]">
                                <span style={{ color: '#475569' }}>Alocação:</span>
                                <span className="font-mono" style={{ color: '#cbd5e1' }}>{c.alocacao_resumo}</span>
                              </div>
                            )}
                            <div className="flex items-center gap-1.5 text-[10px]">
                              <span style={{ color: '#475569' }}>Tempo:</span>
                              <span className="font-mono" style={{ color: '#cbd5e1' }}>{c.tempo_meta}</span>
                            </div>
                          </div>

                          {/* Risk footer */}
                          {c.risco_principal && (
                            <div className="px-4 pb-3 pl-12">
                              <div className="flex items-start gap-1.5 text-[10px]">
                                <AlertTriangle size={10} style={{ color: '#f59e0b', flexShrink: 0, marginTop: 1 }} />
                                <span style={{ color: '#f59e0b' }}>{c.risco_principal}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Riscos */}
              {planoEstrategico.riscos_e_tradeoffs?.length > 0 && (
                <div className="px-5 pb-3">
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldAlert size={11} style={{ color: '#ef4444' }} />
                    <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#ef4444' }}>Riscos</span>
                  </div>
                  {planoEstrategico.riscos_e_tradeoffs.map((r: string, i: number) => (
                    <p key={i} className="text-[11px] leading-snug pl-4 mb-1" style={{ color: '#fca5a5' }}>{r}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </motion.div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* ═══ FASE 1: Botão "Gerar Carteira com este Cenário" ════════════ */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {etapa === 'estrategia' && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <button
            onClick={gerarCarteiraComCenario}
            disabled={!cenarioSelecionado}
            className="w-full py-4 rounded-2xl text-sm font-semibold transition-all flex items-center justify-center gap-3"
            style={{
              background: cenarioSelecionado ? 'rgba(255,152,0,0.15)' : 'rgba(255,255,255,0.02)',
              border: `1px solid ${cenarioSelecionado ? 'rgba(255,152,0,0.4)' : '#1e293b'}`,
              color: cenarioSelecionado ? '#FF9800' : '#475569',
              cursor: cenarioSelecionado ? 'pointer' : 'not-allowed',
            }}
          >
            {cenarioSelecionado
              ? <><BrainCircuit size={18} /> Gerar Carteira — Cenário {cenarioSelecionado} <ChevronRight size={16} /></>
              : <><BrainCircuit size={18} /> Selecione um cenário acima para continuar</>
            }
          </button>

          <button
            onClick={() => navigate('/briefing')}
            className="w-full mt-3 py-3 rounded-xl text-sm transition-all"
            style={{ color: '#64748b', border: '1px solid #1e293b', background: 'rgba(255,255,255,0.02)' }}
          >
            Decidir depois
          </button>
        </motion.div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* ═══ FASE 2: Carteira Sugerida ══════════════════════════════════ */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {etapa === 'carteira' && sugestoes.length > 0 && (
        <>
          {/* Banner de resultado restaurado do cache */}
          {restauradoDoCache && cacheTimestamp && (
            <motion.div
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
              className="rounded-xl px-4 py-3 mb-4 flex items-center justify-between"
              style={{ background: 'rgba(41,121,255,0.06)', border: '1px solid rgba(41,121,255,0.2)' }}
            >
              <div className="flex items-center gap-2">
                <Clock size={14} style={{ color: '#2979FF' }} />
                <span className="text-xs" style={{ color: '#94a3b8' }}>
                  Resultado salvo em{' '}
                  <span style={{ color: '#2979FF', fontWeight: 600 }}>
                    {new Date(cacheTimestamp).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </span>
                </span>
              </div>
              <button
                onClick={rebalancearNovamente}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all"
                style={{ background: 'rgba(255,152,0,0.10)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.25)' }}
              >
                <RotateCcw size={12} /> Rebalancear novamente
              </button>
            </motion.div>
          )}

          {/* Divisor */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
            className="flex items-center gap-3 my-8"
          >
            <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, transparent, #1e293b, #334155)' }} />
            <div className="flex items-center gap-2 px-4 py-2 rounded-full"
              style={{ background: 'rgba(0,191,165,0.06)', border: '1px solid rgba(0,191,165,0.2)' }}>
              <BrainCircuit size={14} style={{ color: '#00BFA5' }} />
              <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#00BFA5' }}>
                Carteira Sugerida
              </span>
              {cenarioSelecionado && (
                <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-bold"
                  style={{ background: 'rgba(255,152,0,0.12)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.25)' }}>
                  {cenarioSelecionado}
                </span>
              )}
            </div>
            <div className="flex-1 h-px" style={{ background: 'linear-gradient(to left, transparent, #1e293b, #334155)' }} />
          </motion.div>

          {/* Resumo financeiro */}
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}
            className="grid grid-cols-3 gap-3 mb-6"
          >
            {[
              { label: 'Capital Total', value: `R$ ${fmt(capitalTotal)}`, color: '#94a3b8' },
              { label: 'Total Aprovado', value: `R$ ${fmt(totalAprovado)}`, color: '#00E676' },
              { label: 'Vai p/ Caixa', value: `R$ ${fmt(capitalCaixa)}`, color: capitalCaixa > 0 ? '#FF9800' : '#475569' },
            ].map(c => (
              <div key={c.label} className="rounded-xl p-3 text-center"
                style={{ background: '#0d1117', border: '1px solid #1e293b' }}>
                <p className="text-[10px] font-mono uppercase tracking-wider mb-1" style={{ color: '#475569' }}>{c.label}</p>
                <p className="text-sm font-bold font-mono" style={{ color: c.color }}>{c.value}</p>
              </div>
            ))}
          </motion.div>

          {/* ── Painel de resumo de mudanças (só no rebalanceamento) ────────── */}
          {isRebal && sugestoes.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 }}
              className="rounded-2xl mb-6 overflow-hidden"
              style={{ background: '#0d1117', border: '1px solid #1e293b' }}
            >
              <div className="px-4 py-3 flex items-center gap-2"
                style={{ borderBottom: '1px solid #1e293b', background: 'rgba(255,152,0,0.04)' }}>
                <ArrowRightLeft size={14} style={{ color: '#FF9800' }} />
                <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#FF9800' }}>
                  Resumo das Mudanças
                </span>
              </div>

              {/* Contadores por ação */}
              <div className="px-4 py-3 flex flex-wrap gap-2" style={{ borderBottom: '1px solid #1e293b' }}>
                {Object.entries(acaoCounts).map(([acao, count]) => {
                  const cfg = ACAO_CONFIG[acao] || ACAO_CONFIG.MANTER
                  return (
                    <span key={acao} className="inline-flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg"
                      style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}25` }}>
                      <cfg.icon size={11} />
                      {count} {cfg.label}
                    </span>
                  )
                })}
                {saidasExtraidas.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg"
                    style={{ background: 'rgba(255,82,82,0.10)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.25)' }}>
                    <LogOut size={11} />
                    {saidasExtraidas.length} SAÍDA
                  </span>
                )}
              </div>

              {/* Alocação antes → depois por módulo */}
              {posicoesAtuais.length > 0 && (() => {
                const totalAtual = posicoesAtuais.reduce((s, p) => s + p.valor_atual, 0)
                const totalProposto = sugestoes.reduce((s, x) => s + x.item.valor_total, 0)
                // Agrupar módulos
                const modulosSet = new Set<string>()
                posicoesAtuais.forEach(p => modulosSet.add(p.modulo))
                sugestoes.forEach(s => modulosSet.add(s.item.modulo))
                const rows = Array.from(modulosSet).filter(m => m !== 'caixa').map(m => {
                  const antes = posicoesAtuais.filter(p => p.modulo === m).reduce((s, p) => s + p.valor_atual, 0)
                  const depois = sugestoes.filter(s => s.item.modulo === m).reduce((s, x) => s + x.item.valor_total, 0)
                  const antesPct = totalAtual > 0 ? (antes / totalAtual) * 100 : 0
                  const depoisPct = totalProposto > 0 ? (depois / totalProposto) * 100 : 0
                  return { modulo: m, antes, depois, antesPct, depoisPct, mudou: Math.abs(antesPct - depoisPct) > 0.5 }
                }).filter(r => r.antes > 0 || r.depois > 0)

                return (
                  <div className="px-4 py-3">
                    <p className="text-[10px] font-mono uppercase tracking-wider mb-2" style={{ color: '#475569' }}>
                      Alocação antes → depois
                    </p>
                    <div className="space-y-1.5">
                      {rows.map(r => {
                        const cor = MODULO_COLORS[r.modulo] ?? '#64748b'
                        return (
                          <div key={r.modulo} className="flex items-center gap-2 text-xs">
                            <span className="w-[120px] truncate" style={{ color: cor }}>
                              {MODULO_LABELS[r.modulo] || r.modulo}
                            </span>
                            <span className="font-mono w-[50px] text-right" style={{ color: '#64748b' }}>
                              {r.antesPct.toFixed(1)}%
                            </span>
                            <ArrowRight size={10} style={{ color: '#475569' }} />
                            <span className="font-mono w-[50px]" style={{ color: r.mudou ? '#f1f5f9' : '#64748b', fontWeight: r.mudou ? 600 : 400 }}>
                              {r.depoisPct.toFixed(1)}%
                            </span>
                            {r.mudou && (
                              <span className="font-mono text-[10px]" style={{ color: r.depoisPct > r.antesPct ? '#00E676' : '#FF9800' }}>
                                {r.depoisPct > r.antesPct ? '+' : ''}{(r.depoisPct - r.antesPct).toFixed(1)}pp
                              </span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })()}
            </motion.div>
          )}

          {/* ── Tabela de comparação ativo por ativo (rebalanceamento) ───── */}
          {isRebal && comparacaoRows.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }}
              className="rounded-2xl mb-6 overflow-hidden"
              style={{ background: '#0d1117', border: '1px solid #1e293b' }}
            >
              <button
                onClick={() => setComparacaoExpandida(prev => !prev)}
                className="w-full px-4 py-3 flex items-center justify-between"
                style={{ borderBottom: comparacaoExpandida ? '1px solid #1e293b' : 'none', background: 'rgba(0,191,165,0.04)' }}
              >
                <div className="flex items-center gap-2">
                  <BarChart3 size={14} style={{ color: '#00BFA5' }} />
                  <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#00BFA5' }}>
                    Comparação Ativo por Ativo
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(0,191,165,0.10)', color: '#00BFA5', border: '1px solid rgba(0,191,165,0.20)' }}>
                    {comparacaoRows.length} ativos
                  </span>
                </div>
                <ChevronDown
                  size={14}
                  style={{ color: '#475569', transform: comparacaoExpandida ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }}
                />
              </button>

              <AnimatePresence>
                {comparacaoExpandida && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    style={{ overflow: 'hidden' }}
                  >
                    {/* Cabeçalho da tabela */}
                    <div className="grid px-4 py-2 text-[10px] font-mono uppercase tracking-wider"
                      style={{
                        gridTemplateColumns: '1fr 70px 100px 100px 90px',
                        borderBottom: '1px solid #1e293b',
                        color: '#475569',
                      }}
                    >
                      <span>Ativo</span>
                      <span className="text-center">Ação</span>
                      <span className="text-right">Antes</span>
                      <span className="text-right">Depois</span>
                      <span className="text-right">Δ Valor</span>
                    </div>

                    {/* Linhas */}
                    {comparacaoRows.map((row, idx) => {
                      const acaoCfg = ACAO_CONFIG[row.acao] || ACAO_CONFIG.MANTER
                      const cor = MODULO_COLORS[row.modulo] ?? '#64748b'
                      const isLast = idx === comparacaoRows.length - 1
                      return (
                        <div
                          key={row.ticker}
                          className="grid px-4 py-2.5 items-center text-xs"
                          style={{
                            gridTemplateColumns: '1fr 70px 100px 100px 90px',
                            borderBottom: isLast ? 'none' : '1px solid #1e293b10',
                            background: row.acao === 'SAIR' ? 'rgba(255,82,82,0.03)' : row.acao === 'ENTRAR' ? 'rgba(41,121,255,0.03)' : 'transparent',
                          }}
                        >
                          {/* Ticker + nome */}
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: cor }} />
                            <div className="min-w-0">
                              <span className="font-mono font-bold text-xs" style={{ color: '#f1f5f9' }}>{row.ticker}</span>
                              <p className="text-[10px] truncate" style={{ color: '#475569' }}>{row.nome}</p>
                            </div>
                          </div>

                          {/* Badge de ação */}
                          <div className="flex justify-center">
                            <span className="inline-flex items-center gap-1 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                              style={{ background: acaoCfg.bg, color: acaoCfg.color, border: `1px solid ${acaoCfg.color}30` }}>
                              <acaoCfg.icon size={8} />
                              {acaoCfg.label}
                            </span>
                          </div>

                          {/* Antes */}
                          <div className="text-right font-mono">
                            {row.antesValor > 0 ? (
                              <>
                                <span style={{ color: '#94a3b8' }}>R$ {fmtK(row.antesValor)}</span>
                                <p className="text-[10px]" style={{ color: '#475569' }}>{row.antesQtd % 1 === 0 ? row.antesQtd.toFixed(0) : row.antesQtd.toFixed(2)} un</p>
                              </>
                            ) : (
                              <span style={{ color: '#334155' }}>—</span>
                            )}
                          </div>

                          {/* Depois */}
                          <div className="text-right font-mono">
                            {row.depoisValor > 0 ? (
                              <>
                                <span style={{ color: row.acao === 'ENTRAR' ? '#2979FF' : '#f1f5f9', fontWeight: row.acao !== 'MANTER' ? 600 : 400 }}>
                                  R$ {fmtK(row.depoisValor)}
                                </span>
                                <p className="text-[10px]" style={{ color: '#475569' }}>{row.depoisQtd % 1 === 0 ? row.depoisQtd.toFixed(0) : row.depoisQtd.toFixed(2)} un</p>
                              </>
                            ) : (
                              <span style={{ color: '#334155' }}>—</span>
                            )}
                          </div>

                          {/* Delta */}
                          <div className="text-right font-mono">
                            {Math.abs(row.deltaReais) > 0.5 ? (
                              <>
                                <span style={{
                                  color: row.deltaReais > 0 ? '#00E676' : '#FF5252',
                                  fontWeight: 600,
                                }}>
                                  {row.deltaReais > 0 ? '+' : ''}{fmtK(row.deltaReais)}
                                </span>
                                {row.acao !== 'ENTRAR' && row.acao !== 'SAIR' && (
                                  <p className="text-[10px]" style={{ color: row.deltaReais > 0 ? '#00E676' : '#FF9800', opacity: 0.7 }}>
                                    {row.deltaPct > 0 ? '+' : ''}{row.deltaPct.toFixed(1)}%
                                  </p>
                                )}
                              </>
                            ) : (
                              <span style={{ color: '#334155' }}>—</span>
                            )}
                          </div>
                        </div>
                      )
                    })}

                    {/* Rodapé — totais */}
                    <div className="grid px-4 py-3 items-center text-xs font-mono"
                      style={{
                        gridTemplateColumns: '1fr 70px 100px 100px 90px',
                        borderTop: '1px solid #1e293b',
                        background: 'rgba(255,255,255,0.02)',
                      }}
                    >
                      <span className="font-bold" style={{ color: '#94a3b8' }}>TOTAL</span>
                      <span />
                      <span className="text-right" style={{ color: '#94a3b8' }}>R$ {fmtK(comparacaoTotalAntes)}</span>
                      <span className="text-right font-bold" style={{ color: '#f1f5f9' }}>R$ {fmtK(comparacaoTotalDepois)}</span>
                      <span className="text-right font-bold" style={{
                        color: comparacaoTotalDepois - comparacaoTotalAntes >= 0 ? '#00E676' : '#FF5252',
                      }}>
                        {comparacaoTotalDepois - comparacaoTotalAntes >= 0 ? '+' : ''}
                        {fmtK(comparacaoTotalDepois - comparacaoTotalAntes)}
                      </span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Ações rápidas */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
            className="flex items-center justify-between mb-5"
          >
            <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#475569' }}>
              {qtdAprovadas} de {sugestoes.length} aprovadas
            </p>
            <div className="flex gap-2">
              <button onClick={aprovarTodas}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}>
                Aprovar todas
              </button>
              <button onClick={rejeitarTodas}
                className="text-xs px-3 py-1.5 rounded-lg"
                style={{ background: 'rgba(255,82,82,0.06)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.15)' }}>
                Rejeitar todas
              </button>
            </div>
          </motion.div>

          {/* Sugestões por módulo */}
          <div className="space-y-4 mb-8">
            {Object.entries(porModulo).map(([modulo, items], mi) => {
              const cor = MODULO_COLORS[modulo] ?? '#64748b'
              const label = MODULO_LABELS[modulo] ?? modulo
              return (
                <motion.div
                  key={modulo}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + mi * 0.06 }}
                  className="rounded-2xl overflow-hidden"
                  style={{ background: '#0d1117', border: '1px solid #1e293b' }}
                >
                  <div className="px-4 py-3 flex items-center justify-between"
                    style={{ borderBottom: '1px solid #1e293b', background: `${cor}08` }}>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: cor }} />
                      <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: cor }}>{label}</span>
                    </div>
                    <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
                      {items.length} ativo{items.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {items.map((s, idx) => {
                    const globalIdx = sugestoes.findIndex(x => x === s)
                    const aprovada = s.aprovada
                    return (
                      <div
                        key={s.item.ticker}
                        className="px-4 py-3 flex items-start gap-3 transition-all"
                        style={{
                          borderBottom: idx < items.length - 1 ? '1px solid #1e293b' : 'none',
                          background: aprovada ? 'transparent' : 'rgba(255,82,82,0.03)',
                          opacity: aprovada ? 1 : 0.5,
                        }}
                      >
                        <button
                          onClick={() => toggleAprovar(globalIdx)}
                          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 transition-all"
                          style={{
                            background: aprovada ? 'rgba(0,230,118,0.12)' : 'rgba(255,82,82,0.1)',
                            border: `1px solid ${aprovada ? 'rgba(0,230,118,0.3)' : 'rgba(255,82,82,0.25)'}`,
                          }}
                        >
                          {aprovada
                            ? <Check size={13} style={{ color: '#00E676' }} />
                            : <X size={13} style={{ color: '#FF5252' }} />
                          }
                        </button>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-bold font-mono" style={{ color: '#f1f5f9' }}>
                                  {s.item.ticker}
                                </span>
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                  style={{ background: `${cor}15`, color: cor, border: `1px solid ${cor}30` }}>
                                  {s.item.tipo}
                                </span>
                                {/* Badge de ação CEO (rebalanceamento) */}
                                {isRebal && (() => {
                                  const acao = (s.item.dados_extras?.acao_ceo as string) || 'MANTER'
                                  const acaoCfg = ACAO_CONFIG[acao] || ACAO_CONFIG.MANTER
                                  return (
                                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                                      style={{ background: acaoCfg.bg, color: acaoCfg.color, border: `1px solid ${acaoCfg.color}30` }}>
                                      <acaoCfg.icon size={9} />
                                      {acaoCfg.label}
                                    </span>
                                  )
                                })()}
                              </div>
                              <p className="text-xs mt-0.5" style={{ color: '#94a3b8' }}>{s.item.nome}</p>
                            </div>
                            <div className="text-right flex-shrink-0">
                              <p className="text-sm font-mono font-semibold" style={{ color: '#f1f5f9' }}>
                                R$ {fmt(s.item.valor_total)}
                              </p>
                              {/* Antes → Depois para AUMENTAR / REDUZIR */}
                              {isRebal && posAtualMap[s.item.ticker] && (() => {
                                const pa = posAtualMap[s.item.ticker]
                                const acao = (s.item.dados_extras?.acao_ceo as string) || ''
                                if (acao === 'AUMENTAR' || acao === 'REDUZIR') {
                                  return (
                                    <p className="text-[10px] font-mono mt-0.5 flex items-center justify-end gap-1">
                                      <span style={{ color: '#64748b' }}>R$ {fmtK(pa.valor_atual)}</span>
                                      <ArrowRight size={8} style={{ color: '#475569' }} />
                                      <span style={{ color: acao === 'AUMENTAR' ? '#00E676' : '#FF9800', fontWeight: 600 }}>
                                        R$ {fmtK(s.item.valor_total)}
                                      </span>
                                    </p>
                                  )
                                }
                                return null
                              })()}
                              <p className="text-[10px] font-mono mt-0.5" style={{ color: '#475569' }}>
                                {s.item.quantidade % 1 === 0
                                  ? `${s.item.quantidade.toFixed(0)} un × R$ ${fmt(s.item.preco_atual)}`
                                  : `R$ ${fmt(s.item.preco_atual)}`
                                }
                              </p>
                            </div>
                          </div>
                          {s.item.justificativa && (
                            <p className="text-[11px] mt-1.5 leading-relaxed" style={{ color: '#475569' }}>
                              {s.item.justificativa}
                            </p>
                          )}
                          <DadosExtrasCard modulo={s.item.modulo} extras={s.item.dados_extras} />
                        </div>
                      </div>
                    )
                  })}
                </motion.div>
              )
            })}
          </div>

          {/* ── Cards de SAÍDA (ativos a vender) ───────────────────────── */}
          {isRebal && saidasExtraidas.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
              className="rounded-2xl mb-6 overflow-hidden"
              style={{ background: '#0d1117', border: '1px solid rgba(255,82,82,0.25)' }}
            >
              <div className="px-4 py-3 flex items-center justify-between"
                style={{ borderBottom: '1px solid rgba(255,82,82,0.15)', background: 'rgba(255,82,82,0.04)' }}>
                <div className="flex items-center gap-2">
                  <LogOut size={14} style={{ color: '#FF5252' }} />
                  <span className="text-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#FF5252' }}>
                    Saídas Recomendadas
                  </span>
                </div>
                <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
                  {saidasExtraidas.length} ativo{saidasExtraidas.length !== 1 ? 's' : ''}
                </span>
              </div>
              {saidasExtraidas.map((saida, idx) => {
                const pa = posAtualMap[saida.ticker]
                return (
                  <div key={saida.ticker}
                    className="px-4 py-3 flex items-start gap-3"
                    style={{ borderBottom: idx < saidasExtraidas.length - 1 ? '1px solid #1e293b' : 'none' }}
                  >
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                      style={{ background: 'rgba(255,82,82,0.12)', border: '1px solid rgba(255,82,82,0.3)' }}>
                      <LogOut size={13} style={{ color: '#FF5252' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold font-mono" style={{ color: '#f1f5f9' }}>
                              {saida.ticker}
                            </span>
                            <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                              style={{ background: 'rgba(255,82,82,0.10)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.30)' }}>
                              <LogOut size={9} />
                              SAÍDA
                            </span>
                          </div>
                          {pa && (
                            <p className="text-[10px] font-mono mt-0.5" style={{ color: '#64748b' }}>
                              {pa.nome}
                            </p>
                          )}
                        </div>
                        {pa && (
                          <div className="text-right flex-shrink-0">
                            <p className="text-sm font-mono font-semibold" style={{ color: '#FF5252' }}>
                              R$ {fmt(pa.valor_atual)}
                            </p>
                            <p className="text-[10px] font-mono mt-0.5" style={{
                              color: pa.pl_percentual >= 0 ? '#00E676' : '#FF5252'
                            }}>
                              {pa.pl_percentual >= 0 ? '+' : ''}{pa.pl_percentual.toFixed(1)}%
                            </p>
                          </div>
                        )}
                      </div>
                      {saida.motivo && (
                        <p className="text-[11px] mt-1.5 leading-relaxed" style={{ color: '#FF5252', opacity: 0.8 }}>
                          {saida.motivo}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </motion.div>
          )}

          {/* Caixa info */}
          {capitalCaixa > 0.5 && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="rounded-xl px-4 py-3 mb-6 flex items-center gap-3 text-sm"
              style={{ background: 'rgba(255,152,0,0.06)', border: '1px solid rgba(255,152,0,0.2)' }}
            >
              <TrendingUp size={15} style={{ color: '#FF9800', flexShrink: 0 }} />
              <span style={{ color: '#94a3b8' }}>
                <span style={{ color: '#FF9800' }}>R$ {fmt(capitalCaixa)}</span> será alocado em{' '}
                <span style={{ color: '#FF9800' }}>Caixa / Liquidez</span>
              </span>
            </motion.div>
          )}

          {erroAplicar && (
            <div className="rounded-xl px-4 py-3 mb-4 text-sm"
              style={{ background: 'rgba(255,82,82,0.06)', border: '1px solid rgba(255,82,82,0.2)', color: '#FF5252' }}>
              {erroAplicar}
            </div>
          )}

          {/* Botões de ação */}
          <div className="flex gap-3">
            {modo !== 'rebalanceamento' && (
              <button
                onClick={voltarParaEstrategia}
                className="flex items-center gap-2 py-3 px-4 rounded-xl text-sm transition-all"
                style={{ color: '#64748b', border: '1px solid #1e293b', background: 'rgba(255,255,255,0.02)' }}
              >
                <ArrowLeft size={14} /> Trocar cenário
              </button>
            )}
            <button
              onClick={() => navigate('/briefing')}
              className="flex-1 py-3 rounded-xl text-sm transition-all"
              style={{ color: '#64748b', border: '1px solid #1e293b', background: 'rgba(255,255,255,0.02)' }}
            >
              Decidir depois
            </button>
            <button
              onClick={confirmar}
              disabled={aplicando}
              className="flex-[2] py-3 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2"
              style={{
                background: aplicando ? 'rgba(255,255,255,0.03)' : (isCarteiraReal && isRebal)
                  ? 'rgba(41,121,255,0.15)' : 'rgba(255,152,0,0.15)',
                border: `1px solid ${aplicando ? '#1e293b' : (isCarteiraReal && isRebal)
                  ? 'rgba(41,121,255,0.4)' : 'rgba(255,152,0,0.4)'}`,
                color: aplicando ? '#475569' : (isCarteiraReal && isRebal) ? '#2979FF' : '#FF9800',
              }}
            >
              {aplicando
                ? <><Loader2 size={15} className="animate-spin" /> {isCarteiraReal && isRebal ? 'Gerando PDF...' : 'Aplicando...'}</>
                : isCarteiraReal && isRebal
                  ? <><FileDown size={15} /> Baixar Plano de Ação (PDF)</>
                  : <><FlaskConical size={15} /> Confirmar {qtdAprovadas} posição{qtdAprovadas !== 1 ? 'ões' : ''} <ChevronRight size={15} /></>
              }
            </button>
          </div>
        </>
      )}

      {/* ─── TELA DE SUCESSO ─────────────────────────────────────────────────── */}
      {etapa === 'sucesso' && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="flex flex-col items-center justify-center text-center py-16 px-6"
        >
          {/* Animated checkmark */}
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.2 }}
            className="w-20 h-20 rounded-full flex items-center justify-center mb-6"
            style={{
              background: isCarteiraReal && isRebal ? 'rgba(41,121,255,0.12)' : 'rgba(0,230,118,0.12)',
              border: `2px solid ${isCarteiraReal && isRebal ? 'rgba(41,121,255,0.3)' : 'rgba(0,230,118,0.3)'}`,
            }}
          >
            {isCarteiraReal && isRebal
              ? <FileDown size={40} style={{ color: '#2979FF' }} />
              : <CheckCircle2 size={40} style={{ color: '#00E676' }} />
            }
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="text-2xl font-bold mb-2" style={{ color: '#f1f5f9' }}
          >
            {isCarteiraReal && isRebal
              ? 'Plano de Ação gerado!'
              : 'Carteira montada com sucesso!'
            }
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55 }}
            className="text-sm mb-8 max-w-md" style={{ color: '#94a3b8' }}
          >
            {isCarteiraReal && isRebal ? (
              <>
                O PDF foi baixado com todas as operações detalhadas.
                Execute na sua corretora e depois registre no app o que foi feito.
              </>
            ) : (
              <>
                {qtdAprovadas} posição{qtdAprovadas !== 1 ? 'ões foram criadas' : ' foi criada'} na sua carteira
                {cenarioSelecionado ? ` com o cenário ${cenarioSelecionado}` : ''}.
                O gestor já está monitorando tudo — você pode acompanhar no Dashboard.
              </>
            )}
          </motion.p>

          {/* Summary cards */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 }}
            className="grid grid-cols-3 gap-4 mb-10 w-full max-w-lg"
          >
            <div className="rounded-xl p-4 text-center" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}>
              <div className="text-xl font-bold" style={{ color: '#00E676' }}>{qtdAprovadas}</div>
              <div className="text-xs mt-1" style={{ color: '#64748b' }}>Posições</div>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}>
              <div className="text-xl font-bold" style={{ color: '#f1f5f9' }}>
                R$ {totalAprovado.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
              </div>
              <div className="text-xs mt-1" style={{ color: '#64748b' }}>Investido</div>
            </div>
            <div className="rounded-xl p-4 text-center" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}>
              <div className="text-xl font-bold" style={{ color: capitalCaixa > 0 ? '#FF9800' : '#64748b' }}>
                R$ {capitalCaixa.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}
              </div>
              <div className="text-xs mt-1" style={{ color: '#64748b' }}>Em caixa</div>
            </div>
          </motion.div>

          {/* Action buttons */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.85 }}
            className="flex gap-3 w-full max-w-lg flex-wrap"
          >
            {/* Botão de re-download PDF (só para carteira real) */}
            {isCarteiraReal && isRebal && (
              <button
                onClick={baixarPlanoPDF}
                className="flex-1 py-3.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
                style={{ background: 'rgba(41,121,255,0.12)', border: '1px solid rgba(41,121,255,0.3)', color: '#2979FF' }}
              >
                <FileDown size={16} /> Baixar PDF novamente
              </button>
            )}
            <button
              onClick={() => navigate('/positions')}
              className="flex-1 py-3.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
              style={{ background: 'rgba(0,230,118,0.12)', border: '1px solid rgba(0,230,118,0.3)', color: '#00E676' }}
            >
              <TrendingUp size={16} />
              {isCarteiraReal && isRebal ? 'Registrar Operações' : 'Ver minhas posições'}
            </button>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex-1 py-3.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b', color: '#94a3b8' }}
            >
              <BarChart3 size={16} /> Ir pro Dashboard
            </button>
          </motion.div>

          {/* Tip */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.1 }}
            className="text-xs mt-6" style={{ color: '#475569' }}
          >
            <Sparkles size={12} className="inline mr-1" style={{ color: '#FF9800' }} />
            {isCarteiraReal && isRebal
              ? 'Execute as operações na corretora e registre no app. Depois o gestor continua monitorando.'
              : 'O Briefing diário vai te atualizar toda manhã sobre o mercado e sua carteira.'
            }
          </motion.p>
        </motion.div>
      )}
    </div>
  )
}
