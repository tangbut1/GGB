# MarketPulse — 红蓝辩论舆情分析后端

基于 BettaFish 架构理念升级的多智能体协作系统。用户输入关键词后，系统采集多源新闻，让两个立场对立的 Agent 围绕同一批数据展开两轮辩论，最后由裁判 Agent 输出结构化终裁。

- **红方** = `SentimentAgent`（危机分析师，看空、放大风险）
- **蓝方** = `TrendAgent`（理性分析师，看多、寻找破局点）
- **裁判** = `LLMHost`（中期引导 + 结构化终裁）

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/framework-Flask-green)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 启动

```bash
pip install -r requirements.txt
cp .env.example .env      # 填入真实 API Key（没有也能跑，进入降级模式）
python app.py             # 默认监听 5050，可用 PORT 覆盖
```

配套前端在仓库根目录的 `frontend/`（React + Vite，默认 5173），需同时启动。完整说明见根目录 `README.md`。

`main.py`（Streamlit）是独立的旧式流水线，**不走辩论架构**，只用于单独测试 Agent。

> `console.py` 与 `src/cli/` 已删除。`templates/index.html` 是旧版 vanilla-JS 界面，当前产品界面是 `frontend/` 的 React 应用。

---

## 辩论流水线

`src/agents/orchestrator.py` 的 `stream_pipeline()` 是生成器，产出 `PipelineEvent` / `ForumEvent` / `ReportEvent` / `ErrorEvent`（定义在 `src/events.py`）。`run_pipeline()` 是阻塞包装，供 Flask 后台线程调用。

```
Collect（多源采集 + 补充词，受 MP_SEARCH_BUDGET 总预算约束）
  → Round 1 红方立论（SnowNLP 实测分布）
  → Round 1 蓝方立论（Prophet 时序）
  → 裁判中期引导（LLM 不可用时无引导继续，不中断）
  → Round 2 红方反驳（点名回应蓝方具体数据）
  → Round 2 蓝方反驳（点名回应红方具体数据）
  → 裁判终裁（结构化 verdict）
  → ReportAgent 定稿 + 独立 HTML 报告
```

- Trend 失败**非致命**，注入降级摘要让下游继续。
- 采集不到真实结果时 CollectAgent 直接报错，**不注入假数据**。

### 降级模式（无 API Key）

SnowNLP / Prophet 本地兜底 + 启发式终裁（confidence 0.4）。此时红蓝双方**仍必须发言**：

- 红方 `_synthesize_red_speech()`：用实测分布合成立论——负面/中性/积极条数与占比、平均情绪分、分级【危机警报】、最负面的三条标题及分值、信源集中度，第二轮再附【驳斥蓝方】
- 蓝方 `lines` 列表：走向、置信度、预测窗口、数据质量评级，第二轮附【驳斥红方】

任一方失声都会让裁判只听到一面之词，辩论退化成单方陈述。

---

## Agents（均继承 `BaseAgent`）

`run(input_data) → {status, data, summary}`，LLM 通过 `call_llm(prompt)` / `call_llm_with_system(sys, usr)` 调用，全部走 OpenAI 兼容接口。

| Agent | 角色 | 关键依赖 |
|---|---|---|
| `CollectAgent` | 多源搜索（Google RSS → DDG → Bing）+ 本地数据合并 | `collect/custom_search.py`、`DataCleaner` |
| `SentimentAgent` | SnowNLP 打分 + LLM 校正（红方） | `analysis/sentiment_analysis.py` |
| `TrendAgent` | Prophet 时序预测 + 数据质量评级（蓝方） | `analysis/trend_prediction.py` |
| `ReportAgent` | HTML 报告 + AI 洞察 JSON + 辩论卡片提取 | `report/export_html.py`、`EventExtractor` |
| `LLMHost` | 裁判：中期引导 + 结构化终裁 | 被 orchestrator 直接调用 |

### Forum 机制

- **`LogManager`**：线程安全地追加写 `logs/forum_{task_id}.log`，每个 Agent 把发现写在这里。
- **`ForumMonitor`**：已不在主流水线中启动（裁判是流水线内的一等公民），保留供测试与旧代码使用。
- 裁判引导写回论坛日志，orchestrator 读取后拼进 Round 2 的 feedback。

### 任务持久化（TaskStore）

`tasks` 和 `task_history` 都是内存结构，后端一重启历史就全丢。`TaskStore`（`src/knowledge/task_store.py`）把每个任务写成一个 JSON，落在 `data/tasks/`（可用 `MP_TASK_STORE_DIR` 覆盖，默认锚在项目根而非 CWD）：

| 时机 | 调用 |
|---|---|
| `/analyze` 建任务时 | `create(task_id, keyword, src_mode)` → 状态 `running` |
| 跑完 | `update_status(task_id, "completed")` + `update_stats(...)`（耗时、样本数） |
| 失败 | `update_status(task_id, "error", error=原因)` |
| 进程启动 | `_seed_history_from_store()` 恢复列表 |

