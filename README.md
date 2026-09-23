# MarketPulse v4 — 红蓝辩论式多智能体舆情分析系统

基于 BettaFish 架构理念升级的多智能体协作系统。用户输入关键词后，系统采集多源新闻，让两个立场对立的 Agent 围绕**同一批数据**展开两轮辩论，最后由裁判 Agent 输出结构化终裁。

- **红方** = `SentimentAgent`（危机分析师，看空、放大风险）
- **蓝方** = `TrendAgent`（理性分析师，看多、寻找破局点）
- **裁判** = `LLMHost`（中期引导 + 结构化终裁）

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/framework-Flask-green)
![React](https://img.shields.io/badge/frontend-React_18-61dafb)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 架构流程

```
用户输入关键词
      │
      ▼
┌─────────────┐   ┌──────────────────────────────────────────────┐
│  React 前端  │   │              Flask 后端 (:5050)               │
│  (:5173)    │◄──┤  SocketIO 实时推送 debate_turn / task_complete │
└─────────────┘   └──────────────────┬───────────────────────────┘
                                      │
                                      ▼
                          OrchestratorAgent.stream_pipeline()
                                      │
      ┌───────────────┬──────────────┼──────────────┬──────────────┐
      ▼               ▼              ▼              ▼              ▼
  CollectAgent   SentimentAgent  TrendAgent      LLMHost       ReportAgent
  多源采集+补充词   红方·立论/反驳   蓝方·立论/反驳   裁判·引导/终裁   定稿+HTML
      │               │              │              │              │
      └───────────────┴──────────────┴──────────────┘              │
                              │                                    │
                              ▼                                    ▼
                    logs/forum_{task_id}.log              results/reports/
```

### 辩论流程

| 阶段 | 内容 |
|---|---|
| Collect | 多源采集（Google RSS → DDG → Bing）+ 差异化补充词，受 `MP_SEARCH_BUDGET` 总预算约束 |
| Round 1 立论 | 红方基于 SnowNLP 实测分布立论，蓝方基于 Prophet 时序立论 |
| 裁判引导 | LLMHost 总结分歧、指出盲区（LLM 不可用时无引导继续，不中断） |
| Round 2 反驳 | 红方点名驳斥蓝方具体数据，蓝方点名驳斥红方具体数据 |
| 终裁 | 裁判输出结构化 verdict：立场 / 置信度 / 核心分歧 / 双方最有力论据 / 行动建议 |
| 报告 | ReportAgent 定稿，生成独立 HTML 报告 |

- Trend 失败**非致命**，注入降级摘要让下游继续。
- 采集不到真实结果时 CollectAgent 直接报错，**不注入假数据**。

---

## 核心特性

- **真辩论，不是轮流发言**：两轮立论 + 反驳，第二轮必须点名回应对方上一轮的具体数据
- **降级不失声**：没有 API Key 时红蓝双方仍基于本地算法（SnowNLP / Prophet）的实测值发言，裁判输出启发式终裁（置信度 0.4），不会变成单方陈述
- **6 Agent 解耦**：采集、情感、趋势、报告、裁判各自独立 LLM 配置，另有阶跃星辰 Agent 做追问上下文补全
- **信源可信度分级**：每条数据按域名后缀归入 T1-T4，情绪分布按层级分开统计——把自媒体推文和央媒快讯算成同一个样本，正负比例就没有解释力
- **SSRF 防护**：所有外发请求统一校验协议白名单、禁止内嵌凭证、DNS 结果不得落在环回/私有/CGNAT/保留段，采集器和 LLM 端点共用同一套判据
- **采集预算**：整个采集阶段有总时间预算（默认 150s），配合 socket 级兜底超时与数据源熔断，避免界面长时间停在"分析中"
- **模型异构**：config.yaml + .env 支持每个 Agent 配置不同的大模型（OpenAI 兼容接口），也可通过全局变量一键切换
- **可复现的算法输出**：情感带 Wilson 95% 置信区间、趋势标注模型类型与降级原因、热词用真实 TF-IDF 权重；拿不到数据时明确说明而不是画个假的
- **追问引发复辩**：追问不是"让一个模型再答一遍"，而是红蓝双方就追问各自复辩、裁判出补充裁定，轮次从 3 开始
- **实时推流**：Flask-SocketIO 推送辩论发言与进度
- **断线可恢复**：长轮询模式下客户端周期性掉线，重新 join 时会完整回放该任务已有状态
- **交互式导出**：生成含 Chart.js + vis-network 的独立 HTML 报告

---

## 快速启动

系统是**两个进程**，需同时启动。

### 1. 克隆项目

```bash
git clone https://github.com/tangbut1/GGB.git
cd GGB
```

### 2. 安装依赖

```bash
pip install -r MarketPulse/requirements.txt
cd frontend && npm install && cd ..
```

### 3. 配置 API Key

```bash
cp MarketPulse/.env.example MarketPulse/.env
```

编辑 `MarketPulse/.env`，把 6 个 Agent 的 `sk-xxx` 替换成真实 Key：

```bash
MP_COLLECT_AGENT_API_KEY=sk-your-real-key     # 采集
MP_SENTIMENT_AGENT_API_KEY=sk-your-real-key   # 情感（红方）
MP_TREND_AGENT_API_KEY=sk-your-real-key       # 趋势（蓝方）
MP_REPORT_AGENT_API_KEY=sk-your-real-key      # 报告
MP_FORUM_HOST_API_KEY=sk-your-real-key        # 裁判
MP_STEPFUN_AGENT_API_KEY=sk-your-real-key     # 阶跃星辰（可选，追问上下文补全）
```

> **没有 Key 也能跑**：系统进入降级模式，红蓝双方用本地算法发言，裁判给启发式终裁。适合先看界面和流程。
>
> **StepFun Agent 不是硬依赖**：未配置时自动回落到 deepseek 路径，只影响追问上下文补全的质量，不影响辩论本身。它跑 `step-5-preview`，长上下文和 reasoning 能力适合读完整论坛记录。

**全局一键切换模型**（可选）：

```bash
MP_GLOBAL_BASE_URL=https://api.openai.com/v1
MP_GLOBAL_MODEL=gpt-4o
```

也可以针对单个 Agent 精准覆盖：

```bash
MP_SENTIMENT_AGENT_MODEL=deepseek-v4-pro      # 仅情感分析用 Pro 模型
MP_TREND_AGENT_BASE_URL=https://api.openai.com/v1  # 仅趋势预测换接口
```

### 4. 启动服务

```bash
# 终端 1：后端
cd MarketPulse && python app.py

# 终端 2：前端
cd frontend && npm run dev
```

浏览器打开 **http://localhost:5173/**。

后端默认端口 5050，可用 `PORT` 覆盖；**改端口必须同步改 `frontend/vite.config.js` 里的 proxy target**，否则前端连不上。

---

## 配置体系

### 覆盖优先级（由高到低）

```
环境变量单 Agent 覆盖 (MP_COLLECT_AGENT_MODEL)
  → 环境变量全局覆盖 (MP_GLOBAL_MODEL)
    → config.yaml 默认值
```

### 采集相关环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MP_SEARCH_TIMEOUT` | 15 | 单次搜索请求超时（秒），同时设为 socket 级兜底 |
| `MP_SEARCH_BUDGET` | 150 | **整个采集阶段**总预算（秒）。一次采集会调主搜索 + 多个补充词，超预算就带着已有结果进入分析 |
| `PORT` | 5050 | 后端监听端口，改后需同步 `frontend/vite.config.js` 的代理 target |
| `MP_TASK_STORE_DIR` | `MarketPulse/data/tasks` | 任务注册表目录，覆盖后历史记录会读写指定位置 |
| `MP_ALLOW_PRIVATE_LLM_ENDPOINTS` | 关 | 设为 `1` 时允许 LLM 端点指向内网（Ollama/vLLM 跑在 127.0.0.1 的场景）。**采集器抓取的第三方 URL 不受此开关影响，一律拦截** |

### config.yaml 关键配置

```yaml
agent_llm:
  collect_agent:
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-v4-flash"
  # ... 其余 Agent 同理

analysis:
  use_prophet: true        # Prophet 时序预测
  forecast_periods: 30     # 默认预测 30 天

collect:
  max_results:
    social: 500
    news: 300
  min_results:
    social: 300
    news: 200
```

### 环境变量完整列表

| 变量 | 说明 |
|---|---|
| `MP_COLLECT_AGENT_API_KEY` | 采集 Agent API Key |
| `MP_SENTIMENT_AGENT_API_KEY` | 情感（红方）Agent API Key |
| `MP_TREND_AGENT_API_KEY` | 趋势（蓝方）Agent API Key |
| `MP_REPORT_AGENT_API_KEY` | 报告 Agent API Key |
| `MP_FORUM_HOST_API_KEY` | 裁判 Agent API Key |
| `MP_STEPFUN_AGENT_API_KEY` | 阶跃星辰 Agent API Key（可选，不配则回落到 deepseek） |
| `MP_GLOBAL_BASE_URL` | 全局 API 地址覆盖 |
| `MP_GLOBAL_MODEL` | 全局模型名覆盖 |
| `MP_{AGENT}_MODEL` | 单 Agent 模型覆盖（如 `MP_SENTIMENT_AGENT_MODEL`） |
| `MP_{AGENT}_BASE_URL` | 单 Agent API 地址覆盖 |
| `MP_SEARCH_TIMEOUT` | 单次搜索超时（秒） |
| `MP_SEARCH_BUDGET` | 采集阶段总预算（秒） |
| `MP_ALLOW_PRIVATE_LLM_ENDPOINTS` | 设为 `1` 允许 LLM 端点指向内网（本地 vLLM/Ollama）。**不影响采集器抓取的第三方 URL** |
| `PORT` | 后端监听端口，默认 5050 |
| `SECRET_KEY` | Flask Session 密钥 |
| `NEWSAPI_KEY` | 备用 NewsAPI 源（可选） |

---

## 界面说明

React 单页应用，三栏布局。配色为 **Slate + Teal**（参考 Linear / Vercel / Zed 一类开发工具，不用纯黑纯白、不做大面积霓虹渐变，靠 1px 细边框和结构化留白分栏），**明暗双主题**可切换，选择记在 `localStorage` 的 `ggb-theme`：

| 区域 | 内容 |
|---|---|
| 左侧栏 | 品牌标识、新建分析按钮、分析记录（点击重跑该关键词）、分析模板、系统能力说明。宽度可拖拽（64-520px），双击复位，也可完全折叠 |
| 中栏 | 红蓝辩论卡片流（红方/蓝方/裁判三色区分，含轮次标记；第 3 轮起带"追问复辩"标记）、底部输入框可持续追问 |
| 右栏 | 五个 Tab：**终裁**（立场/置信度/核心分歧/双方最有力论据/行动建议 + 样本口径）、**趋势**（方向/置信度/预测窗口/模型类型）、**情感**（正负中性分布/均分/Wilson 置信区间）、**热词**（真实 TF-IDF 权重）、**证据**（按信源分级 T1-T4 分组）。宽度可拖拽（320-720px），可完全折叠 |

左右侧栏折叠后中栏自动占满，适合专注读辩论。

### 配色（`frontend/src/index.css`）

唯一来源是 `index.css` 里的 CSS 自定义属性，`tailwind.config.js` 只做 token 映射，组件里不写死色值：

| 用途 | 暗版 | 亮版 |
|---|---|---|
| 画布底色 | `#0B0F17` | `#F8FAFC` |
| 侧栏 / 卡片表面 | `#111827` / `#182231` | `#FFFFFF` |
| 分割线 | `#1E293B` | `#E2E8F0` |
| 主文本 | `#F1F5F9` | `#0F172A` |
| 次文本 | `#94A3B8` | `#64748B` |
| 强调色（Teal） | `#14B8A6` | `#0D9488` |

红蓝辩论三色（红 `#F87171` / 蓝 `#60A5FA` / 裁判 `#FBBF24`，亮版对应 `#DC2626` / `#2563EB` / `#B45309`）也走同一套变量，亮暗切换时整套界面包括图表一起换。

两条容易踩的坑，改配色前先看：

1. **实色必须写成 `R G B` 三通道**（`--c-accent: 20 184 166`），且 `tailwind.config.js` 里套一层 `rgb(var(--c-accent) / <alpha-value>)`。Tailwind v3 对解析不了的色值会**静默丢弃**带不透明度修饰符的类——`bg-accent/10`、`border-danger/25`、`text-text-secondary/30` 不报错，也不生成 CSS，界面上半透明徽章、淡边框、置灰文字会成片消失。本身就是 `rgba()` 的叠加色（hover、soft、grid）不需要，它们只以原样使用。
2. **CSS 自定义属性名大小写敏感**。`frontend/src/theme.js` 的 `CHART_VARS` 用 `[jsKey, cssName]` 显式把驼峰键对上 kebab-case 变量（`tooltipBg` → `--c-tooltip-bg`）。拼错时 `getPropertyValue` 只返回空字符串、不报错，图表颜色会静默变成非法值。

---

## API 端点

后端路由**不带** `/api` 前缀；`/api/...` 是浏览器侧经过 Vite 代理后的路径。直接 curl 后端（5050）用左列，前端代码里用右列。

| 后端路由（:5050） | 前端路径（:5173） | 方法 | 说明 |
|---|---|---|---|
| `/` | `/` | GET | 旧版 vanilla-JS 单页应用（`templates/index.html`） |
| `/analyze` | `/api/analyze` | POST | 提交分析任务，返回 `{task_id}` |
| `/history` | `/api/history` | GET | 最近 50 条任务历史 |
| `/history/<task_id>` | `/api/history/<task_id>` | GET | 单条任务详情 |
| `/report/<task_id>` | `/api/report/<task_id>` | GET | 下载 HTML 报告 |
| `/status` | `/api/status` | GET | 各 Agent 配置状态 |
| `/followup` | `/api/followup` | POST | SSE 流式追问（单模型读结论后回答，快） |
| `/debate_followup` | `/api/debate_followup` | POST | 追问触发新一轮红蓝辩论（红蓝各自复辩 + 裁判补充裁定） |
| `/stream/<task_id>` | `/api/stream/<task_id>` | GET | SSE 实时日志流 |

### `/analyze` 请求体

```json
{
  "keyword": "华为",
  "mode": "multi-agent",
  "srcMode": "news",
  "platforms": ["微博", "小红书", "抖音"],
  "local_data": [],
  "local_data_raw_files": []
}
```

`keyword` 必填；`srcMode` 可选 `news` / `social`，默认 `news`。

### `/debate_followup` 请求体

```json
{"task_id": "task_1737000000_a1b2c3", "query": "蓝方的数据依据是什么？"}
```

红蓝双方的复辩发言**不走这个 HTTP 响应回传**，而是通过 SocketIO 的 `debate_turn` / `forum_message` 实时推送，界面能和首轮辩论一样一条条冒出来。HTTP 响应只回 `{turns, verdict}`，终裁更新另发 `verdict_update` 事件。

追问要求任务已到终态（`completed` / `error`），否则返回 409。复辩**不重新采集**，复用首轮数据，轮次从 3 开始。

### SocketIO 事件

前端通过 `/socket.io` 连接，先 `join` 任务房间：

| 事件 | 方向 | 说明 |
|---|---|---|
| `join` | C→S | 加入任务房间，服务端回放该任务已有的辩论发言与终态 |
| `debate_turn` | S→C | 一条辩论发言（红方/蓝方/裁判） |
| `forum_message` | S→C | 论坛消息 |
| `agent_update` | S→C | Agent 状态与进度 |
| `task_complete` | S→C | 终态（`completed` / `error`），携带 `analysis_data` |
| `verdict_update` | S→C | 追问复辩后终裁更新 |
| `api_usage_update` | S→C | Token 用量统计 |

> 传输只有 HTTP 长轮询（`async_mode='threading'`）。客户端会在轮询切换时周期性掉线又立刻重连，这是正常现象；前端给 15 秒重连宽限期，只有始终没重连才标记中断。

---

## 项目结构

```
GGB/
├── README.md                   # 本文件
├── AGENTS.md / CLAUDE.md       # 给编码代理的项目说明
├── MarketPulse/
│   ├── app.py                  # Flask 主控 + SocketIO + 任务线程
│   ├── main.py                 # Streamlit 独立 Agent 测试入口（不走辩论）
│   ├── requirements.txt
│   ├── start.bat
│   ├── .env.example
│   ├── README.md
│   ├── templates/index.html    # 旧版 vanilla-JS 界面（仍可访问，非当前产品界面）
│   ├── src/
│   │   ├── config.yaml         # LLM 配置 + 采集量 + 分析参数
│   │   ├── config.py           # 统一配置解析（${ENV_VAR} 展开）
│   │   ├── events.py           # PipelineEvent / ForumEvent / ReportEvent / ErrorEvent
│   │   ├── net_safety.py       # SSRF 防护：协议白名单 + 内网地址黑名单（采集器与 LLM 端点共用）
│   │   ├── agents/
│   │   │   ├── base_agent.py       # Agent 基类（call_llm + llm_unavailable + extract_opponent_claim）
│   │   │   ├── collect_agent.py    # 数据采集（多源搜索 + 本地数据融合 + 信源分级）
│   │   │   ├── sentiment_agent.py  # 情感分析（红方：SnowNLP + LLM 校正 + 降级立论合成）
│   │   │   ├── trend_agent.py      # 趋势预测（蓝方：Prophet + 数据质量评级）
│   │   │   ├── report_agent.py     # 报告生成 + AI 解读 + 辩论卡片提取 + TF-IDF 权重
│   │   │   ├── stepfun_agent.py    # 阶跃星辰 Agent（追问上下文补全，非硬依赖）
│   │   │   └── orchestrator.py     # 红蓝辩论流水线调度 + 追问复辩
│   │   ├── collect/
│   │   │   ├── custom_search.py    # 多源搜索 + 预算/熔断/Bing UI 链接过滤 + 逐跳 SSRF 校验
│   │   │   ├── source_registry.py  # 信源可信度分级 T1-T4（按域名后缀匹配）
│   │   │   ├── ingest_cache.py
│   │   │   ├── news_collector.py
│   │   │   ├── providers.py
│   │   │   └── sentiment_api.py
│   │   ├── analysis/
│   │   │   ├── sentiment_analysis.py  # SnowNLP + TextBlob + 词典融合打分
│   │   │   └── trend_prediction.py    # Prophet 时序预测（含 Windows TBB 路径修正）
│   │   ├── forum/
│   │   │   ├── log_manager.py      # forum log 读写 + 线程安全
│   │   │   ├── monitor.py          # 论坛监控（主流水线已不使用）
│   │   │   └── llm_host.py         # 裁判：引导 + 结构化终裁 + 启发式兜底
│   │   ├── knowledge/
│   │   │   ├── event_store.py, retriever.py, graph_insights.py
│   │   │   ├── followup_context.py, task_store.py
│   │   ├── preprocess/cleaner.py   # 数据清洗（jieba 分词 + 去停用词）
│   │   ├── report/
│   │   │   ├── export_html.py      # 独立 HTML 报告
│   │   │   ├── export_pdf.py, export_doc.py
│   │   ├── data/local_loader.py    # 本地上传文件解析（CSV/XLSX/JSON）
│   │   └── visualization/          # charts.py / dashboard.py
│   ├── data/                       # 采集数据缓存、data/tasks/ 任务注册表
│   ├── results/reports/            # 生成的 HTML 报告
│   └── logs/                       # forum_{task_id}.log 任务日志
└── frontend/
    ├── vite.config.js          # dev server + /api 与 /socket.io 代理
    ├── package.json
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── components/
        │   ├── Layout/MainLayout.jsx
        │   ├── LeftSidebar/LeftSidebar.jsx
        │   ├── CenterWorkspace/CenterWorkspace.jsx
        │   └── RightInsightPanel/RightInsightPanel.jsx
        ├── hooks/useAgentSocket.js
        └── services/api.js
```

---

## 测试

```bash
cd MarketPulse
python -m pytest tests/ -q
```

覆盖：Agent 单测、采集 providers、DDG、搜索引擎、情感分析、论坛 Host 等待、socket 契约、追问上下文、知识检索/存储、任务持久化与重启恢复、流水线 e2e、集成冒烟、SSRF 黑名单（协议/私网/CGNAT/IPv4-mapped/重定向逐跳）、信源分级。

### 手动诊断脚本（`MarketPulse/scripts/`）

这两个**不在** pytest 套件里——它们打真实搜索和真实 LLM，花好几分钟也产生真实费用。

```bash
cd MarketPulse

# StepFun Key 与端点连通性自检（退出码 0 正常 / 1 未配 Key / 2 调用报错）
python scripts/check_stepfun.py

# 真实链路自检：采集 → 信源分级 → 情绪 → 趋势 → 终裁 → 追问复辩
python scripts/verify_pipeline.py 华为
```

前端构建验证：

```bash
cd frontend && npm run build
```

---

## 技术栈

- **后端**：Python 3.9+ / Flask / Flask-SocketIO / PyYAML
- **前端**：React 18 / Vite 5 / Tailwind CSS / socket.io-client / Chart.js
- **NLP**：SnowNLP / jieba 分词（TF-IDF 带权重）
- **时序预测**：Prophet
- **LLM**：OpenAI 兼容接口（DeepSeek / 阶跃星辰 step-5-preview / GPT-4o / Claude / Qwen 等均可）
- **辅助入口**：Streamlit（`main.py`，仅用于独立 Agent 测试）

---

## 常见问题

<details>
<summary><strong>前端打开后一直"分析中"，输入框禁用</strong></summary>

两种可能。一是后端进程被重启过（`tasks` 是内存字典，重启即清空），此时重新 join 会收到 `task_complete(status='error')` 并提示"该分析任务已不存在"，重新开始即可。二是采集阶段真的还在跑——采集有 150s 总预算，多源回退叠加时可能需要两分钟。

另一个常见原因是**用 debug reloader 起 Flask**：watchdog 会因源码/字节码变动重启进程，把后台分析线程连同任务一起杀掉。本地长时间验证时建议 `socketio.run(app, debug=False, ...)`。
</details>

<details>
<summary><strong>没有 API Key，能看到什么？</strong></summary>

降级模式：红方用 SnowNLP 实测分布立论（负面/中性/积极条数与占比、平均情绪分、信源集中度、最负面标题），蓝方用 Prophet 结果立论（走向、置信度、数据质量），第二轮双方点名反驳，裁判输出启发式终裁（置信度 0.4）。界面标题栏会标注"裁判 LLM 暂不可用，本立论由本地模型生成"。
</details>

<details>
<summary><strong>采集阶段卡住不动</strong></summary>

检查 `logs/forum_*.log` 里是否有 `⏱ 已超出采集预算` 或 `本轮已熔断` 的告警。Google News RSS 被 503 拒绝时会自动降级到 DDG/Bing；DDG 连续失败会熔断该源，后续补充词直接跳过。单次请求有 `MP_SEARCH_TIMEOUT` 秒超时，另有 socket 级兜底（`socket.setdefaulttimeout`），因为 `ddgs` 自带的 timeout 不覆盖连接建立的每个阶段。
</details>

<details>
<summary><strong>重启后端后，左侧"分析记录"变空了</strong></summary>

不会。任务注册表落在 `MarketPulse/data/tasks/`（`TaskStore`，每个任务一个 JSON），启动时从磁盘恢复列表。上次进程退出时仍写着 `running` 的任务——它的后台线程已经跟着进程消失，永远不会再写终态——会被统一改判为中断，不会永远挂在"分析中"。只有 `data/tasks/` 被手动清空才会丢历史。
</details>

<details>
<summary><strong>新闻里混进 "Past hour" / "Past 7 days" 这种条目</strong></summary>

Bing 新闻页顶部的时间/排序筛选器也是指向 `/news/search` 的链接，兜底扫描会把它们当成新闻卡片。已用 `BING_UI_TITLES` + `_is_bing_ui_link()` 过滤，如仍出现说明 Bing 改了页面结构，需要同步更新这两个定义。
</details>

<details>
<summary><strong>采集文章时报"主机解析到内网/环回地址，已阻断"</strong></summary>

这是 SSRF 防护在起作用：搜索引擎返回的文章链接会被逐个校验，指向 `127.0.0.1`、`192.168.x.x`、`169.254.169.254`（云元数据）、`100.64.x.x`（运营商 NAT）等地址一律拒绝，重定向的每一跳也会重新校验。

如果你确实在跑本地模型服务（Ollama / vLLM 监听 127.0.0.1），设 `MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1` 可以放开 **LLM 端点**校验。这个开关**不影响**采集器抓取的第三方文章 URL——那些是不可信输入，放开等于把后端变成内网探针。
</details>

<details>
<summary><strong>Windows 上 Prophet 报错 <code>'Prophet' object has no attribute 'stan_backend'</code></summary></summary>

真正的错误被吞掉了。中文 Windows 的 `where.exe tbb.dll` 找不到文件时会打印 GBK 编码的"信息: 用提供的模式无法找到文件。"，cmdstanpy 把 stderr 并进 stdout 按 UTF-8 解码，抛出 `UnicodeDecodeError`；而它只捕获 `RuntimeError`，所以自带的 PATH 注入兜底永远不会执行，最终所有 backend 都失败、`self.stan_backend` 没赋值。

`src/analysis/trend_prediction.py` 的 `_seed_tbb_path()` 在导入 Prophet 之前把 prophet 自带的 `tbb` 目录前置到 `PATH`，让 `where.exe` 直接成功、不打印任何本地化信息。设 `PYTHONIOENCODING` / `PYTHONLEGACYWINDOWSSTDIO` 之类的环境变量解决不了这个问题。如果 Prophet 仍然不可用，蓝方会退化为线性回归基线并在右侧"趋势"Tab 标注 `fallback_reason`，流程不会断。
</details>

<details>
<summary><strong>安装 Prophet 失败（报错 pystan / C++ 编译错误）</strong></summary>

Prophet 依赖 `pystan`，需要 C++ 编译环境。macOS 上先 `brew install gcc`，Windows 上安装 Visual Studio Build Tools。如果不需要趋势预测，可在 `requirements.txt` 中注释 `prophet` 行——蓝方会走降级立论，流程不会断。
</details>

<details>
<summary><strong>情绪分布的可信度怎么看？</strong></summary>

看分母是谁。右侧"情感"Tab 除了正负中性比例和均分，还画了 Wilson 95% 置信区间——样本只有十几条时区间宽到没有判别力，这是事实，不是缺陷。"证据"Tab 按信源分级 T1-T4 分组：T4（自媒体/未识别来源）只作情绪信号，不作为事实依据。分级按域名后缀匹配，不按来源名字符串——后者是搜索引擎给的，写法五花八门。
</details>

---

## License

MIT

---

> Built with [BettaFish](https://github.com/your-org/bettafish) multi-agent architecture patterns.
