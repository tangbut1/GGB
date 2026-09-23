# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 本文件与 `AGENTS.md` 正文一致（仅标题不同）。修改请同步改 `AGENTS.md`，否则两份会漂移。

## What This Project Is

MarketPulse 是一个**红蓝辩论式**多智能体舆情分析系统。用户输入一个关键词，系统采集多源新闻，然后让两个立场对立的 Agent 围绕同一批数据展开两轮辩论，最后由裁判 Agent 给出结构化终裁。

- 红方 = `SentimentAgent`（危机分析师，看空、放大风险）
- 蓝方 = `TrendAgent`（理性分析师，看多、寻找破局点）
- 裁判 = `LLMHost`（中期引导 + 终裁结构化裁定）

## Entry Points

系统是**两个独立进程**，必须同时运行：

| 进程 | 入口 | 端口 | 说明 |
|---|---|---|---|
| 后端 | `MarketPulse/app.py` | 5050 | Flask + Flask-SocketIO，红蓝辩论内核 |
| 前端 | `frontend/`（Vite） | 5173 | React SPA，`/api` 与 `/socket.io` 代理到 5050 |

```bash
# 终端 1：后端（在 MarketPulse/ 下）
cd MarketPulse && python app.py

# 终端 2：前端（在 frontend/ 下）
cd frontend && npm run dev
```

浏览器打开 **http://localhost:5173/**。

端口可用 `PORT` 环境变量覆盖后端（默认 5050）；改端口必须同步改 `frontend/vite.config.js` 里的 proxy target。

`MarketPulse/main.py`（Streamlit）是独立的旧式流水线，**不走辩论架构**，只用于单独测试 Agent。

> `console.py` 与 `src/cli/` 已删除，文档里再看到 Textual TUI 的说法都是过期的。

## Commands

```bash
# 安装
pip install -r MarketPulse/requirements.txt
cd frontend && npm install

# 配置（复制后填入真实 Key）
cp MarketPulse/.env.example MarketPulse/.env

# 测试（必须在 MarketPulse/ 下）
python -m pytest tests/ -q

# 手动诊断脚本（打真实搜索与真实 LLM，花时间也花钱，不在 pytest 里）
python scripts/check_stepfun.py        # StepFun Key 连通性
python scripts/verify_pipeline.py 华为  # 采集→分级→情绪→趋势→终裁→追问 全链路

# 前端构建
cd frontend && npm run build
```

## Architecture: Red-Blue Debate

### Pipeline (`OrchestratorAgent.stream_pipeline()`)

```
Collect（多源采集 + 补充词，受总预算约束）
  → Round 1 红方立论（SnowNLP 实测分布）
  → Round 1 蓝方立论（Prophet 时序）
  → 裁判中期引导（失败则无引导继续）
  → Round 2 红方反驳（点名回应蓝方）
  → Round 2 蓝方反驳（点名回应红方）
  → 裁判终裁（结构化 verdict）
  → ReportAgent 定稿 + HTML 报告
```

- `stream_pipeline()` 是生成器，产出 `PipelineEvent` / `ForumEvent` / `ReportEvent` / `ErrorEvent`（定义在 `src/events.py`）。
- `run_pipeline()` 是阻塞包装，供 Flask 后台线程调用。
- Trend 失败**非致命**，注入降级摘要让下游继续。
- 采集不到真实结果时 CollectAgent 直接报错，**不注入假数据**。

### Agents（均继承 `BaseAgent`）

`run(input_data) → {status, data, summary}`，LLM 通过 `call_llm(prompt)` / `call_llm_with_system(sys, usr)` 调用，全部走 OpenAI 兼容接口。

| Agent | 角色 | 关键依赖 |
|---|---|---|
| `CollectAgent` | 多源搜索（Google RSS → DDG → Bing）+ 本地数据合并 + 信源分级 | `custom_search.py`、`source_registry.py`、`DataCleaner` |
| `SentimentAgent` | SnowNLP 打分 + LLM 校正（红方） | `SentimentAnalyzer` |
| `TrendAgent` | Prophet 时序预测 + 数据质量评级（蓝方） | `TrendPredictor` |
| `ReportAgent` | HTML 报告 + AI 洞察 JSON + 辩论卡片提取 + TF-IDF 权重 | `export_html.py`、`EventExtractor` |
| `LLMHost` | 裁判：中期引导 + 结构化终裁 | 被 orchestrator 直接调用 |
| `StepFunAgent` | 阶跃星辰 `step-5-preview`，做追问上下文补全与终裁第二意见 | `src/agents/stepfun_agent.py` |

