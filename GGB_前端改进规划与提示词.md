# GGB 新版前端 — 完整改进规划与 AI 提示词手册

> 项目地址：https://github.com/tangbut1/GGB  
> 技术栈：React + Vite + Tailwind CSS + Socket.IO  
> 布局方向：三栏 Codex 风格（左侧边栏 | 中央对话区 | 右侧分析面板）

---

## 一、当前项目结构总览

```
frontend/
├── src/
│   ├── App.jsx                          # 根组件
│   ├── components/
│   │   ├── Layout/MainLayout.jsx        # 三栏布局总控
│   │   ├── LeftSidebar/LeftSidebar.jsx  # 历史记录侧边栏
│   │   ├── CenterWorkspace/CenterWorkspace.jsx  # 核心交互区
│   │   └── RightInsightPanel/RightInsightPanel.jsx  # 数据可视化面板
│   ├── hooks/useAgentSocket.js          # WebSocket 通信 Hook
│   └── services/api.js                 # API 请求封装
├── tailwind.config.js                  # Tailwind 主题配置
└── vite.config.js                      # Vite 构建配置
```

---

## 二、当前缺陷全面诊断

### 🔴 Bug 级（影响功能）

| # | 文件 | 问题描述 | 严重程度 |
|---|------|----------|----------|
| B1 | `MainLayout.jsx:22` | `setMessages([])` 在此文件中调用，但 `messages` 状态实际由 `useAgentSocket` 管理，导致 `setMessages is not defined` 运行时报错 | 🔴 崩溃 |
| B2 | `useAgentSocket.js` | 每次 `taskId` 变化都新建 socket，但旧 socket 没有等待 `disconnect` 完成就启动新连接，可能导致房间加入失败 | 🔴 数据丢失 |
| B3 | `CenterWorkspace.jsx:mode切换` | 三个模式按钮的 `clsx` 条件逻辑有 AND 短路错误，激活状态判断不正确，所有模式按钮始终显示未选中 | 🔴 逻辑错误 |
| B4 | `RightInsightPanel` Chart区 | TrendContent / SentimentContent 中图表位置只有占位文字，无实际图表渲染，`analysisData` 传入后什么都不显示 | 🔴 功能缺失 |
| B5 | `evidenceCount` | `AgentCard` 中 `evidenceCount={Math.floor(Math.random() * 20)}` 每次渲染都随机，造成闪烁和数值错乱 | 🟡 体验问题 |

### 🟡 体验级（影响观感）

| # | 文件 | 问题描述 |
|---|------|----------|
| U1 | `MainLayout.jsx` | 右侧面板 `hidden lg:flex` 在中等屏幕直接消失，没有折叠/展开按钮，用户无法手动控制 |
| U2 | `LeftSidebar.jsx` | 侧边栏折叠后只收起宽度，但没有 icon-only 模式，折叠状态没有视觉反馈 |
| U3 | `CenterWorkspace.jsx` | 输入框区域用 `absolute` 定位 + `pb-32` hack，在不同高度屏幕下可能遮挡内容，体验不稳定 |
| U4 | 全局 | 没有骨架屏（Skeleton Loader）。分析开始前/加载中状态只有一个小文字，空内容区域无任何提示 |
| U5 | `RightInsightPanel` | 4个 Tab 的内容区全部是静态占位，切换 Tab 没有过渡动画 |
| U6 | `tailwind.config.js` | 没有使用 CSS 变量（`var(--color-*)`），颜色全部硬编码在 config 里，暗色主题无法切换 |
| U7 | 全局 | 没有 `prefers-color-scheme` 响应，没有深色/浅色切换按钮 |
| U8 | `CenterWorkspace` | 快捷 Tag 点击（`@引用上一轮结论` 等）使用字符串拼接插入输入框，没有实际关联任何功能逻辑 |
| U9 | `useAgentSocket.js` | `error` 事件只更新 `systemState`，没有在 UI 中显示错误面板/Alert，用户不知道发生了什么 |

### 🟢 架构级（影响长期维护）

| # | 问题描述 |
|---|----------|
| A1 | 没有全局状态管理（Zustand/Context），所有状态都通过 props 层层传递，未来加字段要改很多地方 |
| A2 | `api.js` 没有统一的 error interceptor，每个地方单独 `try/catch` |
| A3 | 没有 `pages/` 目录，所有功能都在一个 App 里，将来加"历史记录页""设置页"会很乱 |
| A4 | Tailwind 配置里直接用十六进制颜色，导致深色主题切换需要改 config 重新构建 |
| A5 | 没有组件级 `PropTypes` 或 TypeScript，协作和自动补全体验差 |

