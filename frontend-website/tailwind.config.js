/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          main: 'rgb(var(--bg-main) / <alpha-value>)',
          secondary: 'rgb(var(--bg-secondary) / <alpha-value>)',
        },
        surface: 'rgb(var(--surface) / <alpha-value>)',
        purple: {
          DEFAULT: 'rgb(var(--purple) / <alpha-value>)',
          bright: 'rgb(var(--purple-bright) / <alpha-value>)',
          neon: 'rgb(var(--purple-neon) / <alpha-value>)',
        },
        gold: {
          DEFAULT: 'rgb(var(--gold) / <alpha-value>)',
          bright: 'rgb(var(--gold-bright) / <alpha-value>)',
        },
        ink: {
          main: 'rgb(var(--text-main) / <alpha-value>)',
          muted: 'rgb(var(--text-muted) / <alpha-value>)',
        },
        success: 'rgb(var(--success) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        'glow-purple': '0 0 24px 0 rgb(var(--purple-neon) / 0.35)',
        'glow-purple-lg': '0 0 48px 0 rgb(var(--purple-neon) / 0.45)',
        'glow-gold': '0 0 24px 0 rgb(var(--gold) / 0.35)',
        'glow-soft': '0 8px 32px 0 rgb(0 0 0 / 0.45)',
      },
      letterSpacing: {
        'widest-xl': '0.35em',
      },
    },
  },
  plugins: [],
}
