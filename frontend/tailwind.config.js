/** @type {import('tailwindcss').Config} */

// 现代工程风（参考 Linear / Vercel / Zed / Raycast）：Slate 灰阶基底 +
// 克制的 Teal 松石绿点缀。明暗两套的具体色值全部写在 src/index.css 的
// CSS 变量里，这里只把 token 名指向变量——换肤改 index.css 一处就够，
// 组件 className 一行都不用动。
//
// 刻意避开"廉价 AI 风"：无纯黑纯白、无大面积霓虹渐变、无高饱和发光。
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 表面层级：画布 → 侧栏 → 面板 → 卡片，一级亮一级。
        // 层级靠"面"的明度差区分，不靠粗边框。
        //
        // 每个实色都套一层 rgb(... / <alpha-value>)。这是 Tailwind v3 支持
        // 不透明度修饰符的唯一写法：`bg-app/50`、`text-danger/90` 这些类
        // 只有这样才能被生成出来。直接写 var(--c-bg) 的话，带斜杠的类会被
        // 静默丢弃，界面上的半透明边框和置灰文字会莫名消失。
        app: 'rgb(var(--c-bg) / <alpha-value>)',
        sidebar: 'rgb(var(--c-sidebar) / <alpha-value>)',
        panel: 'rgb(var(--c-panel) / <alpha-value>)',
        card: 'rgb(var(--c-card) / <alpha-value>)',
        border: 'rgb(var(--c-border) / <alpha-value>)',
        'border-strong': 'rgb(var(--c-border-strong) / <alpha-value>)',
        // 交互态填充。本身就是半透明色，直接取用
        hover: 'var(--c-hover)',
        active: 'var(--c-active)',
        soft: 'var(--c-soft)',
        'text-main': 'rgb(var(--c-text) / <alpha-value>)',
        'text-secondary': 'rgb(var(--c-text-muted) / <alpha-value>)',
        // 唯一点缀色。只给主按钮、聚焦态、当前选中项、关键数据
        accent: 'rgb(var(--c-accent) / <alpha-value>)',
        'accent-strong': 'rgb(var(--c-accent-strong) / <alpha-value>)',
        'accent-soft': 'var(--c-accent-soft)',
        'accent-line': 'var(--c-accent-line)',
        'on-accent': 'rgb(var(--c-on-accent) / <alpha-value>)',
        success: 'rgb(var(--c-success) / <alpha-value>)',
        warning: 'rgb(var(--c-warning) / <alpha-value>)',
        danger: 'rgb(var(--c-danger) / <alpha-value>)',
        // 红蓝辩论三方固定身份色
        'agent-sentiment': 'rgb(var(--c-red) / <alpha-value>)',
        'agent-trend': 'rgb(var(--c-blue) / <alpha-value>)',
        'agent-spread': 'rgb(var(--c-judge) / <alpha-value>)',
      },
      fontFamily: {
        // 系统字体优先：零加载成本，且和平台原生 UI 一致。
        // Inter/Geist 放后面兜底，需要时在 index.html 引入即可。
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto',
               'Inter', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      borderRadius: {
        // 工具属性：圆角宁小勿大。rounded-3xl 那种大圆角是消费级社交
        // 软件的语言，会让界面显得像玩具。
        'panel': '12px',
        'card': '10px',
        'input': '10px',
      },
      boxShadow: {
        // 极轻的一层阴影，只用来把浮层从背景上托起来，不做 glow
        'panel': '0 1px 2px rgba(0, 0, 0, 0.12), 0 1px 3px rgba(0, 0, 0, 0.08)',
      },
    },
  },
  plugins: [],
}
