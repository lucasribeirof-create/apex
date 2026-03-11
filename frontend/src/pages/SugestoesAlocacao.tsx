/**
 * SugestoesAlocacao — Tela de aprovação de portfólio sugerido pela IA.
 * Acessada após criar uma carteira simulada ou ao solicitar rebalanceamento.
 */
import React, { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BrainCircuit, Check, X, ChevronRight, Loader2,
  FlaskConical, AlertTriangle, RefreshCw, TrendingUp,
  ShieldAlert, Sparkles, ArrowRightLeft, Download,
} from 'lucide-react'
import api from '@/services/api'
import { useStore } from '@/store/useStore'
import { useCostEstimates } from '@/hooks/useCostEstimates'
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
  momentum: 'Momentum', wheel: 'Wheel', alpha: 'Alpha',
  dividendos: 'Dividendos', teses: 'Teses', caixa: 'Caixa',
}

function fmt(v: number) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function SugestoesAlocacao() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setPortfolios, setPortfolioAtivo } = useStore()
  const { format: fmtCost } = useCostEstimates()
  const portfolioCost = fmtCost('sugerir_portfolio')

  // Recebe portfolio_id e modo via state de navegação
  const { portfolioId, modo = 'inicial' } = (location.state as {
    portfolioId: number
    modo?: 'inicial' | 'rebalanceamento'
  }) ?? {}

  const [carregando, setCarregando] = useState(true)
  const [erroCarregamento, setErroCarregamento] = useState<string | null>(null)
  const [sugestoes, setSugestoes] = useState<SugestaoState[]>([])
  const [capitalTotal, setCapitalTotal] = useState(0)
  const [capitalRestante, setCapitalRestante] = useState(0)
  const [observacao, setObservacao] = useState('')
  const [gestorAnalise, setGestorAnalise] = useState<GestorAnalise | null>(null)
  const [aplicando, setAplicando] = useState(false)
  const [erroAplicar, setErroAplicar] = useState<string | null>(null)

  useEffect(() => {
    if (!portfolioId) {
      navigate('/positions')
      return
    }
    // Modo rebalanceamento: sempre força dados frescos (ignora cache de 30 min)
    carregarSugestoes(modo === 'rebalanceamento')
  }, [portfolioId])

  async function carregarSugestoes(forceRefresh = false) {
    setCarregando(true)
    setErroCarregamento(null)
    try {
      const res = await api.post('/portfolio/sugerir-portfolio', {
        portfolio_id: portfolioId,
        force_refresh: forceRefresh,
        modo: modo,
      })
      const data = res.data
      setCapitalTotal(data.capital_total)
      setCapitalRestante(data.capital_restante)
      setObservacao(data.observacao)
      setGestorAnalise(data.gestor_analise ?? null)
      setSugestoes(data.sugestoes.map((s: Sugestao) => ({ item: s, aprovada: true })))
    } catch (e: any) {
      setErroCarregamento(e?.response?.data?.detail ?? 'Erro ao gerar sugestões. Tente novamente.')
    }
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

  // Agrupar por módulo
  const porModulo = sugestoes.reduce<Record<string, SugestaoState[]>>((acc, s) => {
    const m = s.item.modulo
    if (!acc[m]) acc[m] = []
    acc[m].push(s)
    return acc
  }, {})

  async function confirmar() {
    const aprovadas = sugestoes.filter(s => s.aprovada).map(s => ({
      ticker: s.item.ticker,
      nome: s.item.nome,
      tipo: s.item.tipo,
      modulo: s.item.modulo,
      quantidade: s.item.quantidade,
      preco_atual: s.item.preco_atual,
    }))

    if (aprovadas.length === 0 && capitalCaixa <= 0) {
      navigate('/positions')
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
      navigate('/positions')
    } catch (e: any) {
      setErroAplicar(e?.response?.data?.detail ?? 'Erro ao aplicar sugestões.')
      setAplicando(false)
    }
  }

  // ─── Tela de carregamento ─────────────────────────────────────────────────
  if (carregando) {
    const STEPS = [
      'Lendo regime de mercado e dados macro...',
      'Coletando candidatos dos motores especializados...',
      'Verificando perfil de risco e estratégia...',
      'Identificando e resolvendo duplicatas entre módulos...',
      'Calculando alocações e balanço de caixa...',
      'Gestor Geral assinando o portfólio final...',
    ]
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-8 p-8" style={{ background: '#0a0e17' }}>
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
          style={{ background: 'rgba(255,152,0,0.1)', border: '1px solid rgba(255,152,0,0.25)' }}>
          <BrainCircuit size={28} style={{ color: '#FF9800' }} className="animate-pulse" />
        </div>
        <div className="text-center mb-2">
          <p className="text-lg font-semibold mb-1" style={{ color: '#f1f5f9' }}>APEX analisando portfólio...</p>
        </div>
        <ThinkingSteps steps={STEPS} intervalMs={2600} color="#FF9800" />
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
          <p className="text-lg font-semibold mb-2" style={{ color: '#f1f5f9' }}>Erro ao gerar sugestões</p>
          <p className="text-sm mb-6" style={{ color: '#64748b' }}>{erroCarregamento}</p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => carregarSugestoes()}
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
              {modo === 'rebalanceamento' ? 'Sugestão de Rebalanceamento' : 'Sugestão de Portfólio'}
            </h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>
              {modo === 'rebalanceamento' ? 'Aprovação de ajustes sugeridos pela IA' : 'Revise e aprove a alocação inicial'}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {gestorAnalise && (
              <button
                title="Download como HTML"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
                style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8', border: '1px solid #1e293b' }}
                onClick={() => {
                  const dateStr = new Date().toLocaleDateString('pt-BR')
                  const ga = gestorAnalise!
                  // Build suggestions grouped by module
                  let sugHtml = ''
                  const aprovadas = sugestoes.filter(s => s.aprovada)
                  const porMod: Record<string, typeof aprovadas> = {}
                  for (const s of aprovadas) {
                    const m = s.item.modulo
                    if (!porMod[m]) porMod[m] = []
                    porMod[m].push(s)
                  }
                  for (const [mod, items] of Object.entries(porMod)) {
                    sugHtml += `<h3 style="color:#FF9800;text-transform:uppercase;font-size:13px;margin:20px 0 8px">${mod} (${items.length} ativo${items.length > 1 ? 's' : ''})</h3>`
                    for (const s of items) {
                      const just = (s.item.justificativa || '')
                        .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#f1f5f9">$1</strong>')
                        .replace(/\n/g, '<br/>')
                      sugHtml += `<div style="border-left:3px solid #1e293b;padding:8px 12px;margin-bottom:10px;background:rgba(255,255,255,0.02);border-radius:0 8px 8px 0">`
                      sugHtml += `<div style="display:flex;justify-content:space-between;align-items:center"><strong style="color:#f1f5f9;font-size:14px">${s.item.ticker}</strong><span style="color:#00E676;font-family:monospace">R$ ${s.item.valor_total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span></div>`
                      sugHtml += `<div style="color:#64748b;font-size:11px;margin:2px 0">${s.item.nome} · ${s.item.tipo} · ${s.item.quantidade} un × R$ ${s.item.preco_atual.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>`
                      if (just) sugHtml += `<div style="color:#94a3b8;font-size:12px;margin-top:6px;line-height:1.6">${just}</div>`
                      sugHtml += '</div>'
                    }
                  }
                  // CEO analysis
                  const analiseHtml = (ga.analise || '')
                    .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#f1f5f9">$1</strong>')
                    .replace(/\n{2,}/g, '</p><p style="margin:0 0 10px">')
                    .replace(/\n/g, '<br/>')
                  const alertasHtml = ga.alertas.length > 0
                    ? '<h3 style="color:#FF5252;font-size:13px;margin:16px 0 6px">Alertas</h3><ul>' + ga.alertas.map(a => `<li style="color:#ef4444;font-size:12px;margin-bottom:4px">${a}</li>`).join('') + '</ul>'
                    : ''
                  const ajustesHtml = ga.ajustes_realizados.length > 0
                    ? '<h3 style="color:#64748b;font-size:13px;margin:16px 0 6px">Ajustes Realizados</h3><ul>' + ga.ajustes_realizados.map(a => `<li style="color:#94a3b8;font-size:12px;margin-bottom:4px">${a}</li>`).join('') + '</ul>'
                    : ''
                  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rebalanceamento APEX — ${dateStr}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e17; color: #e2e8f0; max-width: 720px; margin: 0 auto; padding: 40px 24px; line-height: 1.7; font-size: 14px; }
    h1 { color: #FF9800; font-size: 22px; margin-bottom: 4px; }
    h2 { color: #FF9800; font-size: 16px; margin: 20px 0 8px; }
    h3 { color: #FF9800; font-size: 14px; margin: 16px 0 6px; }
    strong { color: #f1f5f9; }
    hr { border: none; border-top: 1px solid #1e293b; margin: 20px 0; }
    li { margin-left: 16px; }
    .badge { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 4px; font-family: monospace; }
    .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b; color: #475569; font-size: 11px; text-align: center; }
  </style>
</head>
<body>
  <h1>🧠 Sugestão de Rebalanceamento APEX</h1>
  <div style="color:#64748b;font-size:13px;margin-bottom:4px">${dateStr} · Score: <span style="color:${ga.score_portfolio >= 75 ? '#00E676' : ga.score_portfolio >= 50 ? '#FF9800' : '#FF5252'};font-weight:bold">${ga.score_portfolio}/100</span> · Regime: ${ga.regime} · ${ga.usou_ia ? '<span class="badge" style="background:rgba(170,0,255,0.12);color:#AA00FF">IA</span>' : '<span class="badge" style="background:rgba(100,116,139,0.12);color:#64748b">Algorítmico</span>'}</div>
  <div style="display:flex;gap:12px;margin:16px 0">
    <div style="flex:1;background:#0d1117;border:1px solid #1e293b;border-radius:8px;padding:10px;text-align:center"><div style="color:#475569;font-size:10px;text-transform:uppercase;font-family:monospace">Capital Total</div><div style="color:#94a3b8;font-weight:bold;font-family:monospace">R$ ${capitalTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div></div>
    <div style="flex:1;background:#0d1117;border:1px solid #1e293b;border-radius:8px;padding:10px;text-align:center"><div style="color:#475569;font-size:10px;text-transform:uppercase;font-family:monospace">Total Aprovado</div><div style="color:#00E676;font-weight:bold;font-family:monospace">R$ ${totalAprovado.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div></div>
  </div>
  <hr>
  <h2>Análise do Gestor</h2>
  <p style="line-height:1.8">${analiseHtml}</p>
  ${alertasHtml}
  ${ajustesHtml}
  <hr>
  <h2>Sugestões (${aprovadas.length} ativos)</h2>
  ${sugHtml}
  <div class="footer">APEX Manager · Gerado automaticamente</div>
</body>
</html>`
                  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `rebalanceamento-apex-${dateStr.replace(/\//g, '-')}.html`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
              >
                <Download size={12} /> Baixar
              </button>
            )}
            <button
              onClick={() => carregarSugestoes(true)}
              title="Recalcular com dados atuais (pode demorar 2-5 min)"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
              style={{ background: 'rgba(255,152,0,0.08)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.2)' }}
            >
              <RefreshCw size={12} /> Atualizar dados
              {portfolioCost && <span style={{ fontSize: 9, color: '#b45309', opacity: 0.7 }}>{portfolioCost}</span>}
            </button>
          </div>
        </div>
        {/* Observação só aparece quando gestor_analise não está disponível */}
        {observacao && !gestorAnalise && (
          <p className="text-sm mt-3 px-4 py-3 rounded-xl leading-relaxed"
            style={{ background: 'rgba(255,152,0,0.06)', border: '1px solid rgba(255,152,0,0.15)', color: '#94a3b8' }}>
            {observacao}
          </p>
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
            {/* Score */}
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

          {/* Análise executiva */}
          {gestorAnalise.analise && (
            <div className="px-5 pt-4 pb-3">
              <div className="text-sm leading-relaxed space-y-1.5" style={{ color: '#94a3b8' }}>
                {gestorAnalise.analise.split('\n').map((line, i) => {
                  if (!line.trim()) return <div key={i} className="h-1" />
                  const parts = line.split(/\*\*(.*?)\*\*/g)
                  return (
                    <p key={i}>
                      {parts.map((part, j) =>
                        j % 2 === 1
                          ? <strong key={j} style={{ color: '#e2e8f0' }}>{part}</strong>
                          : part
                      )}
                    </p>
                  )
                })}
              </div>
            </div>
          )}

          {/* Alertas */}
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

          {/* Retry IA — quando fallback algorítmico em rebalanceamento */}
          {!gestorAnalise.usou_ia && modo === 'rebalanceamento' && (
            <div className="px-4 py-3" style={{ borderTop: '1px solid rgba(255,152,0,0.1)' }}>
              <button
                onClick={() => carregarSugestoes(true)}
                disabled={carregando}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium transition-colors"
                style={{ background: 'rgba(255,152,0,0.12)', color: '#FF9800', border: '1px solid rgba(255,152,0,0.3)' }}
              >
                <BrainCircuit size={14} />
                {carregando ? 'Processando...' : 'Tentar análise com IA'}
                {portfolioCost && <span style={{ fontSize: 9, color: '#b45309', opacity: 0.7 }}>{portfolioCost}</span>}
              </button>
            </div>
          )}

          {/* Ajustes realizados */}
          {gestorAnalise.ajustes_realizados.length > 0 && (
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

      {/* Resumo financeiro */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
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

      {/* Ações rápidas */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
        className="flex items-center justify-between mb-5"
      >
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#475569' }}>
          {qtdAprovadas} de {sugestoes.length} sugestões aprovadas
        </p>
        <div className="flex gap-2">
          <button
            onClick={aprovarTodas}
            className="text-xs px-3 py-1.5 rounded-lg transition-all"
            style={{ background: 'rgba(0,230,118,0.08)', color: '#00E676', border: '1px solid rgba(0,230,118,0.2)' }}
          >
            Aprovar todas
          </button>
          <button
            onClick={rejeitarTodas}
            className="text-xs px-3 py-1.5 rounded-lg transition-all"
            style={{ background: 'rgba(255,82,82,0.06)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.15)' }}
          >
            Rejeitar todas
          </button>
          <button
            onClick={() => carregarSugestoes()}
            className="text-xs px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5"
            style={{ background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid #1e293b' }}
            title="Gerar novas sugestões"
          >
            <RefreshCw size={11} /> Regerar
            {portfolioCost && <span style={{ fontSize: 9, color: '#475569', opacity: 0.7 }}>{portfolioCost}</span>}
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
              {/* Cabeçalho do módulo */}
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

              {/* Itens do módulo */}
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
                    {/* Botão aprovar/rejeitar */}
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

                    {/* Info do ativo */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold font-mono" style={{ color: '#f1f5f9' }}>
                              {s.item.ticker}
                            </span>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                              style={{ background: `${cor}15`, color: cor, border: `1px solid ${cor}30` }}>
                              {s.item.tipo}
                            </span>
                          </div>
                          <p className="text-xs mt-0.5" style={{ color: '#94a3b8' }}>{s.item.nome}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className="text-sm font-mono font-semibold" style={{ color: '#f1f5f9' }}>
                            R$ {fmt(s.item.valor_total)}
                          </p>
                          <p className="text-[10px] font-mono mt-0.5" style={{ color: '#475569' }}>
                            {s.item.quantidade % 1 === 0
                              ? `${s.item.quantidade.toFixed(0)} un × R$ ${fmt(s.item.preco_atual)}`
                              : `R$ ${fmt(s.item.preco_atual)}`
                            }
                          </p>
                        </div>
                      </div>
                      {s.item.justificativa && (
                        <div className="text-xs mt-2 leading-relaxed whitespace-pre-line" style={{ color: '#94a3b8' }}>
                          {s.item.justificativa.split(/\*\*(.*?)\*\*/g).map((part: string, i: number) =>
                            i % 2 === 1
                              ? <strong key={i} style={{ color: '#e2e8f0' }}>{part}</strong>
                              : <span key={i}>{part}</span>
                          )}
                        </div>
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
            <span style={{ color: '#FF9800' }}>Caixa / Liquidez</span> (sugestões rejeitadas + capital restante)
          </span>
        </motion.div>
      )}

      {/* Erro ao aplicar */}
      {erroAplicar && (
        <div className="rounded-xl px-4 py-3 mb-4 text-sm"
          style={{ background: 'rgba(255,82,82,0.06)', border: '1px solid rgba(255,82,82,0.2)', color: '#FF5252' }}>
          {erroAplicar}
        </div>
      )}

      {/* Botões de ação */}
      <div className="flex gap-3">
        <button
          onClick={() => navigate('/positions')}
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
            background: aplicando ? 'rgba(255,255,255,0.03)' : 'rgba(255,152,0,0.15)',
            border: `1px solid ${aplicando ? '#1e293b' : 'rgba(255,152,0,0.4)'}`,
            color: aplicando ? '#475569' : '#FF9800',
          }}
        >
          {aplicando
            ? <><Loader2 size={15} className="animate-spin" /> Aplicando...</>
            : <><FlaskConical size={15} /> Confirmar {qtdAprovadas} posição{qtdAprovadas !== 1 ? 'ões' : ''} <ChevronRight size={15} /></>
          }
        </button>
      </div>
    </div>
  )
}
