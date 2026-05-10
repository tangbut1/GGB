# MarketPulse v4 — 多智能体论坛舆情分析系统

基于 BettaFish 架构理念升级的多智能体协作系统。五个独立 Agent（Collect / Sentiment / Trend / Report / Host）通过中央论坛日志（forum.log）模拟圆桌辩论，LLM Host 定期总结并指出分析盲区，驱动各 Agent 在迭代中不断完善结论。

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/framework-Flask-green)
![Streamlit](https://img.shields.io/badge/dev--tools-Streamlit-red)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 架构流程

```
用户输入关键词 → Flask 主控 → OrchestratorAgent 流水线调度
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
CollectAgent                   SentimentAgent                    TrendAgent
数据采集与清洗                  SnowNLP + LLM 校正情感分析        Prophet 时序预测
    │                               │                               │
    └───────────┬───────────────────┴───────────┬───────────────────┘
                │                               │
                ▼                               ▼
           forum.log ◄── Monitor 守护线程 ──► LLM Host
          (Agent 写入发现)    (达到阈值触发)    (总结 + 盲区引导)
                │                               │
                └───────────┬───────────────────┘
                            ▼
                      ReportAgent
                   HTML 报告 + 事件图谱 + AI 解读
```

### 五轮迭代流程

| Round | 内容 |
|-------|------|
| Round 1 | CollectAgent 采集 → SentimentAgent 情感分析 → TrendAgent 趋势预测 → HOST 总结 & 盲区引导 |
| Round 2 | SentimentAgent + TrendAgent 根据 HOST 盲区引导深入分析 → HOST 综合研判 |
| 报告 | ReportAgent 定稿 → 生成交互式 HTML 报告 + 事件关系图谱 + AI 洞察卡片 |

---

## 核心特性

- **5 Agent 解耦**：采集、情感、趋势、报告、主持人各自独立 LLM 配置
- **论坛辩论机制**：Agent 把关键发现写入 forum.log，Monitor 守护线程在达到阈值（Agent 消息 ≥ 5 条或 15 秒无新消息）时触发 Host 介入
- **LLM 情感校正**：SnowNLP 对中文财经/政治文本存在正向偏置，SentimentAgent 通过 LLM 输出 JSON 校正情感分布，确保负面率真实反映舆情
- **因果层级图谱**：EventExtractor 按因果层级（起因/发展/影响）构建有向事件关系图，支持触发/激化/引发/关联四种边类型
- **模型异构**：config.yaml + .env 支持每个 Agent 配置不同的大模型（OpenAI 兼容接口），也可通过全局变量一键切换
- **实时推流**：Flask-SocketIO 将论坛讨论实时推送前端面板
- **交互式导出**：生成含 Chart.js + vis-network 的独立 HTML 报告
- **追问功能**：AI 解读 Tab 内任意洞察卡片可展开详情并触发 SSE 流式追问

---

## 界面预览

> 启动后浏览器打开 `http://localhost:5050` 可看到完整界面。以下截图展示了系统的主要功能模块：

| 模块 | 说明 |
|------|------|
| 左侧面板 | Agent 状态指示 + 实时日志流 + 关键词输入 |
| 概览 Tab | 舆情摘要 + 情感四维指标卡片 |
| 数据图表 Tab | 饼图 + 折线图 + 柱状图 + 堆叠图 |
| 事件关系图 Tab | 因果层级有向图谱，支持主线/时间/平台/全景四种视图 |
| AI 解读 Tab | 洞察卡片（置信度条 + 反共识标签 + 追问）+ 多智能体辩论时间线 |

> 📸 截图请替换为实际运行截图，放在 `MarketPulse/assets/` 目录下

---

## 快速启动

### 1. 克隆项目

```bash
git clone https://github.com/tangbut1/GGB.git
cd GGB
```

### 2. 安装依赖

```bash
pip install -r MarketPulse/requirements.txt
```

### 3. 配置 API Key

```bash
cp MarketPulse/.env.example MarketPulse/.env
```

编辑 `MarketPulse/.env`，将 5 个 Agent 的 `sk-xxx` 替换为真实 API Key：

```bash
# CollectAgent - 数据采集与清洗
MP_COLLECT_AGENT_API_KEY=sk-your-real-key

# SentimentAgent - 情感分析
MP_SENTIMENT_AGENT_API_KEY=sk-your-real-key

# TrendAgent - 趋势预测
MP_TREND_AGENT_API_KEY=sk-your-real-key

# ReportAgent - 报告生成
MP_REPORT_AGENT_API_KEY=sk-your-real-key

# Forum Host - 论坛主持人
MP_FORUM_HOST_API_KEY=sk-your-real-key
```

**全局一键切换模型**（可选）：如需切换到其他兼容 OpenAI 协议的模型（如 GPT-4o、Claude、Qwen），在 `.env` 中取消注释并配置：

```bash
MP_GLOBAL_BASE_URL=https://api.openai.com/v1
MP_GLOBAL_MODEL=gpt-4o
```

也可以针对单个 Agent 精准覆盖：

```bash
MP_SENTIMENT_AGENT_MODEL=deepseek-v4-pro    # 仅情感分析用 Pro 模型
MP_TREND_AGENT_BASE_URL=https://api.openai.com/v1  # 仅趋势预测换接口
```

### 4. 启动服务

**macOS / Linux：**
```bash
cd MarketPulse
bash start.sh
```

**Windows：**
```cmd
cd MarketPulse
start.bat
```

**或直接用 Flask：**
```bash
cd MarketPulse
python3 -m flask run --host=0.0.0.0 --port=5050
```

浏览器打开 **http://localhost:5050** 即可使用。

---

## 配置体系

### 覆盖优先级（由高到低）

```
环境变量单 Agent 覆盖 (MP_COLLECT_AGENT_MODEL)
  → 环境变量全局覆盖 (MP_GLOBAL_MODEL)
    → config.yaml 默认值
```

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
    social: 500             # 社交媒体模式目标采集量
    news: 300               # 新闻媒体模式目标采集量
  min_results:
    social: 300
    news: 200
  time_distribution:        # 采集时间分布配比
    recent_7d: 0.30
    week_8_30d: 0.40
    month_31_90d: 0.30
```

### 环境变量完整列表

| 变量 | 说明 |
|------|------|
| `MP_COLLECT_AGENT_API_KEY` | 采集 Agent API Key |
| `MP_SENTIMENT_AGENT_API_KEY` | 情感 Agent API Key |
| `MP_TREND_AGENT_API_KEY` | 趋势 Agent API Key |
| `MP_REPORT_AGENT_API_KEY` | 报告 Agent API Key |
| `MP_FORUM_HOST_API_KEY` | 论坛主持人 API Key |
| `MP_GLOBAL_BASE_URL` | 全局 API 地址覆盖 |
| `MP_GLOBAL_MODEL` | 全局模型名覆盖 |
| `MP_{AGENT}_MODEL` | 单 Agent 模型覆盖（如 `MP_SENTIMENT_AGENT_MODEL`） |
| `MP_{AGENT}_BASE_URL` | 单 Agent API 地址覆盖 |
| `NEWSAPI_KEY` | 备用 NewsAPI 源（可选） |
| `SECRET_KEY` | Flask Session 密钥 |

---

## 使用指南

### 选择数据源模式

- **社交媒体模式**：采集微博、抖音、小红书、知乎、X/Twitter 等平台的公开讨论，适合分析品牌口碑、产品情绪、热点事件
- **新闻媒体模式**：采集 Google News、Bing News、财经媒体等专业报道，适合分析政策影响、行业趋势、机构观点

### 本地文件上传

支持拖拽上传 CSV、TSV、Excel、JSON 文件，后端会自动解析并与线上采集数据融合分析。

### 查看分析结果

分析完成后，右侧面板提供四个 Tab：

| Tab | 内容 |
|-----|------|
| **概览** | 舆情摘要、情感指标卡片（正面/负面/采集量/综合分）、关键词标签 |
| **数据图表** | 情感分布饼图、30天情感走势折线图、多平台采集量柱状图、各平台情感堆叠图 |
| **事件关系图** | 因果层级有向图谱（起因→发展→影响），支持主线/时间/平台/全景四种视图，节点详情面板 + 负面链路高亮 |
| **AI 解读** | 核心判断卡（action_signal 徽章）、洞察卡片流（置信度进度条 + 反共识标签 + 展开详情 + 追问）、数据盲区、多智能体论坛辩论时间线 |

### 追问功能

在 AI 解读 Tab 展开任意洞察卡片，点击"深挖原因"、"质疑这个判断"、"给出可执行建议"或输入自定义追问，弹窗内 SSE 流式返回 AI 回复。

### 导出报告

点击底部"下载 HTML 报告"生成含 Chart.js 图表的独立 HTML 文件，也可导出 PDF / Word 格式。

---

## API 端点

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主界面 |
| `/analyze` | POST | 提交分析任务 |
| `/stream/<task_id>` | GET | SSE 实时日志流 |
| `/report/<task_id>` | GET | 下载 HTML 报告 |
| `/status` | GET | 各 Agent 配置状态 |
| `/history` | GET | 最近 50 条任务历史 |
| `/followup` | POST | SSE 流式 AI 解读追问 |

### `/analyze` 请求体

```json
{
  "keyword": "华为",
  "srcMode": "social",
  "local_data": [],
  "local_data_raw_files": []
}
```

---

## 项目结构

```
GGB/
├── README.md                   # 本文件
└── MarketPulse/
    ├── app.py                  # Flask 主控 + SocketIO + SSE
    ├── main.py                 # Streamlit 独立 Agent 测试入口
    ├── requirements.txt
    ├── start.sh / start.bat
    ├── .env.example
    ├── README.md
    ├── templates/
    │   └── index.html          # 前端单页应用 (Chart.js + vis-network)
    ├── src/
    │   ├── config.yaml         # LLM 配置 + 采集量 + 分析参数
    │   ├── agents/
    │   │   ├── base_agent.py   # Agent 基类 (call_llm + call_llm_with_system)
    │   │   ├── collect_agent.py    # 数据采集 (多源搜索 + 本地数据融合)
    │   │   ├── sentiment_agent.py  # 情感分析 (SnowNLP + LLM 校正)
    │   │   ├── trend_agent.py      # 趋势预测 (Prophet + 数据质量评级)
    │   │   ├── report_agent.py     # 报告生成 + AI 解读 + 论坛辩论提取
    │   │   └── orchestrator.py     # 流水线调度 (5 阶段 + 2 轮迭代)
    │   ├── collect/
    │   │   └── custom_search.py    # 多源搜索 (Google RSS → DDG → Bing → NewsAPI)
    │   ├── analysis/
    │   │   ├── sentiment_analysis.py  # SnowNLP + TextBlob + 词典融合打分
    │   │   ├── trend_prediction.py    # Prophet 时序预测
    │   │   └── event_extractor.py     # jieba 关键词提取 + 因果层级图谱
    │   ├── forum/
    │   │   ├── log_manager.py    # forum.log 读写 + 线程安全
    │   │   ├── monitor.py        # 守护线程 (阈值触发 HOST)
    │   │   └── llm_host.py       # HOST LLM 调用
    │   ├── preprocess/
    │   │   └── cleaner.py        # 数据清洗 (jieba 分词 + 去停用词)
    │   ├── report/
    │   │   ├── export_html.py    # 独立 HTML 报告生成
    │   │   ├── export_pdf.py     # PDF 导出
    │   │   └── export_doc.py     # Word 导出
    │   ├── data/
    │   │   └── local_loader.py   # 本地上传文件解析 (CSV/XLSX/JSON)
    │   └── visualization/
    │       └── charts.py         # Plotly 图表（备用）
    ├── data/                     # 采集数据缓存
    ├── results/reports/          # 生成的 HTML 报告
    └── logs/                     # forum.log 任务日志
```

---

## 测试

### 全流程测试

1. 启动服务后访问 `http://localhost:5050/status` 确认 5 个 Agent 均为 `configured: true`
2. 选择数据源模式（社交媒体 / 新闻媒体），输入关键词，点击"开始分析"
3. 观察左侧 Agent 状态依次变为 active → done，日志区实时滚动
4. 任务完成后四个 Tab 依次检查：概览 / 数据图表 / 事件关系图 / AI 解读
5. 在 AI 解读 Tab 展开任意洞察卡片，点击追问按钮验证流式追问
6. 点击"下载 HTML 报告"验证离线报告

### 独立 Agent 测试

```bash
cd MarketPulse

# 测试 CollectAgent 数据采集
python3 tests/test_agents.py

# 测试论坛 Monitor 与 HOST 触发机制
python3 tests/test_forum.py
```

---

## 技术栈

- **后端**：Python 3.9+ / Flask / Flask-SocketIO / PyYAML
- **前端**：Vanilla JS / Chart.js 4.4 / vis-network / SSE
- **NLP**：SnowNLP / TextBlob / jieba 分词
- **时序预测**：Prophet
- **LLM**：OpenAI 兼容接口（DeepSeek / GPT-4o / Claude / Qwen 等均可）

---

## 常见问题

<details>
<summary><strong>安装 Prophet 失败（报错 pystan / C++ 编译错误）</strong></summary>

Prophet 依赖 `pystan`，需要 C++ 编译环境。macOS 上先安装：
```bash
brew install gcc
```
Windows 上安装 Visual Studio Build Tools。如果不需要趋势预测功能，可在 `requirements.txt` 中注释 `prophet` 行。
</details>

<details>
<summary><strong>安装 PyTorch 太慢或失败</strong></summary>

`requirements.txt` 中的 torch 依赖带有平台条件（`platform_system!="Windows"`），macOS/Linux 会安装完整版。如果只需要基础功能，可注释掉 `torch`、`torchaudio`、`torchvision` 三行。
</details>

<details>
<summary><strong>启动后未获取到在线新闻</strong></summary>

系统使用 Google News RSS → DuckDuckGo → Bing News → NewsAPI 四层回退。国内网络环境下 Google News RSS 可能不可用，系统会自动降级到 Bing/DDG。如果所有源均失效，系统会使用模拟数据继续流程。
</details>

<details>
<summary><strong>AI 解读 Tab 没有显示洞察卡片</strong></summary>

LLM 可能未按 JSON 格式输出。系统有 5 级兜底解析（代码块剥离 → 直接解析 → 大括号提取 → 正则 → Markdown 结构解析），如果全部失败会回退到模拟数据展示。检查 API Key 余额和网络连通性。
</details>

<details>
<summary><strong>事件关系图所有关系都显示"关联"</strong></summary>

需要后端 EventExtractor 正常提取因果层级后，才会出现触发/激化/引发等有向边类型。如果采集数据量过少或全部来自同一时间段，层级差异不明显时会回退到基础关联模式。确保采集量 ≥ 50 条且时间跨度 > 1 天。
</details>

---

如果这个项目对你有所启发，欢迎点亮 ⭐️ 支持！