启动时会把上次退出仍写着 `running` 的任务改判为 `error`——它的后台线程已经跟着进程死了，不改写就永远挂在"分析中"，既占历史一行，也让 join 回放给出错误的等待预期。

> `TaskStore._lock` 必须是 `RLock`。`update_stats` 在一次持锁内做"读-改-写"，而 `_read`/`_write` 各自也会取同一把锁；用 `Lock` 会让自己把自己锁死，调用线程一直挂着，任务永远写不上终态。

---

## 关键设计

### LLM 失败约定

`BaseAgent._call_llm_inner()` 的**所有**失败路径（未配置、缺 Key、网络异常、响应格式异常）都返回以 `"Error"` 开头的字符串。降级逻辑必须用 `BaseAgent.llm_unavailable()` 判断：

```python
@staticmethod
def llm_unavailable(response: str) -> bool:
    return not response or not response.strip() or response.strip().startswith("Error")
```

不能把失败当成"成功了但内容不好"——否则会拿兜底值冒充模型结论。

### 引用对方发言

`BaseAgent.extract_opponent_claim(feedback, limit=...)` 从主持人拼装的 feedback 中取出对方上一轮发言。它会剥掉 `【段头】` 结构标记，并按句末（。！？；优先，逗号兜底）截断——直接切片会把词断在半中间，实测出现过"时间跨"这种残句。

### 采集预算与熔断

| 机制 | 说明 |
|---|---|
| `MP_SEARCH_BUDGET`（150s） | **整个采集阶段**总预算。`self._deadline` 在第一次搜索时设定，一次采集的主搜索 + 多个补充词共享同一个截止时间。按单次 `search_news` 给预算等于没有预算 |
| `MP_SEARCH_TIMEOUT`（15s） | 单次请求超时，同时通过 `socket.setdefaulttimeout()` 设为进程级兜底——`ddgs` 自带的 timeout 不覆盖连接建立的每个阶段，实测挂住过好几分钟 |
| `_google_banned` / `_bing_banned` / `_ddg_banned` | 数据源熔断标志（按采集器实例），命中 403/429/503 后短路，避免每轮重复踩被封来源 |

`BING_UI_TITLES` + `_is_bing_ui_link()` 过滤 Bing 页面顶部的时间/排序筛选器——它们也是指向 `/news/search` 的链接，兜底扫描会把它们当成新闻卡片收进来（标题全是 "Past hour"）。

### task_id

```python
task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
```

`int(time.time())` 分辨率是 1 秒，同一秒内发起的两次分析会拿到同一个 id，后一个任务覆盖前一个，两条流水线还会同时往同一个论坛日志和房间写数据。加随机后缀保证唯一，时间前缀保留便于按启动顺序读日志。

### JSON 安全序列化

`app.py` 的 `_json_safe()` 递归转换 Prophet/pandas 的 `Timestamp` 和 numpy 标量。它们会随预测结果进入 `analysis_data`，`socketio.emit` 时直接抛 `TypeError`，导致终态事件发不出、后台线程崩掉。

### Socket 传输

`async_mode='threading'` + werkzeug dev server ⇒ 只有 HTTP 长轮询。客户端会在轮询切换时周期性掉线又立刻重连，**这不是故障**：前端给 15s 重连宽限期，只有始终没重连才标记中断。实时单发事件会丢，所以 `on_join` 必须完整回放该任务已有状态（辩论发言 + 终态）。

`on_join` 遇到未知 task_id 时必须明确发 `task_complete(status='error')`——静默返回会让客户端一直等一个永远不来的事件，输入框永久禁用。

---

## 配置体系

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   （单 Agent，最高）
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL  （全局）
    → config.yaml 默认值                  （最低）
