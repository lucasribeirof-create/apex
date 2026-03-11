import { useState, useEffect } from 'react'
import api from '@/services/api'

interface CostData {
  estimates: Record<string, number>
  provider: string | null
  tier: string // "paid" | "free" | "none"
}

let _cache: CostData | null = null
let _fetching = false
let _listeners: Array<(d: CostData) => void> = []

function _fetch() {
  if (_fetching) return
  _fetching = true
  api.get('/settings/ai/cost-estimates')
    .then(r => {
      _cache = r.data
      _listeners.forEach(fn => fn(_cache!))
    })
    .catch(() => {
      _cache = { estimates: {}, provider: null, tier: 'none' }
      _listeners.forEach(fn => fn(_cache!))
    })
    .finally(() => { _fetching = false; _listeners = [] })
}

export function useCostEstimates() {
  const [data, setData] = useState<CostData | null>(_cache)

  useEffect(() => {
    if (_cache) { setData(_cache); return }
    _listeners.push(setData)
    _fetch()
  }, [])

  const format = (key: string): string => {
    if (!data || data.tier === 'none') return ''
    if (data.tier === 'free') return 'grátis'
    const v = data.estimates[key]
    if (v == null) return ''
    if (v < 0.01) return '~$0.01'
    return `~$${v.toFixed(2)}`
  }

  return { costs: data?.estimates ?? {}, tier: data?.tier ?? 'none', format }
}
