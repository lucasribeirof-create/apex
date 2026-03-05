import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type StrategyType = 'CORE' | 'ALPHA' | 'RENDA' | 'CUSTOM'

export interface PortfolioInfo {
  id: number
  nome: string
  tipo: 'real' | 'simulada' | 'tese'
  ativo?: boolean
  patrimonio_total?: number
}

// ─── Chat message types (exported so Chat.tsx can import) ─────────────────────
export interface ChatRegularMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatProposalAction {
  tipo: string
  descricao_curta: string
  nova_estrategia: string | null
  nova_alocacao: Record<string, number>
  pode_aplicar: boolean
  motivo_bloqueio: string | null
}

export interface ChatProposalMessage {
  role: 'proposal'
  analise: string
  acao_proposta: ChatProposalAction | null
  status: 'pendente' | 'aprovado' | 'cancelado'
}

export type ChatMessage = ChatRegularMessage | ChatProposalMessage

// ─── Rebalancing snapshot (persisted so navigating away doesn't lose results) ──
export interface RebalSugestaoSnapshot {
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
  aprovada: boolean
}

export interface RebalPosicaoSnapshot {
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

export interface UltimoRebalanceamento {
  sugestoes: RebalSugestaoSnapshot[]
  posicoesAtuais: RebalPosicaoSnapshot[]
  capitalTotal: number
  capitalRestante: number
  observacao: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  gestorAnalise: any | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  planoEstrategico: any | null
  cenarioSelecionado: string | null
  portfolioId: number
  modo: string
  etapa: string
  timestamp: number
}

interface AppState {
  userId: string | null
  userName: string | null
  strategyType: StrategyType | null
  portfolioId: string | null
  portfolioAtivo: PortfolioInfo | null
  portfolios: PortfolioInfo[]
  chatMessages: ChatMessage[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ultimoPlanoEstrategico: any | null   // Persiste o plano estratégico do primeiro portfólio
  cenarioEscolhido: string | null      // Cenário escolhido na Fase 1 (Conservador/Recomendado/Agressivo)
  ultimoRebalanceamento: UltimoRebalanceamento | null

  // Actions
  setUser: (userId: string, userName: string) => void
  setStrategy: (strategyType: StrategyType) => void
  setPortfolioId: (id: string) => void
  setPortfolioAtivo: (p: PortfolioInfo | null) => void
  setPortfolios: (list: PortfolioInfo[]) => void
  setChatMessages: (msgs: ChatMessage[]) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setUltimoPlanoEstrategico: (plano: any) => void
  setCenarioEscolhido: (cenario: string | null) => void
  setUltimoRebalanceamento: (data: UltimoRebalanceamento) => void
  clearUltimoRebalanceamento: () => void
  clearChat: () => void
  reset: () => void
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      userId: null,
      userName: null,
      strategyType: null,
      portfolioId: null,
      portfolioAtivo: null,
      portfolios: [],
      chatMessages: [],
      ultimoPlanoEstrategico: null,
      cenarioEscolhido: null,
      ultimoRebalanceamento: null,

      setUser: (userId, userName) => set({ userId, userName }),
      setStrategy: (strategyType) => set({ strategyType }),
      setPortfolioId: (id) => set({ portfolioId: id }),
      setPortfolioAtivo: (p) => set({ portfolioAtivo: p }),
      setPortfolios: (list) => set({ portfolios: list }),
      setChatMessages: (msgs) => set({ chatMessages: msgs }),
      setUltimoPlanoEstrategico: (plano) => set({ ultimoPlanoEstrategico: plano }),
      setCenarioEscolhido: (cenario) => set({ cenarioEscolhido: cenario }),
      setUltimoRebalanceamento: (data) => set({ ultimoRebalanceamento: data }),
      clearUltimoRebalanceamento: () => set({ ultimoRebalanceamento: null }),
      clearChat: () => set({ chatMessages: [] }),
      reset: () => set({ userId: null, userName: null, strategyType: null, portfolioId: null, portfolioAtivo: null, portfolios: [], chatMessages: [], ultimoPlanoEstrategico: null, cenarioEscolhido: null, ultimoRebalanceamento: null }),
    }),
    { name: 'apex-store' }
  )
)