---

## 三、分阶段改进路线图

### 阶段一：修复所有 Bug（1-2 天）
优先级最高，确保基本功能可用。

- [ ] 修复 B1：从 `MainLayout` 移除 `setMessages([])`，在 `useAgentSocket` 中实现消息重置
- [ ] 修复 B2：在 `useAgentSocket` 的 `useEffect` cleanup 中正确等待 socket 断开
- [ ] 修复 B3：重写 `CenterWorkspace` 中模式切换按钮的 `clsx` 条件
- [ ] 修复 B4：接入 Chart.js，在 TrendContent 和 SentimentContent 中渲染真实图表
- [ ] 修复 B5：将 `evidenceCount` 改为从后端数据读取，或存入 state 避免重渲染

### 阶段二：体验完善（3-5 天）
让界面达到"可展示"的水准。

- [ ] 实现右侧面板响应式折叠/展开按钮（U1）
- [ ] 实现左侧边栏 icon-only 折叠模式（U2）
- [ ] 将输入框改为 `sticky bottom-0` 布局（U3）
- [ ] 添加骨架屏（U4）
- [ ] 添加 Tab 切换过渡动画（U5）
- [ ] 添加全局错误提示 Alert 组件（U9）

### 阶段三：架构升级（1 周）
提升代码质量，为后续功能扩展打基础。

- [ ] 引入 Zustand 进行全局状态管理（A1）
- [ ] 将 Tailwind 颜色迁移为 CSS 变量 + 深色主题支持（A4/U6/U7）
- [ ] 统一 API 层错误处理（A2）
- [ ] 添加 `react-router-dom` 实现多页路由（A3）
- [ ] 迁移至 TypeScript（可选，A5）

### 阶段四：功能扩展（长期）
添加缺失的核心功能。

- [ ] 右侧面板接入真实 Chart.js 图表：热度趋势折线图、情感饼图
- [ ] 热词词云（react-wordcloud 或 D3.js）
- [ ] 左侧边栏历史记录持久化（localStorage 或后端 API）
- [ ] 分析报告导出 PDF 功能
- [ ] 追问功能（followup）与上下文关联

---

## 四、AI 提示词（直接发给 DeepSeek/Claude）

每个提示词都是独立的，按阶段顺序使用。将代码粘贴到 `[...]` 位置后直接发送。

---

### 提示词 #1：修复 MainLayout 状态管理崩溃（B1）

```
你是一位 React 专家，请帮我修复以下代码中的一个运行时 Bug。

**问题描述：**
在 `MainLayout.jsx` 的 `handleStartAnalysis` 函数中，直接调用了 `setMessages([])`，但 `messages` 状态是由 `useAgentSocket` Hook 管理的，`setMessages` 根本不存在于 `MainLayout` 的作用域内，会导致 `ReferenceError: setMessages is not defined`。

**要求：**
1. 在 `useAgentSocket.js` 中，当 `taskId` 发生变化时，自动重置 `messages` 为空数组
2. 在 `MainLayout.jsx` 中移除 `setMessages([])` 这一行
3. 修改后的代码要确保：每次开始新分析时，旧的消息列表会被清空
4. 不要改变任何其他逻辑，只修复这一个 Bug
5. 给出修改后的完整文件内容

**当前 `useAgentSocket.js` 代码：**
[粘贴 useAgentSocket.js 完整内容]

**当前 `MainLayout.jsx` 代码：**
[粘贴 MainLayout.jsx 完整内容]
```

---

### 提示词 #2：修复模式切换按钮高亮逻辑（B3）

