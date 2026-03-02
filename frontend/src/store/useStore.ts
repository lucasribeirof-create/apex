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

interface AppState {
  userId: string | null
  userName: string | null
  strategyType: StrategyType | null
  portfolioId: string | null
  portfolioAtivo: PortfolioInfo | null
  portfolios: PortfolioInfo[]
  chatMessages: ChatMessage[]

  // Actions
  setUser: (userId: string, userName: string) => void
  setStrategy: (strategyType: StrategyType) => void
  setPortfolioId: (id: string) => void
  setPortfolioAtivo: (p: PortfolioInfo | null) => void
  setPortfolios: (list: PortfolioInfo[]) => void
  setChatMessages: (msgs: ChatMessage[]) => void
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

      setUser: (userId, userName) => set({ userId, userName }),
      setStrategy: (strategyType) => set({ strategyType }),
      setPortfolioId: (id) => set({ portfolioId: id }),
      setPortfolioAtivo: (p) => set({ portfolioAtivo: p }),
      setPortfolios: (list) => set({ portfolios: list }),
      setChatMessages: (msgs) => set({ chatMessages: msgs }),
      clearChat: () => set({ chatMessages: [] }),
      reset: () => set({ userId: null, userName: null, strategyType: null, portfolioId: null, portfolioAtivo: null, portfolios: [], chatMessages: [] }),
    }),
    { name: 'apex-store' }
  )
)
