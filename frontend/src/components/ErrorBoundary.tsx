import { Component, ErrorInfo, ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

/**
 * Error Boundary — captura crashes de componentes filhos e exibe tela amigável.
 * Sem isso, qualquer exceção não tratada derruba a aplicação inteira.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[APEX] Erro não tratado:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen flex items-center justify-center p-6"
          style={{ background: '#0a0e17' }}
        >
          <div className="text-center max-w-sm space-y-5">
            <div
              className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center text-2xl"
              style={{ background: 'rgba(255,82,82,0.1)', border: '1px solid rgba(255,82,82,0.25)' }}
            >
              ⚠️
            </div>
            <div>
              <h1 className="text-lg font-bold mb-1" style={{ color: '#f1f5f9' }}>
                Algo deu errado
              </h1>
              <p className="text-sm" style={{ color: '#64748b' }}>
                Ocorreu um erro inesperado. Recarregue a página para continuar.
              </p>
            </div>
            {this.state.error?.message && (
              <pre
                className="text-xs text-left p-3 rounded-lg overflow-auto max-h-32"
                style={{ background: '#0d1117', color: '#FF5252', border: '1px solid #1e293b' }}
              >
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={() => window.location.reload()}
              className="px-5 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: 'rgba(0,230,118,0.1)',
                color: '#00E676',
                border: '1px solid rgba(0,230,118,0.25)',
              }}
            >
              Recarregar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
