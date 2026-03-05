/**
 * EncerrarPosicaoModal — Modal inteligente para encerrar/vender posição.
 * Captura preço de venda, quantidade, destino do capital (caixa ou saque)
 * e calcula P&L realizado em tempo real.
 */
import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { X, DollarSign, ArrowRight, Wallet, LogOut, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'
import api from '@/services/api'

interface PositionInfo {
  id: number
  ticker: string
  nome: string
  tipo: string
  modulo: string
  quantidade: number
  preco_medio: number
  preco_atual: number
  valor_investido: number
  valor_atual: number
  pl_reais: number
  pl_percentual: number
}

interface Props {
  position: PositionInfo
  onClose: () => void
  onSuccess: (result: {
    venda_total: boolean
    ticker: string
    valor_venda: number
    pl_realizado: number
    destino_capital: string
  }) => void
}

export default function EncerrarPosicaoModal({ position, onClose, onSuccess }: Props) {
  const [precoVenda, setPrecoVenda] = useState(position.preco_atual.toFixed(2))
  const [qtdVendida, setQtdVendida] = useState(position.quantidade.toString())
  const [destino, setDestino] = useState<'caixa' | 'saque'>('caixa')
  const [motivo, setMotivo] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')

  const preco = parseFloat(precoVenda) || 0
  const qtd = parseFloat(qtdVendida) || 0
  const qtdMax = position.quantidade
  const qtdReal = Math.min(qtd, qtdMax)
  const vendaTotal = qtdReal >= qtdMax

  const valorVenda = useMemo(() => preco * qtdReal, [preco, qtdReal])
  const plRealizado = useMemo(
    () => (preco - position.preco_medio) * qtdReal,
    [preco, position.preco_medio, qtdReal]
  )
  const plPct = useMemo(
    () => position.preco_medio > 0 ? ((preco / position.preco_medio) - 1) * 100 : 0,
    [preco, position.preco_medio]
  )

  const fmt = (v: number) =>
    v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  const confirmar = async () => {
    if (preco <= 0 || qtdReal <= 0) {
      setErro('Preço e quantidade devem ser maiores que zero')
      return
    }
    setEnviando(true)
    setErro('')
    try {
      const res = await api.post(`/portfolio/posicoes/${position.id}/encerrar`, {
        preco_venda: preco,
        quantidade_vendida: qtdReal,
        destino_capital: destino,
        motivo: motivo || 'Encerrado manualmente',
      })
      onSuccess(res.data)
    } catch (e: any) {
      setErro(e?.response?.data?.detail || 'Erro ao encerrar posição')
      setEnviando(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)' }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="w-full max-w-md rounded-2xl overflow-hidden"
        style={{ background: '#0f172a', border: '1px solid #1e293b' }}
      >
        {/* Header */}
        <div className="px-5 py-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid #1e293b', background: 'rgba(255,82,82,0.04)' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'rgba(255,82,82,0.12)', border: '1px solid rgba(255,82,82,0.3)' }}>
              <LogOut size={15} style={{ color: '#FF5252' }} />
            </div>
            <div>
              <h3 className="text-sm font-bold" style={{ color: '#f1f5f9' }}>
                {vendaTotal ? 'Encerrar' : 'Venda Parcial'} — {position.ticker}
              </h3>
              <p className="text-[10px]" style={{ color: '#64748b' }}>{position.nome}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg transition-all hover:bg-white/5">
            <X size={16} style={{ color: '#64748b' }} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Resumo da posição */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Quantidade', value: position.quantidade.toString() },
              { label: 'PM', value: `R$ ${fmt(position.preco_medio)}` },
              { label: 'Preço Atual', value: `R$ ${fmt(position.preco_atual)}` },
            ].map(c => (
              <div key={c.label} className="rounded-lg p-2 text-center"
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1e293b' }}>
                <p className="text-[9px] font-mono uppercase" style={{ color: '#475569' }}>{c.label}</p>
                <p className="text-xs font-mono font-semibold mt-0.5" style={{ color: '#94a3b8' }}>{c.value}</p>
              </div>
            ))}
          </div>

          {/* Inputs */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-mono uppercase block mb-1" style={{ color: '#64748b' }}>
                Preço de Venda
              </label>
              <div className="relative">
                <DollarSign size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: '#475569' }} />
                <input
                  type="number"
                  step="0.01"
                  value={precoVenda}
                  onChange={e => setPrecoVenda(e.target.value)}
                  className="w-full pl-7 pr-3 py-2 rounded-lg text-sm font-mono outline-none"
                  style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-mono uppercase block mb-1" style={{ color: '#64748b' }}>
                Quantidade
              </label>
              <input
                type="number"
                step="1"
                min="1"
                max={qtdMax}
                value={qtdVendida}
                onChange={e => setQtdVendida(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm font-mono outline-none"
                style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
              />
              <button
                onClick={() => setQtdVendida(qtdMax.toString())}
                className="text-[10px] font-mono mt-1 px-1.5 py-0.5 rounded transition-all"
                style={{ color: '#FF9800', background: 'rgba(255,152,0,0.08)' }}
              >
                Vender tudo ({qtdMax})
              </button>
            </div>
          </div>

          {/* P&L Preview */}
          <div className="rounded-xl p-3" style={{
            background: plRealizado >= 0 ? 'rgba(0,230,118,0.06)' : 'rgba(255,82,82,0.06)',
            border: `1px solid ${plRealizado >= 0 ? 'rgba(0,230,118,0.2)' : 'rgba(255,82,82,0.2)'}`,
          }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                {plRealizado >= 0
                  ? <TrendingUp size={13} style={{ color: '#00E676' }} />
                  : <TrendingDown size={13} style={{ color: '#FF5252' }} />
                }
                <span className="text-[10px] font-mono uppercase" style={{ color: '#64748b' }}>
                  P&L Realizado
                </span>
              </div>
              <div className="text-right">
                <span className="text-sm font-mono font-bold" style={{
                  color: plRealizado >= 0 ? '#00E676' : '#FF5252'
                }}>
                  {plRealizado >= 0 ? '+' : ''}R$ {fmt(plRealizado)}
                </span>
                <span className="text-[10px] font-mono ml-1.5" style={{
                  color: plRealizado >= 0 ? '#00E676' : '#FF5252', opacity: 0.7
                }}>
                  ({plPct >= 0 ? '+' : ''}{plPct.toFixed(1)}%)
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-[10px] font-mono" style={{ color: '#475569' }}>
                Valor da venda
              </span>
              <span className="text-xs font-mono font-semibold" style={{ color: '#f1f5f9' }}>
                R$ {fmt(valorVenda)}
              </span>
            </div>
          </div>

          {/* Destino do capital */}
          <div>
            <label className="text-[10px] font-mono uppercase block mb-2" style={{ color: '#64748b' }}>
              O que fazer com R$ {fmt(valorVenda)}?
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setDestino('caixa')}
                className="flex items-center gap-2 p-3 rounded-xl text-xs transition-all"
                style={{
                  background: destino === 'caixa' ? 'rgba(0,230,118,0.08)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${destino === 'caixa' ? 'rgba(0,230,118,0.3)' : '#1e293b'}`,
                  color: destino === 'caixa' ? '#00E676' : '#64748b',
                }}
              >
                <Wallet size={14} />
                <div className="text-left">
                  <div className="font-semibold">Mover p/ Caixa</div>
                  <div className="text-[9px] opacity-70">Fica disponível para reinvestir</div>
                </div>
              </button>
              <button
                onClick={() => setDestino('saque')}
                className="flex items-center gap-2 p-3 rounded-xl text-xs transition-all"
                style={{
                  background: destino === 'saque' ? 'rgba(255,152,0,0.08)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${destino === 'saque' ? 'rgba(255,152,0,0.3)' : '#1e293b'}`,
                  color: destino === 'saque' ? '#FF9800' : '#64748b',
                }}
              >
                <ArrowRight size={14} />
                <div className="text-left">
                  <div className="font-semibold">Sacar</div>
                  <div className="text-[9px] opacity-70">Retirar do patrimônio</div>
                </div>
              </button>
            </div>
          </div>

          {/* Motivo (opcional) */}
          <div>
            <label className="text-[10px] font-mono uppercase block mb-1" style={{ color: '#64748b' }}>
              Motivo (opcional)
            </label>
            <input
              value={motivo}
              onChange={e => setMotivo(e.target.value)}
              placeholder="Ex: Stop atingido, realização de lucro..."
              className="w-full px-3 py-2 rounded-lg text-xs outline-none"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
            />
          </div>

          {/* Erro */}
          {erro && (
            <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
              style={{ background: 'rgba(255,82,82,0.08)', border: '1px solid rgba(255,82,82,0.2)', color: '#FF5252' }}>
              <AlertTriangle size={12} />
              {erro}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 flex gap-3" style={{ borderTop: '1px solid #1e293b' }}>
          <button onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm transition-all"
            style={{ color: '#64748b', border: '1px solid #1e293b', background: 'rgba(255,255,255,0.02)' }}>
            Cancelar
          </button>
          <button
            onClick={confirmar}
            disabled={enviando || preco <= 0 || qtdReal <= 0}
            className="flex-[2] py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2"
            style={{
              background: enviando ? 'rgba(255,255,255,0.03)' : 'rgba(255,82,82,0.15)',
              border: `1px solid ${enviando ? '#1e293b' : 'rgba(255,82,82,0.4)'}`,
              color: enviando ? '#475569' : '#FF5252',
              opacity: (preco <= 0 || qtdReal <= 0) ? 0.4 : 1,
            }}
          >
            {enviando ? 'Processando...' : vendaTotal ? 'Encerrar Posição' : 'Registrar Venda'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
