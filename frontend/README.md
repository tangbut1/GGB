# MarketPulse Frontend — 红蓝辩论舆情分析界面

React 单页应用，展示红蓝双 Agent 辩论全过程与终裁结论。明暗双主题（Slate + Teal，左侧栏顶部切换，选择存 `localStorage` 键 `ggb-theme`）、无路由（单屏工作台），通过 SocketIO 实时接收后端流水线事件。

![React](https://img.shields.io/badge/React-18-61DAFB) ![Vite](https://img.shields.io/badge/Vite-5-646CFF) ![Tailwind](https://img.shields.io/badge/TailwindCSS-3-38BDF8)

---

## 启动

```bash
npm install
npm run dev        # http://localhost:5173
```

后端必须同时运行（默认 5050）：

```bash
cd ../MarketPulse && python app.py
```

前端通过 Vite 代理转发到后端，所以浏览器里**只需要**访问 5173。

---

## 代理契约（`vite.config.js`）

| 前缀 | 转发到 | 说明 |
|---|---|---|
| `/api/*` | `http://127.0.0.1:5050/*` | 剥掉 `/api` 前缀再转发 |
| `/socket.io/*` | `http://127.0.0.1:5050/socket.io/*` | `ws: true`，实际走长轮询 |

后端端口由 `PORT` 环境变量决定（默认 5050）。改了后端端口**必须同步改这里的 `target`**，否则前端一切请求都变成 HTML 首页，症状是控制台一片 JSON 解析失败。

---

## 目录结构

```
frontend/
├── vite.config.js           # /api 与 /socket.io 代理
├── tailwind.config.js       # 颜色 token → CSS 变量映射（rgb(var(--c-*) / <alpha-value>)）
├── index.html
└── src/
    ├── main.jsx / App.jsx   # 挂载点；全屏布局容器
    ├── theme.js             # 主题读取/切换/持久化 + useChartColors（canvas 取色）
    ├── index.css            # 两套 CSS 变量（:root 暗 / [data-theme=light] 亮）
    ├── services/
    │   └── api.js           # REST + SSE 追问客户端（fetch，无 axios）
    ├── hooks/
    │   └── useAgentSocket.js# 所有实时状态与 socket 生命周期
    └── components/
        ├── Layout/MainLayout.jsx        # 三栏布局 + 状态编排
        ├── LeftSidebar/LeftSidebar.jsx  # 历史记录、会话列表、折叠
        ├── CenterWorkspace/CenterWorkspace.jsx  # 辩论流卡片 + 输入框 + 追问
        └── RightInsightPanel/RightInsightPanel.jsx  # 终裁/趋势/情感/热词/证据
```

---

## 状态管理

没有引入路由或全局 store——`MainLayout` 持有全部应用状态（`currentTaskId` / `currentQuery` / `history` / `activeTab`），`useAgentSocket(taskId)` 负责实时状态。`zustand`、`react-router-dom`、`prop-types` 仍在 `package.json` 里但**当前未被使用**，属于历史依赖残留。

### `useAgentSocket(taskId)`

整个 socket 生命周期都在一个 `useEffect` 里，`taskId` 变化即重建连接：

```js
const { turns, followups, status, systemState, progress,
        analysisData, usage, followupStreaming, sendFollowup }
  = useAgentSocket(currentTaskId);
```

| 返回值 | 含义 |
|---|---|
| `turns` | 辩论发言流（红方/蓝方/裁判），按 `(author, round, content)` 去重 |
| `status` | `idle` / `analyzing` / `completed` / `error`，输入框的禁用开关 |
| `progress` / `systemState` | 进度条与一句话状态说明 |
| `analysisData` | 终态时后端回传的完整分析数据（右侧面板的唯一数据源） |
| `followups` / `sendFollowup` | 追问会话与流式发送 |

**后端事件 → 前端处理：**

| 后端事件 | 处理 |
|---|---|
| `connect` | emit `join`；后端回放该任务已有发言与终态 |
| `agent_update` | 更新 `systemState` 与 `progress` |
| `debate_turn` | 归一化成发言卡片（红/蓝/采集） |
| `forum_message` | 裁判事件：中期引导（`guidance`）或终裁（`verdict`，带结构化 verdict） |
| `api_usage_update` | Token 用量 |
| `task_complete` | 置终态、写 `analysisData`、进度 100% |
| `disconnect` | 给 15s 重连宽限期，超时才判 `error` |

`taskId` 置空（点"新分析"）时整体复位——否则上一场异常终止会把 `status` 永远留在 `analyzing`，输入框禁用，用户再也无法开始新分析。

---

## 关键实现约定

### 主题与配色

颜色只有一处来源：`index.css` 的 CSS 自定义属性（`:root` 是暗版，`[data-theme='light']` 是亮版）。`tailwind.config.js` 把 token 映射到这些变量，组件里一律用 `bg-card`、`text-text-secondary`、`border-border` 这类语义类，**不要写死十六进制或 `bg-white/5`**。

- 实色写成 `R G B` 三通道（`--c-accent: 20 184 166`），config 里套 `rgb(var(--c-accent) / <alpha-value>)`。Tailwind v3 对解析不了的色值会静默丢弃带 `/` 的类，不报错。
- `<canvas>` 里 Tailwind class 不生效，图表色值用 `useChartColors(theme)` 从 CSS 变量现取，`CHART_VARS` 里的驼峰键与 kebab-case 变量名要显式对上。
- 叠加色（hover / soft / grid）本身就是 `rgba()`，按原样用，不进三通道。

### 长轮询不是断线

后端是 `async_mode='threading'` + werkzeug dev server，**只有 HTTP 长轮询**。客户端在轮询切换时会周期性 `disconnect` 又立刻重连。所以：

- `disconnect` 后有 **15 秒**宽限期，只有始终没重连才置 `error`
- socket.io 的 `error` 事件是传输层抖动，**不是业务失败**——只更新提示文案，不改 `status`
- 业务失败一律由 `task_complete(status='error', message=...)` 传达，`message` 直接展示给用户

### 发言去重

后端日志广播器与 join 回放可能推同一条发言，前端用 `seenTurns` 这个 `Set` 以 `author|round|content` 为键去重。**不要**只用数组长度或时间戳判断——同一任务重连时两者都可能重复。

### 输入框的程序化写入

E2E 或任何代码里给 `<textarea>` 设值，必须走原生 setter 再派发 `input` 事件，React 的受控组件才会认：

```js
const setter = Object.getOwnPropertyDescriptor(
  window.HTMLTextAreaElement.prototype, 'value').set;
setter.call(el, text);
el.dispatchEvent(new Event('input', { bubbles: true }));
```

另：没有 `type` 属性的 `<button>` 在 DOM 里 `type === "submit"`，不能靠它定位提交按钮。

### 报告链接

`CenterWorkspace` 的报告下载按钮需要 `task_id`，由 `MainLayout` 以 `taskId` prop 注入。

---

## 右侧面板 Tab

| Tab | 内容 |
|---|---|
| 终裁 | 裁判结构化 verdict（结论、胜方、最有力论据、置信度、行动建议） |
| 趋势 | Prophet 预测曲线与走向 |
| 情感 | 情感分布饼图与平均分 |
| 热词 | 关键词与词频 |
| 证据 | 新闻列表与信源分布 |

Tab id 是 `verdict` / `trend` / `sentiment` / `keywords` / `evidence`。点击发言卡片上的"查看证据"会通过 `onSelectAgent('evidence')` 跳到证据 Tab（当前只用于这一处跳转）。

---

## 命令

```bash
npm run dev       # 开发服务器（HMR）
npm run build     # 产物构建到 dist/
npm run preview   # 本地预览构建产物
```

---

## 技术栈

React 18 · Vite 5 · TailwindCSS 3 · Chart.js 4（react-chartjs-2）· lucide-react 图标 · socket.io-client 4 · 原生 fetch（含 SSE 流式读取）