```
你是一位 React 专家，请帮我修复 CenterWorkspace.jsx 中模式切换按钮的高亮逻辑 Bug。

**问题描述：**
当前的 clsx 条件表达式存在运算符优先级错误，导致三个模式按钮（快速思考、深度思考、多 Agent 辩论）无论点击哪个，视觉上都不会正确高亮显示当前选中的模式。

当前错误代码段（仅供参考）：
```jsx
(mode === 'multi-agent' && m === '多 Agent 辩论') || (mode !== 'multi-agent' && m !== '多 Agent 辩论') && m === '快速思考'
```

**要求：**
1. 将模式用一个清晰的映射对象表示，例如：
   `const modeMap = { '快速思考': 'fast', '深度思考': 'deep', '多 Agent 辩论': 'multi-agent' }`
2. 重写按钮渲染逻辑，使点击哪个按钮就高亮哪个，逻辑清晰易读
3. 保留原有的 `setMode` 状态切换功能
4. 给出修改后的完整 `CenterWorkspace.jsx` 文件

**当前完整代码：**
[粘贴 CenterWorkspace.jsx 完整内容]
```

---

### 提示词 #3：接入 Chart.js 实现趋势图和情感饼图（B4）

```
你是一位 React + Chart.js 专家，请帮我在 `RightInsightPanel.jsx` 中接入真实的图表。

**当前问题：**
TrendContent 和 SentimentContent 组件内只有占位文字，没有实际渲染图表。

**要求：**
1. 使用 `react-chartjs-2` 库（需要在 package.json 中添加依赖）
2. 在 TrendContent 中：
   - 接入 Line 折线图组件
   - X 轴为时间（从 data.trend_data 数组中读取，字段为 `time` 和 `value`）
   - 如果 data 为 null，显示骨架屏（灰色矩形占位，带 shimmer 动画）
3. 在 SentimentContent 中：
   - 接入 Doughnut 环形图组件
   - 数据来自 `data.positive_pct`, `data.negative_pct`, `data.neutral_pct`
   - 颜色：正面用 `#22C55E`，负面用 `#EF4444`，中性用 `#98A2B3`
   - 如果 data 为 null，显示骨架屏
4. 图表样式要匹配项目的深色主题（背景 `#1C2129`，网格线 `#2A303A`，文字 `#98A2B3`）
5. 给出修改后的完整 `RightInsightPanel.jsx` 文件

**骨架屏 CSS 参考：**
```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, #1C2129 25%, #2A303A 50%, #1C2129 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 8px;
}
```

**当前完整代码：**
[粘贴 RightInsightPanel.jsx 完整内容]
```

---

### 提示词 #4：右侧面板响应式折叠功能（U1）

```
你是一位 React 专家，请帮我给 GGB 项目的三栏布局添加右侧面板的折叠/展开功能。

**当前问题：**
右侧 `RightInsightPanel` 在 `lg` 断点以下直接隐藏（`hidden lg:flex`），用户无法手动控制。

**要求：**
1. 在 `MainLayout.jsx` 中添加 `rightPanelOpen` 状态，默认值在桌面端为 `true`，移动端为 `false`
2. 在中央工作区的头部（TopBar）右侧添加一个切换按钮，点击时控制右侧面板的显示/隐藏
   - 图标：面板打开时用 `PanelRightClose`，关闭时用 `PanelRight`（来自 lucide-react）
3. 右侧面板的展开/收起要有 CSS transition 动画（宽度从 0 过渡到 360px），持续时间 280ms，缓动函数 `cubic-bezier(0.16, 1, 0.3, 1)`
4. 中央工作区宽度要随右侧面板的开关状态自动调整（flex-1 即可）
5. 修改后右侧面板的 `hidden lg:flex` 要移除，改为受状态控制
6. 给出修改后的完整 `MainLayout.jsx` 文件

**当前完整代码：**
[粘贴 MainLayout.jsx 完整内容]
```

---

### 提示词 #5：左侧边栏 icon-only 折叠模式（U2）

```
你是一位 React + Tailwind 专家，请帮我完善 LeftSidebar.jsx 的折叠功能。

**当前问题：**
侧边栏折叠后只是宽度收起，没有 icon-only 模式，折叠状态下内容直接消失，体验很差。

**要求：**
1. 折叠状态（`collapsed=true`）下：
   - 侧边栏宽度从 240px 变为 60px，有过渡动画
   - 只显示每个功能入口的图标，不显示文字
   - Logo 区域只显示简化图标
   - 所有文字用 `overflow-hidden opacity-0` 隐藏，不要用 `display:none`（保留空间让宽度动画顺滑）
2. 展开状态下完整显示图标 + 文字
3. 折叠/展开按钮本身始终可见（放在侧边栏底部或顶部）
4. 给出修改后的完整 `LeftSidebar.jsx` 文件，如果目前文件里没有图标，从 lucide-react 添加合适的图标

