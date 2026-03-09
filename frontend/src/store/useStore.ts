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
  usage?: { in: number; out: number; cost: number; provider: string; model: string } | null
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
  tokenUsage: { totalIn: number; totalOut: number; totalCost: number; date: string }
  tokenBudget: number | null  // orçamento em USD definido pelo usuário
  tokenSpentAll: number       // gasto total acumulado (nunca reseta)
  carteiraCache: Record<string, string>  // cache de diagnóstico por módulo
  carteiraModulo: string                  // módulo selecionado no diagnóstico

  // Actions
  setUser: (userId: string, userName: string) => void
  setStrategy: (strategyType: StrategyType) => void
  setPortfolioId: (id: string) => void
  setPortfolioAtivo: (p: PortfolioInfo | null) => void
  setPortfolios: (list: PortfolioInfo[]) => void
  setChatMessages: (msgs: ChatMessage[]) => void
  addTokenUsage: (inTokens: number, outTokens: number, cost: number) => void
  setTokenBudget: (budget: number | null) => void
  setCarteiraCache: (modulo: string, texto: string) => void
  setCarteiraModulo: (modulo: string) => void
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
      tokenUsage: { totalIn: 0, totalOut: 0, totalCost: 0, date: new Date().toISOString().slice(0, 10) },
      tokenBudget: null,
      tokenSpentAll: 0,
      carteiraCache: {},
      carteiraModulo: 'todos',

      setUser: (userId, userName) => set({ userId, userName }),
      setStrategy: (strategyType) => set({ strategyType }),
      setPortfolioId: (id) => set({ portfolioId: id }),
      setPortfolioAtivo: (p) => set({ portfolioAtivo: p }),
      setPortfolios: (list) => set({ portfolios: list }),
      setChatMessages: (msgs) => set({ chatMessages: msgs }),
      addTokenUsage: (inTokens, outTokens, cost) => set((state) => {
        const today = new Date().toISOString().slice(0, 10)
        const prev = state.tokenUsage.date === today ? state.tokenUsage : { totalIn: 0, totalOut: 0, totalCost: 0, date: today }
        return {
          tokenUsage: { totalIn: prev.totalIn + inTokens, totalOut: prev.totalOut + outTokens, totalCost: prev.totalCost + cost, date: today },
          tokenSpentAll: state.tokenSpentAll + cost,
        }
      }),
      setTokenBudget: (budget) => set({ tokenBudget: budget }),
      setCarteiraCache: (modulo, texto) => set((state) => ({ carteiraCache: { ...state.carteiraCache, [modulo]: texto } })),
      setCarteiraModulo: (modulo) => set({ carteiraModulo: modulo }),
      clearChat: () => set({ chatMessages: [] }),
      reset: () => set({ userId: null, userName: null, strategyType: null, portfolioId: null, portfolioAtivo: null, portfolios: [], chatMessages: [], tokenUsage: { totalIn: 0, totalOut: 0, totalCost: 0, date: new Date().toISOString().slice(0, 10) }, tokenBudget: null, tokenSpentAll: 0, carteiraCache: {}, carteiraModulo: 'todos' }),
    }),
    { name: 'apex-store' }
  )
)
