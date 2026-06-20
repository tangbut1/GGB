/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        app: '#0F1115',
        sidebar: '#13161B',
        panel: '#171A20',
        card: '#1C2129',
        border: '#2A303A',
        'text-main': '#E8ECF2',
        'text-secondary': '#98A2B3',
        accent: '#3B82F6',
        success: '#22C55E',
        warning: '#F59E0B',
        danger: '#EF4444',
        'agent-trend': '#60A5FA',
        'agent-sentiment': '#A78BFA',
        'agent-spread': '#34D399',
        'agent-skeptic': '#F87171',
      },
      fontFamily: {
        sans: ['PingFang SC', 'MiSans', 'HarmonyOS Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'panel': '16px',
        'card': '14px',
        'input': '18px',
      }
    },
  },
  plugins: [],
}
