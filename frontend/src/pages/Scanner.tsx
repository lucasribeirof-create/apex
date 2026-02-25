import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, RefreshCw, Zap } from 'lucide-react'
import api from '@/services/api'

export default function ScannerPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const runScan = async () => {
    setLoading(true)
    try {
      const res = await api.get('/scanner/scan')
      setData(res.data)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Search size={18} style={{ color: '#00E676' }} />
          <h1 className="text-2xl font-bold" style={{ color: '#f1f5f9' }}>Scanner APEX</h1>
        </div>
        <button onClick={runScan} disabled={loading} className="btn-primary flex items-center gap-2">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Escaneando...' : 'Executar Scanner'}
        </button>
      </div>

      {!data && !loading && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="apex-card p-8 text-center">
          <Zap size={32} style={{ color: '#00E676', margin: '0 auto 16px' }} />
          <h3 className="text-lg font-semibold mb-2" style={{ color: '#f1f5f9' }}>Scanner APEX — 5 Filtros Sequenciais</h3>
          <p className="text-sm mb-6" style={{ color: '#64748b' }}>
            Varre a watchlist com os filtros: MM200, alinhamento de médias, rompimento 60d, volume e força relativa.
            Score ≥ 75 = trade gerado automaticamente.
          </p>
          <button onClick={runScan} className="btn-primary">Executar Agora</button>
        </motion.div>
      )}

      {loading && (
        <div className="flex items-center gap-3 mt-12" style={{ color: '#64748b' }}>
          <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: '#1e293b', borderTopColor: '#00E676' }} />
          <span>Calculando scores APEX...</span>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex gap-4">
            {[
              { label: 'TRADE', count: data.trades?.length, color: '#00E676' },
              { label: 'MONITOR', count: data.monitor?.length, color: '#FFD740' },
              { label: 'FORA', count: data.out?.length, color: '#64748b' },
            ].map((s) => (
              <div key={s.label} className="apex-card px-4 py-3 flex items-center gap-3">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
                <span className="text-sm font-mono" style={{ color: s.color }}>{s.label}</span>
                <span className="text-sm font-bold font-data" style={{ color: '#f1f5f9' }}>{s.count}</span>
              </div>
            ))}
          </div>

          {data.trades?.length > 0 && (
            <div className="apex-card overflow-hidden">
              <div className="px-5 py-3 border-b" style={{ borderColor: '#1e293b' }}>
                <h3 className="text-sm font-medium" style={{ color: '#00E676' }}>OPORTUNIDADES — SCORE ≥ 75</h3>
              </div>
              <div className="divide-y" style={{ borderColor: '#1e293b' }}>
                {data.trades.map((t: any) => (
                  <div key={t.ticker} className="px-5 py-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium font-mono" style={{ color: '#f1f5f9' }}>{t.ticker}</p>
                      {t.trade_setup && (
                        <p className="text-xs mt-0.5 font-mono" style={{ color: '#64748b' }}>
                          Entrada: R$ {t.trade_setup.entry?.toFixed(2)} · Stop: R$ {t.trade_setup.stop_initial?.toFixed(2)}
                        </p>
                      )}
                    </div>
                    <div className="text-right">
                      <div
                        className="text-lg font-bold font-data"
                        style={{ color: t.score >= 75 ? '#00E676' : t.score >= 50 ? '#FFD740' : '#64748b' }}
                      >
                        {t.score}
                      </div>
                      <p className="text-xs font-mono" style={{ color: '#64748b' }}>score</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