**当前完整代码：**
[粘贴 LeftSidebar.jsx 完整内容]
```

---

### 提示词 #6：输入框布局修复（U3）

```
你是一位 React + CSS 专家，请帮我修复 CenterWorkspace.jsx 中输入框区域的布局问题。

**当前问题：**
输入框使用 `position: absolute; bottom: 0` + 内容区 `pb-32` 的 hack 方式，在不同高度的屏幕上容易出现内容被遮挡或滚动不到底的问题。

**要求：**
1. 将整个 CenterWorkspace 改为标准的 flex 列布局：
   - 顶部 TopBar：`shrink-0`
   - 中间消息列表区：`flex-1 overflow-y-auto`
   - 底部输入框区：`shrink-0`，不再用 absolute 定位
2. 底部输入框区域的渐变背景效果可以用 `box-shadow: inset 0 30px 30px -30px <bg-color>` 实现，不需要 absolute 伪元素
3. 确保消息列表的最后一条消息不会被输入框遮住（标准 flex 布局自然解决）
4. 不要改变任何视觉样式，只改布局结构
5. 给出修改后的完整 `CenterWorkspace.jsx` 文件

**当前完整代码：**
[粘贴 CenterWorkspace.jsx 完整内容]
```

---

### 提示词 #7：添加全局错误 Alert 组件（U9）

```
你是一位 React 专家，请帮我给 GGB 项目添加一个全局错误提示组件。

**当前问题：**
`useAgentSocket.js` 的 `error` 事件只更新 `systemState` 文字，没有可见的错误面板，用户不知道发生了错误。

**要求：**
1. 创建一个新文件 `src/components/UI/Alert.jsx`，实现一个 Toast 提示组件：
   - 出现在屏幕右上角
   - 有三种类型：`error`（红色）、`warning`（黄色）、`success`（绿色）
   - 自动在 5 秒后消失，也可以手动点击关闭
   - 出现/消失有 `translateY` + `opacity` 动画，持续 200ms
2. 在 `useAgentSocket.js` 中，当 socket 触发 `error` 事件时，通过一个全局事件总线（`window.dispatchEvent(new CustomEvent('app:toast', { detail: { type: 'error', message: data.message } }))`）发出通知
3. 在 `App.jsx` 中监听 `app:toast` 事件并渲染 Alert 组件
4. 给出以下三个文件的完整代码：
   - `src/components/UI/Alert.jsx`（新建）
   - `src/hooks/useAgentSocket.js`（修改）
   - `src/App.jsx`（修改）

**项目配色（Tailwind 类名）：**
- 背景：`bg-panel`（`#171A20`）
- 边框：`border-border`（`#2A303A`）
- 错误：`bg-danger/10 border-danger/30 text-danger`
- 成功：`bg-success/10 border-success/30 text-success`
- 警告：`bg-warning/10 border-warning/30 text-warning`

**当前相关文件：**
App.jsx：[粘贴内容]
useAgentSocket.js：[粘贴内容]
```

---

### 提示词 #8：引入 Zustand 全局状态管理（A1）

```
你是一位 React 架构专家，请帮我将 GGB 项目的状态管理迁移到 Zustand。

**当前问题：**
所有状态（taskId、messages、status、analysisData 等）都在 `MainLayout.jsx` 中通过 props 层层传递，未来添加功能时维护成本很高。

**要求：**
1. 安装 `zustand`
2. 创建 `src/store/analysisStore.js`，将以下状态集中管理：
   - `currentTaskId` / `setCurrentTaskId`
   - `currentQuery` / `setCurrentQuery`
   - `messages` / `addMessage` / `resetMessages`
   - `status` / `setStatus`（idle | analyzing | completed | error）
   - `systemState` / `setSystemState`
   - `analysisData` / `setAnalysisData`
   - `activeTab` / `setActiveTab`（trend | sentiment | keywords | evidence）
   - `sidebarCollapsed` / `toggleSidebar`
3. 修改 `useAgentSocket.js`：从 store 读取 `taskId`，直接调用 store actions 更新状态，不再通过 return 值传递
4. 修改 `MainLayout.jsx`：移除 props drilling，改为各子组件直接从 store 读取所需状态
5. 修改 `CenterWorkspace.jsx` 和 `RightInsightPanel.jsx`：直接从 store 读取，不再需要从 props 接收
6. 给出所有修改文件的完整代码

