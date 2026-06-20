/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        app: 'var(--color-app)',
        sidebar: 'var(--color-sidebar)',
        panel: 'var(--color-panel)',
        card: 'var(--color-card)',
        border: 'var(--color-border)',
        'text-main': 'var(--color-text-main)',
        'text-secondary': 'var(--color-text-secondary)',
        accent: 'var(--color-accent)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        danger: 'var(--color-danger)',
        'agent-trend': 'var(--color-agent-trend)',
        'agent-sentiment': 'var(--color-agent-sentiment)',
        'agent-spread': 'var(--color-agent-spread)',
        'agent-skeptic': 'var(--color-agent-skeptic)',
      },
      fontFamily: {
        sans: ['PingFang SC', 'MiSans', 'HarmonyOS Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'panel': '16px',
        'card': '14px',
        'input': '18px',
      },
      transitionDuration: {
        '280': '280ms',
      },
      transitionTimingFunction: {
        'apple': 'cubic-bezier(0.16, 1, 0.3, 1)',
      }
    },
  },
  plugins: [],
}
