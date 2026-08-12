/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
      },
      colors: {
        glass: {
          DEFAULT: 'rgba(255, 255, 255, 0.06)',
          border: 'rgba(255, 255, 255, 0.12)',
          highlight: 'rgba(255, 255, 255, 0.5)',
          shadow: 'rgba(0, 0, 0, 0.45)',
        },
        surface: {
          50: '#f0f4ff',
          100: '#dbe4ff',
          200: '#bac8ff',
          300: '#91a7ff',
          400: '#748ffc',
          500: '#5c7cfa',
          600: '#4c6ef5',
          700: '#4263eb',
          800: '#3b5bdb',
          900: '#364fc7',
        },
        navy: {
          50: '#e8eaf0',
          100: '#c5cbe0',
          200: '#9ea8cd',
          300: '#7685b8',
          400: '#586aa8',
          500: '#3b5098',
          600: '#2f438a',
          700: '#1f3478',
          800: '#0f2566',
          900: '#0a1a4a',
          950: '#060f2d',
        },
        risk: {
          low: '#22c55e',
          medium: '#f59e0b',
          high: '#ef4444',
          critical: '#dc2626',
        },
        severity: {
          info: '#3b82f6',
          low: '#22c55e',
          medium: '#f59e0b',
          high: '#ef4444',
          critical: '#dc2626',
        },
        'ai-purple': '#8b5cf6',
      },
      backdropBlur: {
        glass: '24px',
      },
      boxShadow: {
        glass: '0 24px 60px rgba(0, 0, 0, 0.45)',
        'glass-sm': '0 12px 30px rgba(0, 0, 0, 0.3)',
        'glass-lg': '0 36px 80px rgba(0, 0, 0, 0.55)',
        'glass-inner': 'inset 0 1px 1px rgba(255, 255, 255, 0.5), inset 0 -8px 20px rgba(255, 255, 255, 0.06)',
      },
      borderRadius: {
        glass: '28px',
        'glass-sm': '16px',
        'glass-lg': '32px',
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
        'slide-up': 'slide-up 0.5s ease-out',
        'fade-in': 'fade-in 0.3s ease-out',
        'count-up': 'count-up 0.6s ease-out',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(59, 130, 246, 0.1)' },
          '50%': { boxShadow: '0 0 30px rgba(59, 130, 246, 0.3)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'slide-up': {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
