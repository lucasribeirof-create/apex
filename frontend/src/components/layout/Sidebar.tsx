import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Newspaper, TrendingUp, Search, MessageSquare, LogOut, RefreshCw, Settings, Lightbulb, History } from 'lucide-react'
import { useStore } from '@/store/useStore'
import PortfolioSwitcher from '@/components/PortfolioSwitcher'
import clsx from 'clsx'

const navItems = [
  { path: '/briefing', label: 'Briefing', icon: Newspaper },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/positions', label: 'Posições', icon: TrendingUp },
  { path: '/historico', label: 'Histórico', icon: History },
  { path: '/teses', label: 'Teses', icon: Lightbulb },
  { path: '/scanner', label: 'Scanner', icon: Search },
  { path: '/chat', label: 'Chat', icon: MessageSquare },
]

export default function Sidebar() {
  const { userName, strategyType, reset } = useStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    reset()
    navigate('/selecionar')
  }

  const handleSwitchUser = () => {
    reset()
    navigate('/selecionar')
  }

  const strategyColor = strategyType === 'ALPHA' ? '#00E676'
    : strategyType === 'RENDA' ? '#00BFA5'
    : strategyType === 'CUSTOM' ? '#FF9800'
    : '#94a3b8'
  const strategyBg = strategyType === 'ALPHA' ? 'rgba(0,230,118,0.1)'
    : strategyType === 'RENDA' ? 'rgba(0,191,165,0.1)'
    : strategyType === 'CUSTOM' ? 'rgba(255,152,0,0.1)'
    : 'rgba(148,163,184,0.1)'

  return (
    <aside className="w-64 min-h-screen flex flex-col border-r" style={{ borderColor: '#1e293b', background: '#0a0e17' }}>
      {/* Logo */}
      <div className="px-6 py-6 border-b" style={{ borderColor: '#1e293b' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00E676, #00BFA5)' }}>
            <span className="text-sm font-bold" style={{ color: '#0a0e17' }}>A</span>
          </div>
          <div>
            <h1 className="font-bold text-base tracking-tight" style={{ color: '#f1f5f9' }}>APEX</h1>
            <p className="text-xs font-mono" style={{ color: '#64748b' }}>Manager</p>
          </div>
        </div>
      </div>

      {/* User info */}
      <div className="px-6 py-4 border-b" style={{ borderColor: '#1e293b' }}>
        <p className="text-sm font-medium" style={{ color: '#f1f5f9' }}>{userName}</p>
        <div className="flex items-center gap-2 mt-1">
          <span
            className="text-xs font-mono px-2 py-0.5 rounded"
            style={{
              background: strategyBg,
              color: strategyColor,
              border: `1px solid ${strategyColor}33`,
            }}
          >
            APEX {strategyType}
          </span>
        </div>
      </div>

      {/* Portfolio Switcher */}
      <div className="py-3 border-b" style={{ borderColor: '#1e293b' }}>
        <PortfolioSwitcher onSwitch={() => window.dispatchEvent(new Event('portfolio-changed'))} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'text-green-primary bg-green-surface-alpha'
                  : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={18} style={{ color: isActive ? '#00E676' : undefined }} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t space-y-1" style={{ borderColor: '#1e293b' }}>
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all w-full',
              isActive ? 'text-green-primary bg-green-surface-alpha' : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
            )
          }
        >
          {({ isActive }) => (
            <>
              <Settings size={16} style={{ color: isActive ? '#00E676' : undefined }} />
              Configurações
            </>
          )}
        </NavLink>
        <button
          onClick={handleSwitchUser}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm w-full transition-all"
          style={{ color: '#64748b' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#00E676')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#64748b')}
        >
          <RefreshCw size={16} />
          Trocar carteira
        </button>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm w-full transition-all"
          style={{ color: '#64748b' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#FF5252')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#64748b')}
        >
          <LogOut size={18} />
          Sair
        </button>
      </div>
    </aside>
  )
}