`StepFunAgent` **不是红蓝辩论的一员**，也不继承 `BaseAgent`（它不需要论坛写权限）。红蓝双方跑在 deepseek 上——互相驳斥要快且便宜；StepFun 只接需要长上下文和更强推理的独立环节。未配 Key 时 `available()` 返回 False，调用方自动回落到 deepseek 路径，**不构成硬依赖**。

### Forum 机制

- **`LogManager`**：线程安全地追加写 `logs/forum_{task_id}.log`，每个 Agent 把发现写在这里。
- **`ForumMonitor`**：已不在主流水线中启动（裁判是流水线内的一等公民），保留供测试与旧代码使用。
- 裁判引导写回论坛日志，orchestrator 读取后拼进 Round 2 的 feedback。

### 信源可信度分级（`src/collect/source_registry.py`）

情绪分布的统计意义完全取决于样本是谁说的：把一条自媒体推文和一条新华社快讯算成同一个"样本"，正面/负面比例就被稀释得没有解释力。所以每条数据都带一个 `source_tier`（1-4，数字越小越权威），前端右侧"证据"Tab 按层级分组，"热词"与"情感"的分母也能分开统计。

| 层级 | 含义 |
|---|---|
| T1 | 权威通讯社 / 央媒 / 监管机构，有一线采编与事实核查流程 |
| T2 | 主流财经与行业媒体，有编辑审核，可能带立场 |
| T3 | 门户 / 地方媒体 / 聚合站，转载为主，事实层薄 |
| T4 | 自媒体 / 论坛 / 未识别来源，仅作情绪信号，**不作为事实依据** |

**分级只按域名后缀匹配，不按来源名字符串**：来源名字段是搜索引擎给的，写法五花八门（"新华网"、"新华社新闻"、"Xinhua"），域名只有一个。写后缀而不是完整域名，子域名自动归到同一层。有域名但不在表里归 T3（不冒充实名），没有 URL 归 T4。

### SSRF 防护（`src/net_safety.py`）

采集器要抓搜索结果里文章的正文，而那些 URL 来自第三方搜索引擎的返回内容——等于把不可信输入直接喂给 `requests`。一个指向 `http://127.0.0.1:6379` 或 `http://169.254.169.254/` 的"新闻链接"就能让后端变成探测内网的跳板。

`validate_public_url()` 是所有外发请求的统一出口，校验四件事：协议仅 http/https、禁止内嵌凭证（`user:pass@host`）、DNS 解析结果不得落在环回/私有/链路本地/保留/组播/未指定段。采集器抓正文、`BaseAgent` 的 LLM 端点、`StepFunAgent`、`LLMHost` 全部走它，**不要在各处另写一份**。

`is_blocked_ip()` 有两个容易漏的点，改它之前先看测试：

- **CGNAT 100.64.0.0/10**：`ipaddress` 在 3.13 之前不把它算作 `is_private`，必须显式列出。服务端没有理由直连运营商内网。
- **IPv4-mapped IPv6**（`::ffff:127.0.0.1`）：部分 Python 版本上 `is_loopback` 判定为 False，先还原成 IPv4 再判，别让套壳地址绕过整张黑名单。

本地模型服务（Ollama/vLLM 跑在 127.0.0.1）是合理配置，留了显式逃生口 `MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1`，**默认必须是关的**。另注意 `requests.post` 默认跟随重定向，LLM 调用必须显式 `allow_redirects=False`——否则校验过的公网地址可以 302 跳到内网，前面的校验全部作废。

### Configuration Hierarchy（env 覆盖 config.yaml）

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   （单 Agent，最高）
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL  （全局）
    → config.yaml 默认值                  （最低）
