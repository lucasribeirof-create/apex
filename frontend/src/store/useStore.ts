import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type StrategyType = 'CORE' | 'ALPHA' | 'RENDA' | 'CUSTOM'

interface AppState {
  userId: string | null
  userName: string | null
  strategyType: StrategyType | null
  portfolioId: string | null

  // Actions
  setUser: (userId: string, userName: string) => void
  setStrategy: (strategyType: StrategyType) => void
  setPortfolioId: (id: string) => void
  reset: () => void
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      userId: null,
      userName: null,
      strategyType: null,
      portfolioId: null,

      setUser: (userId, userName) => set({ userId, userName }),
      setStrategy: (strategyType) => set({ strategyType }),
      setPortfolioId: (id) => set({ portfolioId: id }),
      reset: () => set({ userId: null, userName: null, strategyType: null, portfolioId: null }),
    }),
    { name: 'apex-store' }
  )
)
