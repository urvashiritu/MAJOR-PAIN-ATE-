/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['ui-monospace', 'Cascadia Code', 'JetBrains Mono', 'Menlo', 'Consolas', 'monospace'],
        mono: ['ui-monospace', 'Cascadia Code', 'JetBrains Mono', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        paper: {
          DEFAULT: '#0b0e14',
          50: '#10151d',
          100: '#151a24',
          200: '#1a2132',
          300: '#232c40',
        },
        ink: {
          DEFAULT: '#e8ecf4',
          dim: '#8b93a5',
          faint: '#5a6274',
        },
        ochre: {
          DEFAULT: '#e8a33d',
          dim: '#b07d2b',
        },
        critical: '#e5484d',
        low: '#57b06c',
        high: '#ff9b9e',
        info: '#6ea8e8',
        risk: {
          low: '#57b06c',
          medium: '#e8a33d',
          high: '#ff9b9e',
          critical: '#e5484d',
        },
        severity: {
          info: '#6ea8e8',
          low: '#57b06c',
          medium: '#e8a33d',
          high: '#ff9b9e',
          critical: '#e5484d',
        },
      },
    },
  },
  plugins: [],
}