```

`src/config.yaml` 的 `${ENV_VAR}` 占位符由 `src/config.py` 在启动时展开。5 个 Agent + forum_host 各自独立 Key：`MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST}_AGENT_API_KEY`。

---

## HTTP 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 旧版 vanilla-JS 单页应用 |
| `/analyze` | POST | 提交分析任务，返回 `{task_id}` |
| `/history` | GET | 最近 50 条任务历史 |
| `/history/<task_id>` | GET | 单条任务详情 |
| `/report/<task_id>` | GET | 下载 HTML 报告 |
| `/status` | GET | 各 Agent 配置状态 |
| `/followup` | POST | SSE 流式追问（单模型读结论后回答，快） |
| `/debate_followup` | POST | 追问触发新一轮红蓝辩论（红蓝各自复辩 + 裁判补充裁定） |
| `/stream/<task_id>` | GET | SSE 实时日志流 |

SocketIO 事件：`join`（C→S）、`debate_turn`、`forum_message`、`agent_update`、`task_complete`、`verdict_update`、`api_usage_update`。

> 前端访问这些路由时带 `/api` 前缀（`/api/analyze`），由 Vite 代理剥掉前缀后转发到这里。直接 curl 后端请用上表的裸路径。

---

## 项目结构

```
MarketPulse/
├── app.py                      # Flask 主控 + SocketIO + 任务线程
├── main.py                     # Streamlit 独立 Agent 测试入口（不走辩论）
├── requirements.txt
├── start.bat
├── .env.example
├── scripts/                    # 手动诊断脚本（打真实 API，不进 pytest）
│   ├── check_stepfun.py        #   StepFun Key 连通性自检
│   └── verify_pipeline.py      #   采集→分级→情绪→趋势→终裁→追问 全链路自检
├── templates/index.html        # 旧版 vanilla-JS 界面
├── src/
│   ├── config.yaml / config.py # 配置（${ENV_VAR} 展开）
│   ├── events.py               # PipelineEvent / ForumEvent / ReportEvent / ErrorEvent
│   ├── net_safety.py           # SSRF 防护：协议白名单 + 内网地址黑名单
│   ├── agents/
│   │   ├── base_agent.py       # 基类：call_llm + llm_unavailable + extract_opponent_claim
│   │   ├── collect_agent.py    # 数据采集（多源 + 本地数据融合 + 信源分级）
│   │   ├── sentiment_agent.py  # 红方：SnowNLP + LLM 校正 + 降级立论合成
│   │   ├── trend_agent.py      # 蓝方：Prophet + 数据质量评级 + 降级反驳
│   │   ├── report_agent.py     # 报告 + AI 解读 + 辩论卡片提取 + TF-IDF 权重
│   │   ├── stepfun_agent.py    # 阶跃星辰 Agent（追问上下文补全，非硬依赖）
│   │   └── orchestrator.py     # 红蓝辩论流水线调度 + 追问复辩
│   ├── collect/
│   │   ├── custom_search.py    # 多源搜索 + 预算/熔断/Bing UI 过滤 + 逐跳 SSRF 校验
│   │   ├── source_registry.py  # 信源可信度分级 T1-T4（按域名后缀匹配）
│   │   ├── ingest_cache.py, news_collector.py, providers.py, sentiment_api.py
│   ├── analysis/
│   │   ├── sentiment_analysis.py  # SnowNLP + TextBlob + 词典融合
│   │   └── trend_prediction.py    # Prophet 时序预测（含 Windows TBB 路径修正）
│   ├── forum/
│   │   ├── log_manager.py      # forum log 读写 + 线程安全
│   │   ├── monitor.py          # 论坛监控（主流水线已不使用）
│   │   └── llm_host.py         # 裁判：引导 + 终裁 + 启发式兜底
│   ├── knowledge/              # event_store / retriever / graph_insights / followup_context / task_store
│   ├── preprocess/cleaner.py   # jieba 分词 + 去停用词
│   ├── report/                 # export_html / export_pdf / export_doc
│   ├── data/local_loader.py    # 上传文件解析（CSV/XLSX/JSON）
│   └── visualization/          # charts.py / dashboard.py
├── data/                       # 采集数据缓存；data/tasks/ 任务注册表（TaskStore）
├── results/reports/            # 生成的 HTML 报告
└── logs/                       # forum_{task_id}.log 任务日志
```

---

## 启动陷阱：不要用 reloader

```python
socketio.run(app, debug=False, port=...)   # 对
socketio.run(app, debug=True, ...)         # 错
```

debug 模式会拉起 watchdog reloader。流水线跑到一半时任何源码或 `.pyc` 变动都会让进程重启，**后台分析线程连同任务一起被杀死**——前端停在"报告生成中"，永远收不到 `task_complete`，输入框一直禁用。所以 `app.py` 与 `start.bat` 都是 `debug=False`；需要热重载的调试场景请另用 `flask run`，跑分析一律走 `python app.py`。

---

## 测试

```bash
python -m pytest tests/ -q
```

覆盖：Agent 单测、采集 providers、DDG、搜索引擎、情感分析、论坛 Host 等待、socket 契约、追问上下文、知识检索/存储、任务持久化与重启恢复、流水线 e2e、集成冒烟、SSRF 黑名单（协议/私网/CGNAT/IPv4-mapped/重定向逐跳）、信源分级。

手动诊断脚本（打真实搜索与真实 LLM，花时间也花钱，所以不进自动套件）：

```bash
python scripts/check_stepfun.py       # StepFun Key 连通性
python scripts/verify_pipeline.py 华为  # 全链路自检
```

---

## 技术栈

- **运行时**：Python 3.9+ / Flask / Flask-SocketIO / PyYAML
- **NLP**：SnowNLP / jieba 分词
- **时序预测**：Prophet
- **报告导出**：HTML（内嵌 Chart.js + vis-network）；PDF / DOCX 为可选依赖（需额外安装 `reportlab` / `python-docx`）
- **LLM**：OpenAI 兼容接口（DeepSeek / 阶跃星辰 step-5-preview / GPT-4o / Claude / Qwen 等均可）

---

## License

MIT

---

> Built with [BettaFish](https://github.com/your-org/bettafish) multi-agent architecture patterns.
