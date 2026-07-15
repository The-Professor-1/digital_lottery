/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#0d0d0d',
          50: '#1a1a1a',
          100: '#121212',
          200: '#1e1e1e',
          300: '#2a2a2a',
        },
        gold: {
          DEFAULT: '#f5a623',
          light: '#ffb84d',
          dark: '#d4891a',
        },
        forest: {
          DEFAULT: '#1e8e5a',
          dim: '#0f3d2a',
          deep: '#0a2e1f',
        },
        sold: '#5c1a1a',
      },
      maxWidth: {
        phone: '420px',
      },
      borderRadius: {
        card: '18px',
      },
      boxShadow: {
        glow: '0 0 24px rgba(245, 166, 35, 0.35)',
        'glow-sm': '0 0 12px rgba(245, 166, 35, 0.25)',
      },
      fontFamily: {
        display: ['"Segoe UI"', 'Noto Sans Ethiopic', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
