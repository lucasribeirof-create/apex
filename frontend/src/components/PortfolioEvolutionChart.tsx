/**
 * Gráfico de evolução patrimonial: Carteira vs CDI.
 * Alimentado por snapshots diários salvos ao clicar "Atualizar Preços".
 */
import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import api from '@/services/api'

interface Snap {
  date: string
  patrimonio: number
  pl_pct: number
  cdi_pct: number
}

export default function PortfolioEvolutionChart() {
  const [data, setData] = useState<Snap[]>([])

  useEffect(() => {
    api.get('/portfolio/evolucao')
      .then(res => { if (Array.isArray(res.data) && res.data.length >= 2) setData(res.data) })
      .catch(() => {})
  }, [])

  if (data.length < 2) return null

  const fmtDate = (d: string) => {
    const [, m, day] = d.split('-')
    return `${day}/${m}`
  }

  return (
    <div className="apex-card p-4" style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12 }}>
      <p className="text-xs font-mono uppercase tracking-wider mb-3" style={{ color: '#64748b' }}>
        📈 Evolução Patrimonial
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: '#64748b', fontSize: 10 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={v => `${v.toFixed(1)}%`} />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
            labelFormatter={fmtDate}
            formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
          <Line type="monotone" dataKey="pl_pct" name="Carteira" stroke="#00E676" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="cdi_pct" name="CDI" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 5" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
