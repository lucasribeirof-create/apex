/**
 * ThinkingSteps — mostra os "passos do raciocínio" da IA enquanto processa.
 * Exibe frases contextuais que ciclam suavemente durante o loading.
 */
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface ThinkingStepsProps {
  steps: string[]
  intervalMs?: number
  color?: string
}

export default function ThinkingSteps({ steps, intervalMs = 2600, color = '#00E676' }: ThinkingStepsProps) {
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    setIdx(0)
    const timer = setInterval(() => {
      setIdx(prev => (prev + 1) % steps.length)
    }, intervalMs)
    return () => clearInterval(timer)
  }, [steps.length, intervalMs])

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Dots */}
      <div className="flex gap-1.5">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full animate-bounce"
            style={{ background: color, animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>

      {/* Step text */}
      <div style={{ minHeight: 24 }}>
        <AnimatePresence mode="wait">
          <motion.p
            key={idx}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.3 }}
            className="text-sm text-center font-mono"
            style={{ color: '#475569' }}
          >
            {steps[idx]}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  )
}