```

6 个 Agent 各自独立 Key：`MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST|STEPFUN}_AGENT_API_KEY`。

每个 `agent_llm` 条目都可配 `timeout` / `max_retries`（`BaseAgent.__init__` 读取，默认 120s / 2 次）。**不要写死**：step-5-preview 这类带 reasoning 的模型在长 prompt 下很容易超过 60s，硬编码 `timeout=60` 会让 LLM 校正间歇性静默失效。重试会跳过 4xx（429 除外）——请求本身有问题时重试没有意义。

采集相关：`MP_SEARCH_TIMEOUT`（单请求秒数，默认 15）、`MP_SEARCH_BUDGET`（**整个采集阶段**总秒数，默认 150）。
SSRF 逃生口：`MP_ALLOW_PRIVATE_LLM_ENDPOINTS=1`（默认关）。
任务注册表：`MP_TASK_STORE_DIR`（默认 `MarketPulse/data/tasks`）。

## Frontend (React)

`frontend/src/`，React 18 + Vite + Tailwind + socket.io-client：

```
App.jsx
├── theme.js                                 # 主题读取/切换/持久化 + useChartColors（canvas 取色）
├── index.css                                # 两套 CSS 变量（:root 暗 / [data-theme=light] 亮）
├── Layout/MainLayout.jsx                 # 状态汇总 + 历史加载 + 左右侧栏拖拽调宽
├── LeftSidebar/LeftSidebar.jsx           # 分析记录（点击 = 重跑该关键词）+ 主题切换
├── CenterWorkspace/CenterWorkspace.jsx   # 辩论卡片 + 输入框 + 追问
├── RightInsightPanel/RightInsightPanel.jsx  # 终裁/趋势/情感/热词/证据 五个 Tab
├── hooks/useAgentSocket.js               # socket 生命周期 + 状态归一
└── services/api.js                       # /api 代理 + SSE 追问
```

配色是 Slate + Teal 的明暗双主题，左侧栏顶部切换，选择存 `localStorage` 键 `ggb-theme`。颜色唯一来源是 `index.css` 的 CSS 自定义属性，`tailwind.config.js` 只做 token 映射，组件里不写死色值。改配色前注意两条：实色要写成 `R G B` 三通道并在 config 里套 `rgb(var(--c-x) / <alpha-value>)`，否则 Tailwind v3 会静默丢弃所有带不透明度修饰符的类；`theme.js` 的 `CHART_VARS` 必须把驼峰键显式对上 kebab-case 变量名，CSS 自定义属性大小写敏感，拼错时 `getPropertyValue` 只返回空字符串、图表颜色静默失效。

后端只认 `/api/...` 与 `/socket.io` 前缀（见 `vite.config.js` 的 rewrite）。

**两条追问路径，别混**：`/followup` 是"让一个模型读结论然后回答"，快但只有一方的声音；`/debate_followup` 是让红蓝双方就追问各自复辩、裁判出补充裁定，慢但是真辩论。追问轮次从 **3** 开始（首轮两轮立论 + 反驳占 1、2），前端用 `FOLLOWUP_ROUND_MIN` 判断卡片要不要打"追问复辩"标记。复辩**不重新采集**，复用首轮数据；`run_followup_debate` 的发言通过 SocketIO 的 `debate_turn` / `forum_message` 实时推送，HTTP 响应里只回 turns + verdict。

侧栏宽度：`MainLayout` 用 `ResizeHandle` 实现拖拽调宽（左 64-520px，右 320-720px），双击复位，另有按钮完全折叠。`ResizeHandle` 是受控组件，宽度由父组件持有——它自己不存宽度状态。

右侧五个 Tab 不是装饰，每个都对应一种可复现的算法输出，缺数据时**明确说"本次运行未取得"而不是画个假的**：

- **终裁**：verdict + 样本口径（总条数 + 信源分级分布）+ 置信度说明（裁判自评，不是统计显著性）
- **趋势**：`model_type` / `data_points` / `forecast_window` / `data_quality`，Prophet 不可用时显示 `fallback_reason`
- **情感**：SnowNLP 分数 + LLM 校正前后对比，Wilson 95% 置信区间点线图
- **热词**：`keyword_weights` 里真实的 jieba TF-IDF 值与 `doc_freq`，**没有权重就不画柱状图**——用排名反推高度等于编造数值
- **证据**：按 `source_tier` T1→T4 分组的新闻卡片

## Key Patterns

- **LLM 失败约定**：`BaseAgent._call_llm_inner()` 的所有失败路径都返回以 `"Error"` 开头的字符串。降级逻辑必须用 `BaseAgent.llm_unavailable()` 判断，不能把失败当成"成功了但内容不好"——否则会拿兜底值冒充模型结论。
- **降级模式（无 Key）**：SnowNLP/Prophet 本地兜底 + 启发式终裁（confidence 0.4）。此时红蓝双方**仍必须发言**：红方用 `_synthesize_red_speech()`、蓝方用 `lines` 列表基于实测数据合成，不能失声变成单方陈述。
- **引用对方发言**：用 `BaseAgent.extract_opponent_claim(feedback, limit=...)`。它会剥掉 `【段头】` 并按句末截断——直接切片会把词断在半中间（实测出现过"时间跨"这种残句）。
- **采集预算按实例算**：`CustomSearchCollector` 的 `self._deadline` 在第一次搜索时设定，一次采集的多个补充词共享同一个截止时间。按单次 `search_news` 给预算等于没有预算。
- **socket 传输只有 HTTP 长轮询**（`async_mode='threading'` + werkzeug）。客户端会在轮询切换时周期性掉线又立刻重连，**这不是故障**：前端给 15s 重连宽限期，只有始终没重连才标记中断。实时单发事件会丢，所以 `on_join` 必须回放全部状态。
- **task_id 格式**：`task_{int(time.time())}_{uuid4hex[:6]}`。只用时间戳会在同一秒内碰撞，两个任务互相覆盖。
- **`_json_safe()`**：Prophet/pandas 的 `Timestamp` 和 numpy 标量会随预测结果进入 `analysis_data`，`socketio.emit` 时直接抛 TypeError。所有下发数据都要过它。
- **Windows 上 Prophet 必须先喂 TBB 路径**（`src/analysis/trend_prediction.py::_seed_tbb_path()`）：中文 Windows 的 `where.exe tbb.dll` 会打印 GBK 编码的"信息: 用提供的模式无法找到文件。"，cmdstanpy 把 stderr 并进 stdout 按 UTF-8 解码直接抛 `UnicodeDecodeError`；它只捕 `RuntimeError`，所以自带的 PATH 注入兜底永远不会执行，最终所有 backend 失败、`self.stan_backend` 没赋值，报错信息是那句没有上下文的 `'Prophet' object has no attribute 'stan_backend'`。解法是在 `from prophet import Prophet` **之前**把 prophet 自带的 `tbb` 目录前置到 `PATH`，让 `where.exe` 直接成功、不打印任何本地化信息。设 `PYTHONIOENCODING` 之类的环境变量没用。
- **TF-IDF 权重要真的传下去**：`ReportAgent._extract_keyword_weights()` 用 jieba `withWeight=True` 取真实权重和 `doc_freq`，经 `app.py` 塞进 `analysis_data.keyword_weights`。前端拿不到权重时宁可不画图——**用排名反推柱高等于编造数据**。
- **`fallback_reason` 要透传到前端**：Prophet 失败退化到线性基线时，`TrendPredictor.fit_error` 记原因，`TrendAgent` 写进 `trend_summary`，`app.py` 下发。不告诉用户"这是退化模型、区间语义和 Prophet 不同"，用户会把恒定宽度的残差带当成不确定性分解来读。
- **FinBERT 缺失不是错误**：`requirements.txt` 里没有 torch，`SentimentAnalyzer` 先用 `_torch_available()` 探一次再决定要不要加载，否则每次运行都打两行 `name 'torch' is not defined`。没有 FinBERT 时"财经词典 + SnowNLP"照样能跑。
- **任务状态要落盘**：`tasks` / `task_history` 都是内存结构，重启即清空。`TaskStore`（`src/knowledge/task_store.py`，每个任务一个 JSON）负责持久化：`/analyze` 时 `create`，终态时 `update_status` + `update_stats`，启动时 `_seed_history_from_store()` 恢复列表。上次退出时仍是 `running` 的任务会被改判为中断——它的线程已经跟着进程死了，不改写就永远挂在"分析中"。注意 `TaskStore._lock` 必须是 `RLock`：`update_stats` 在持锁期间调用同样取锁的 `_read`/`_write`。
- **不要在有流水线运行时用 reloader 起 Flask**：watchdog 会因源码/字节码变动重启进程，把后台分析线程连同任务一起杀掉，前端永远收不到终态。本地验证时用 `socketio.run(app, debug=False, ...)`。

## Gotchas

- Bing 新闻页顶部的时间/排序筛选器也是指向 `/news/search` 的链接，兜底扫描会把它们当成新闻卡片收进来（标题全是 "Past hour"）。已用 `BING_UI_TITLES` + `_is_bing_ui_link()` 过滤。
- `ddgs` 自带的 timeout 不覆盖连接建立的每个阶段，单次调用可能挂住好几分钟。除 deadline 检查外还有 `socket.setdefaulttimeout()` 兜底，以及 `_ddg_banned` 熔断。
- SnowNLP 对中文财经/政治文本系统性低报负面。`SentimentAgent` 会把 SnowNLP 结果 + 样本交给 LLM 校正，再按分数排序重排标签。
- `MarketPulse/templates/index.html` 是 200KB 的旧版 vanilla-JS 单页应用（`http://localhost:5050/` 仍可访问），当前产品界面是 `frontend/` 的 React 应用。改 UI 只改 `frontend/`。
