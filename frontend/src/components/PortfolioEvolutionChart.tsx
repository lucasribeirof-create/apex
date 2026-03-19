/**
 * Gráfico de rentabilidade: Carteira vs CDI vs IBOV vs S&P500.
 * Alimentado por snapshots diários + benchmarks via yfinance.
 * Filtro de período: Tudo, 1M, 3M, 6M, 1A, ou intervalo customizado.
 */
import { useState, useEffect, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { Calendar } from 'lucide-react'
import api from '@/services/api'

interface DataPoint {
  date: string
  carteira_pct: number
  cdi_pct: number
  ibov_pct: number | null
  sp500_pct: number | null
}

const LINES = [
  { key: 'carteira_pct', name: 'Carteira', color: '#00E676', width: 2.5, dash: undefined },
  { key: 'cdi_pct', name: 'CDI', color: '#94a3b8', width: 1.5, dash: '5 5' },
  { key: 'ibov_pct', name: 'IBOV', color: '#FFD740', width: 1.5, dash: undefined },
  { key: 'sp500_pct', name: 'S&P 500', color: '#42A5F5', width: 1.5, dash: '4 3' },
] as const

const PRESETS = [
  { label: 'Tudo', days: 0 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1A', days: 365 },
] as const

function rebaseData(data: DataPoint[]): DataPoint[] {
  if (data.length === 0) return data
  const first = data[0]
  return data.map(d => ({
    ...d,
    carteira_pct: +(d.carteira_pct - first.carteira_pct).toFixed(2),
    cdi_pct: +(d.cdi_pct - first.cdi_pct).toFixed(2),
    ibov_pct: d.ibov_pct != null && first.ibov_pct != null
      ? +(d.ibov_pct - first.ibov_pct).toFixed(2) : d.ibov_pct,
    sp500_pct: d.sp500_pct != null && first.sp500_pct != null
      ? +(d.sp500_pct - first.sp500_pct).toFixed(2) : d.sp500_pct,
  }))
}

export default function PortfolioEvolutionChart() {
  const [rawData, setRawData] = useState<DataPoint[]>([])
  const [visible, setVisible] = useState<Record<string, boolean>>({
    carteira_pct: true, cdi_pct: true, ibov_pct: true, sp500_pct: true,
  })
  const [preset, setPreset] = useState(0) // 0 = Tudo
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [showCustom, setShowCustom] = useState(false)

  useEffect(() => {
    api.get('/portfolio/evolucao')
      .then(res => { if (Array.isArray(res.data) && res.data.length >= 2) setRawData(res.data) })
      .catch(() => {})
  }, [])

  const data = useMemo(() => {
    if (rawData.length === 0) return []
    let filtered = rawData

    if (showCustom && customFrom) {
      filtered = filtered.filter(d => d.date >= customFrom && (!customTo || d.date <= customTo))
    } else if (preset > 0) {
      const cutoff = new Date()
      cutoff.setDate(cutoff.getDate() - preset)
      const cutStr = cutoff.toISOString().slice(0, 10)
      filtered = filtered.filter(d => d.date >= cutStr)
    }

    return rebaseData(filtered)
  }, [rawData, preset, showCustom, customFrom, customTo])

  if (rawData.length < 2) return null

  const fmtDate = (d: string) => {
    const [, m, day] = d.split('-')
    return `${day}/${m}`
  }

  const toggle = (key: string) => setVisible(v => ({ ...v, [key]: !v[key] }))
  const minDate = rawData[0]?.date || ''
  const maxDate = rawData[rawData.length - 1]?.date || ''

  return (
    <div className="apex-card p-4" style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12 }}>
      {/* Header row: title + line toggles */}
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
          📊 Rentabilidade vs Benchmarks
        </p>
        <div className="flex items-center gap-3">
          {LINES.map(l => (
            <button
              key={l.key}
              onClick={() => toggle(l.key)}
              className="flex items-center gap-1.5 text-[10px] font-medium transition-opacity"
              style={{ opacity: visible[l.key] ? 1 : 0.35, color: l.color }}
            >
              <span className="w-3 h-0.5 rounded-full inline-block" style={{
                background: l.color,
                borderBottom: l.dash ? `1px dashed ${l.color}` : undefined,
              }} />
              {l.name}
            </button>
          ))}
        </div>
      </div>

      {/* Date filter row */}
      <div className="flex items-center gap-2 mb-3">
        {PRESETS.map(p => (
          <button
            key={p.label}
            onClick={() => { setPreset(p.days); setShowCustom(false) }}
            className="text-[10px] px-2 py-0.5 rounded-md font-medium transition-all"
            style={{
              background: !showCustom && preset === p.days ? 'rgba(0,230,118,0.12)' : 'transparent',
              border: `1px solid ${!showCustom && preset === p.days ? '#00E67640' : '#1e293b'}`,
              color: !showCustom && preset === p.days ? '#00E676' : '#64748b',
            }}
          >
            {p.label}
          </button>
        ))}

        <div className="w-px h-4 mx-1" style={{ background: '#1e293b' }} />

        <button
          onClick={() => { setShowCustom(!showCustom); if (!customFrom) setCustomFrom(minDate) }}
          className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md font-medium transition-all"
          style={{
            background: showCustom ? 'rgba(0,230,118,0.12)' : 'transparent',
            border: `1px solid ${showCustom ? '#00E67640' : '#1e293b'}`,
            color: showCustom ? '#00E676' : '#64748b',
          }}
        >
          <Calendar size={10} /> Período
        </button>

        {showCustom && (
          <div className="flex items-center gap-1.5 ml-1">
            <input
              type="date"
              value={customFrom}
              min={minDate}
              max={maxDate}
              onChange={e => setCustomFrom(e.target.value)}
              className="text-[10px] font-mono rounded px-1.5 py-0.5"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
            />
            <span className="text-[10px]" style={{ color: '#475569' }}>até</span>
            <input
              type="date"
              value={customTo || maxDate}
              min={customFrom || minDate}
              max={maxDate}
              onChange={e => setCustomTo(e.target.value)}
              className="text-[10px] font-mono rounded px-1.5 py-0.5"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
            />
          </div>
        )}
      </div>

      {data.length < 2 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-xs" style={{ color: '#475569' }}>Período sem dados suficientes</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: '#64748b', fontSize: 10 }} />
            <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={v => `${v.toFixed(1)}%`} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
              labelStyle={{ color: '#94a3b8' }}
              labelFormatter={fmtDate}
              formatter={(v: any, name: string) => [v != null ? `${Number(v).toFixed(2)}%` : '—', name]}
            />
            {LINES.map(l => visible[l.key] && (
              <Line
                key={l.key}
                type="monotone"
                dataKey={l.key}
                name={l.name}
                stroke={l.color}
                strokeWidth={l.width}
                strokeDasharray={l.dash}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
