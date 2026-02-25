import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Activity, DollarSign, Calendar } from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip } from 'recharts'
import api from '@/services/api'
import { useStore } from '@/store/useStore'

// Mock performance data para visualizar o layout
const mockPerformance = [
  { date: 'Set', apex: 0, ibov: 0, cdi: 0 },
  { date: 'Out', apex: 4.2, ibov: 2.1, cdi: 0.9 },
  { date: 'Nov', apex: 8.7, ibov: 3.8, cdi: 1.8 },
  { date: 'Dez', apex: 6.1, ibov: 1.2, cdi: 2.7 },
  { date: 'Jan', apex: 11.3, ibov: 5.4, cdi: 3.6 },
  { date: 'Fev', apex: 14.8, ibov: 4.9, cdi: 4.5 },
]

const allocationData = [
  { module: 'ETFs', target: 35, current: 31, color: '#00E676' },
  { module: 'FIIs', target: 20, current: 22, color: '#00BFA5' },
  { module: 'Renda Fixa', target: 20, current: 24, color: '#1DE9B6' },
  { module: 'Momentum', target: 15, current: 13, color: '#64FFDA' },
  { module: 'Caixa', target: 10, current: 10, color: '#475569' },
]

function getDeviation(target: number, current: number) {
  const diff = current - target
  if (Math.abs(diff) <= 2) return { color: '#00E676', label: 'OK', bg: 'rgba(0, 230, 118, 0.08)' }
  if (Math.abs(diff) <= 5) return { color: '#FFD740', label: `${diff > 0 ? '+' : ''}${diff}%`, bg: 'rgba(255, 215, 64, 0.08)' }
  return { color: '#FF5252', label: `${diff > 0 ? '+' : ''}${diff}%`, bg: 'rgba(255, 82, 82, 0.08)' }
}

export default function DashboardPage() {
  const { userName, strategyType } = useStore()

  const metrics = [
    { label: 'Patrimônio Total', value: 'R$ 485.200', change: '+R$ 3.840', positive: true, icon: DollarSign },
    { label: 'Retorno no Mês', value: '+4,8%', change: 'vs CDI +3,1%', positive: true, icon: TrendingUp },
    { label: 'Retorno no Ano', value: '+14,8%', change: 'vs IBOV +4,9%', positive: true, icon: Activity },
    { label: 'Renda do Mês', value: 'R$ 1.240', change: 'Dividendos + FIIs', positive: true, icon: Calendar },
  ]

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Dashboard</h1>
        <p className="text-sm mt-1" style={{ color: '#64748b' }}>
          {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
      </div>

      {/* RENDA Strategy: yield metrics */}
      {strategyType === 'RENDA' && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl p-5 space-y-4"
          style={{ background: 'rgba(0,191,165,0.04)', border: '1px solid rgba(0,191,165,0.15)' }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#00BFA5' }}>APEX RENDA — Métricas de Renda</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Renda Mensal Projetada', value: 'R$ 1.240', sub: 'Dividendos + JCP + FIIs', color: '#00BFA5' },
              { label: 'Yield on Cost', value: '8,4% a.a.', sub: 'Sobre preço médio', color: '#00BFA5' },
              { label: 'Cobertura da Meta', value: '62%', sub: 'R$ 1.240 / R$ 2.000 alvo', color: '#FFD740' },
            ].map((item) => (
              <div key={item.label} className="rounded-lg p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #1e293b' }}>
                <p className="text-xs font-mono uppercase tracking-wider mb-2" style={{ color: '#64748b' }}>{item.label}</p>
                <p className="text-xl font-bold font-data" style={{ color: item.color }}>{item.value}</p>
                <p className="text-xs mt-1" style={{ color: '#475569' }}>{item.sub}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        {metrics.map((m, i) => (
          <motion.div
            key={m.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="apex-card p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>{m.label}</span>
              <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 230, 118, 0.08)' }}>
                <m.icon size={15} style={{ color: '#00E676' }} />
              </div>
            </div>
            <p className="text-xl font-bold font-data" style={{ color: '#f1f5f9' }}>{m.value}</p>
            <p className="text-xs mt-1" style={{ color: m.positive ? '#00E676' : '#FF5252' }}>{m.change}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Performance Chart */}
        <motion.div
          className="apex-card p-5 col-span-2"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-sm font-medium" style={{ color: '#94a3b8' }}>PERFORMANCE DESDE O INÍCIO</h3>
            <div className="flex gap-4 text-xs font-mono">
              {[
                { label: 'APEX', color: '#00E676' },
                { label: 'IBOV', color: '#4A6FA5' },
                { label: 'CDI', color: '#475569' },
              ].map((l) => (
                <div key={l.label} className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 rounded" style={{ background: l.color }} />
                  <span style={{ color: '#64748b' }}>{l.label}</span>
                </div>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={mockPerformance}>
              <defs>
                <linearGradient id="apexGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00E676" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#00E676" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ background: '#0f1729', border: '1px solid #1e293b', borderRadius: '8px' }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v: number) => [`${v}%`, '']}
              />
              <Area type="monotone" dataKey="apex" stroke="#00E676" fill="url(#apexGrad)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="ibov" stroke="#4A6FA5" fill="transparent" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              <Area type="monotone" dataKey="cdi" stroke="#475569" fill="transparent" strokeWidth={1.5} dot={false} strokeDasharray="2 2" />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Allocation */}
        <motion.div
          className="apex-card p-5"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <h3 className="text-sm font-medium mb-5" style={{ color: '#94a3b8' }}>ALOCAÇÃO</h3>
          <div className="space-y-3">
            {allocationData.map((item) => {
              const dev = getDeviation(item.target, item.current)
              return (
                <div key={item.module}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs" style={{ color: '#94a3b8' }}>{item.module}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono" style={{ color: '#f1f5f9' }}>{item.current}%</span>
                      <span
                        className="text-xs font-mono px-1.5 py-0.5 rounded"
                        style={{ color: dev.color, background: dev.bg }}
                      >
                        {dev.label}
                      </span>
                    </div>
                  </div>
                  <div className="allocation-bar">
                    <div className="allocation-fill" style={{ width: `${(item.current / 40) * 100}%`, background: item.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </motion.div>
      </div>

      {/* Regime */}
      <motion.div
        className="apex-card p-4 flex items-center gap-3"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        <div className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ background: '#00E676' }} />
        <span className="text-sm font-mono" style={{ color: '#00E676' }}>BULL</span>
        <span className="text-sm" style={{ color: '#64748b' }}>
          BOVA11 acima da MM200 há 18 pregões · MM50 acima da MM200 com inclinação positiva
        </span>
      </motion.div>
    </div>
  )
}
