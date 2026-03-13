/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0e17',
          secondary: '#0f1729',
          card: 'rgba(15, 23, 42, 0.6)',
          elevated: '#111827',
        },
        border: {
          DEFAULT: '#1e293b',
          light: '#2d3f5c',
        },
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        green: {
          primary: '#00E676',
          secondary: '#00BFA5',
          light: '#1DE9B6',
          pale: '#64FFDA',
          surface: '#A7FFEB',
          'surface-alpha': 'rgba(0, 230, 118, 0.08)',
        },
        yellow: {
          DEFAULT: '#FFD740',
          surface: 'rgba(255, 215, 64, 0.1)',
        },
        red: {
          DEFAULT: '#FF5252',
          surface: 'rgba(255, 82, 82, 0.1)',
        },
      },
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['Space Mono', 'monospace'],
      },
      backgroundImage: {
        'green-gradient': 'linear-gradient(135deg, #00E676, #00BFA5)',
        'card-gradient': 'linear-gradient(145deg, rgba(15, 23, 42, 0.8), rgba(10, 14, 23, 0.9))',
        'glow-green': 'radial-gradient(circle at center, rgba(0, 230, 118, 0.15) 0%, transparent 70%)',
      },
      boxShadow: {
        'green-glow': '0 0 20px rgba(0, 230, 118, 0.15)',
        'card': '0 4px 24px rgba(0, 0, 0, 0.4)',
        'card-hover': '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(0, 230, 118, 0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
        'typewriter': 'typewriter 0.05s steps(1) forwards',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(20px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 230, 118, 0.1)' },
          '50%': { boxShadow: '0 0 40px rgba(0, 230, 118, 0.25)' },
        },
      },
    },
  },
  plugins: [],
}