**当前各文件代码：**
MainLayout.jsx：[粘贴]
useAgentSocket.js：[粘贴]
CenterWorkspace.jsx：[粘贴]
RightInsightPanel.jsx：[粘贴]
```

---

### 提示词 #9：Tailwind 深色主题 CSS 变量化（A4/U6/U7）

```
你是一位前端样式专家，请帮我将 GGB 项目的 Tailwind 颜色系统迁移到 CSS 变量，并支持深色/浅色主题切换。

**当前问题：**
1. `tailwind.config.js` 中所有颜色都是硬编码的十六进制值
2. 没有主题切换功能
3. 只有一个深色主题

**要求：**
1. 在 `src/index.css` 中定义 CSS 变量：
   - `[data-theme="dark"]`（当前深色配色保持不变）：
     `--color-app: #0F1115; --color-sidebar: #13161B; --color-panel: #171A20; --color-card: #1C2129; --color-border: #2A303A; --color-text-main: #E8ECF2; --color-text-secondary: #98A2B3; --color-accent: #3B82F6;`
   - `[data-theme="light"]`（设计浅色版本）：
     `--color-app: #F5F6F8; --color-sidebar: #ECEEF2; --color-panel: #FFFFFF; --color-card: #F8F9FB; --color-border: #E2E6ED; --color-text-main: #1A1D23; --color-text-secondary: #6B7280; --color-accent: #2563EB;`
2. 修改 `tailwind.config.js`，将所有颜色改为引用 CSS 变量：
   `app: 'var(--color-app)'`, `sidebar: 'var(--color-sidebar)'` 等
3. 在 `App.jsx` 中：
   - 读取 `window.matchMedia('(prefers-color-scheme: dark)')` 设置初始主题
   - 在 `<html>` 元素上设置 `data-theme` 属性
   - 提供一个切换函数，存入 Context 或 Zustand store
4. 在 `LeftSidebar.jsx` 底部添加一个主题切换按钮（太阳/月亮图标，来自 lucide-react）
5. 给出所有修改文件的完整代码

**当前相关文件：**
tailwind.config.js：[粘贴]
src/index.css：[粘贴]
App.jsx：[粘贴]
LeftSidebar.jsx：[粘贴]
```

---

### 提示词 #10：热词词云组件（阶段四功能）

```
你是一位 React 数据可视化专家，请帮我在 GGB 项目的 RightInsightPanel 中实现热词词云。

**要求：**
1. 使用 `react-wordcloud` 库（需要添加依赖）
2. 修改 `RightInsightPanel.jsx` 中的 `KeywordContent` 组件：
   - 接收 `data.keywords` 数组（格式：`[{ text: "关键词", value: 数量 }]`）
   - 使用 `react-wordcloud` 渲染词云
   - 词云高度 280px，不要超出容器
   - 颜色随机从以下调色板中选取：`['#60A5FA', '#A78BFA', '#34D399', '#F87171', '#FBBF24']`
   - 字体大小范围：14px ~ 56px
   - 如果 `data` 为 null，显示骨架屏（5行随机宽度的灰色矩形条）
3. 词云中文字点击时，将该关键词填入中央工作区的输入框（通过 Zustand store 实现）
4. 给出修改后的完整 `RightInsightPanel.jsx` 和需要新建/修改的 store 文件

**项目深色主题背景色：** `#1C2129`

**当前 RightInsightPanel.jsx：**
[粘贴完整内容]
```

---

## 五、使用这些提示词的注意事项

1. **按顺序执行**：阶段一 Bug 修复要在阶段二体验优化之前完成，否则后者的改动可能被前者覆盖
2. **每次只改一个问题**：不要把多个提示词合并成一个发给 AI，否则改动范围太大容易出现新 Bug
3. **改完立即测试**：每个提示词对应的修改完成后，先运行 `npm run dev` 确认没有新报错，再进行下一步
4. **粘贴代码时保留缩进**：将代码粘贴到提示词的 `[...]` 位置时，直接复制 GitHub 上的原始内容，不要手动改格式
5. **如果 AI 给出的代码有问题**：把错误信息加在提示词末尾，继续追问"按上面的要求，我运行后出现了这个错误：[错误内容]，请修复"

---

*文档生成日期：2026-06-20 | 基于 tangbut1/GGB 仓库 main 分支最新代码*
