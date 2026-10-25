/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        app: 'rgb(var(--app) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        'surface-2': 'rgb(var(--surface-2) / <alpha-value>)',
        'surface-3': 'rgb(var(--surface-3) / <alpha-value>)',
        card: 'rgb(var(--card) / <alpha-value>)',
        content: 'rgb(var(--content) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        'line-strong': 'rgb(var(--line-strong) / <alpha-value>)',
        gold: {
          DEFAULT: 'rgb(var(--gold) / <alpha-value>)',
          light: 'rgb(var(--gold-light) / <alpha-value>)',
          dark: 'rgb(var(--gold-dark) / <alpha-value>)',
        },
        forest: {
          DEFAULT: 'rgb(var(--forest) / <alpha-value>)',
          light: 'rgb(var(--forest-light) / <alpha-value>)',
          dim: 'rgb(var(--forest-dim) / <alpha-value>)',
          deep: 'rgb(var(--forest-deep) / <alpha-value>)',
        },
        'on-gold': 'rgb(var(--on-gold) / <alpha-value>)',
        'on-forest': 'rgb(var(--on-forest) / <alpha-value>)',
        success: 'rgb(var(--success) / <alpha-value>)',
        'success-bg': 'rgb(var(--success-bg) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
        'danger-bg': 'rgb(var(--danger-bg) / <alpha-value>)',
        'danger-text': 'rgb(var(--danger-text) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        'warning-bg': 'rgb(var(--warning-bg) / <alpha-value>)',
        info: 'rgb(var(--info) / <alpha-value>)',
        'info-bg': 'rgb(var(--info-bg) / <alpha-value>)',
      },
      maxWidth: {
        phone: '440px',
      },
      borderRadius: {
        card: '22px',
      },
      boxShadow: {
        glow: '0 0 24px rgb(var(--gold) / 0.28)',
        'glow-sm': '0 0 12px rgb(var(--gold) / 0.2)',
        soft: '0 18px 50px -24px rgb(var(--shadow) / 0.32)',
        card: '0 10px 30px -18px rgb(var(--shadow) / 0.28)',
      },
      fontFamily: {
        sans: ['Manrope', 'Noto Sans Ethiopic', 'Segoe UI', 'system-ui', 'sans-serif'],
        display: ['Fraunces', 'Noto Sans Ethiopic', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
