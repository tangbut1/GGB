# MarketPulse v4 — 多智能体论坛舆情分析系统

基于 BettaFish 架构理念升级的多智能体协作系统。五个独立 Agent（Collect / Sentiment / Trend / Report / Host）通过中央论坛日志（forum.log）模拟圆桌辩论，LLM Host 定期总结并指出分析盲区，驱动各 Agent 在迭代中不断完善结论。

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Textual](https://img.shields.io/badge/TUI-Textual-blueviolet)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 架构流程

```
用户/CLI 输入关键词 → TUI 工作台/事件循环 → OrchestratorAgent 调度
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
CollectAgent                   SentimentAgent                    TrendAgent
数据采集与清洗                  FinBERT + LLM 校正情感分析        Prophet 时序预测
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
- **LLM 情感校正**：FinBERT 基础分类后，SentimentAgent 通过 LLM 输出 JSON 进一步校正情感分布，确保负面率真实反映舆情
- **因果层级图谱**：EventExtractor 按因果层级（起因/发展/影响）构建有向事件关系图，支持触发/激化/引发/关联四种边类型
- **模型异构**：config.yaml + .env 支持每个 Agent 配置不同的大模型（OpenAI 兼容接口），也可通过全局变量一键切换
- **交互式导出**：生成含 Chart.js + vis-network 的独立 HTML 报告
- **本地工作台**：采用 Textual 驱动的终端用户界面（TUI），支持取消任务、查看历史、流式追问等高级操作，无需额外部署 Web 容器

---

## 快速启动

### 1. 克隆项目

```bash
git clone https://github.com/tangbut1/GGB.git
cd GGB/MarketPulse
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，将 5 个 Agent 的 `sk-xxx` 替换为真实 API Key：

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

**启动 TUI 终端工作台（推荐）：**
```bash
python3 console.py
```
(支持交互式仪表盘、模式选择、实时事件流与任务历史管理)

**或通过模块方式启动：**
```bash
python -m src.cli.app
```

**Headless 模式（无 TUI，直接输出结果）：**
```bash
python -m src.cli.app -k "华为" -m news
python -m src.cli.app --keyword "苹果" --mode social
```

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
| `MP_{AGENT}_MODEL` | 单 Agent 模型覆盖 |
| `MP_{AGENT}_BASE_URL` | 单 Agent API 地址覆盖 |
| `NEWSAPI_KEY` | 备用 NewsAPI 源（可选） |


---

## 工作台界面 (TUI)

- **左侧面板**：控制台与任务历史（最近 50 条任务）。支持查看过往任务图谱与分析结果。
- **右侧主交互区**：包含 **实时日志 (Pipeline/Agent 状态)**、**Agent 报告洞察**、**综合视图**、**因果链路概览**，并提供追问（Follow-up）功能。
- **快捷键支持**：按 `Escape` 取消进行中的流水线任务，`Ctrl+C` 退出工作台。其他快捷键包括 `g`(图谱)、`r`(报告)、`q`(追问)、`h`(历史)、`t`(主题切换)。

> *注：本项目已将核心分析逻辑（`OrchestratorAgent.stream_pipeline`）与 UI 完全解耦，全面拥抱 TUI 工作台和可持久化分析，原本的 Flask Web 端代码已在此版本移除。*

---

## 项目结构

```
MarketPulse/
├── requirements.txt
├── .env.example
├── README.md
├── src/
│   ├── config.yaml             # LLM 配置 + 采集量 + 分析参数
│   ├── config.py               # 统一配置解析管理
│   ├── cli/
│   │   ├── app.py              # Textual TUI 工作台主入口
│   │   └── events.py           # 流水线事件定义
│   ├── agents/
│   │   ├── base_agent.py       # Agent 基类 (call_llm + call_llm_with_system)
│   │   ├── collect_agent.py    # 数据采集 (多源搜索 + 本地数据融合)
│   │   ├── sentiment_agent.py  # 情感分析 (FinBERT + LLM 校正)
│   │   ├── trend_agent.py      # 趋势预测 (Prophet + 数据质量评级)
│   │   ├── report_agent.py     # 报告生成 + AI 解读 + 论坛辩论提取
│   │   └── orchestrator.py     # 流水线调度 (5 阶段 + 2 轮迭代)
│   ├── collect/
│   │   └── custom_search.py    # 多源搜索 (Google RSS → DDG → Bing → NewsAPI)
│   ├── analysis/
│   │   ├── sentiment_analysis.py  # FinBERT + TextBlob + 词典融合打分
│   │   ├── trend_prediction.py    # Prophet 时序预测
│   │   └── event_extractor.py     # jieba 关键词提取 + 因果层级图谱
│   ├── forum/
│   │   ├── log_manager.py      # forum.log 读写 + 线程安全
│   │   ├── monitor.py          # 守护线程 (阈值触发 HOST)
│   │   └── llm_host.py         # HOST LLM 调用
│   ├── preprocess/
│   │   └── cleaner.py          # 数据清洗 (jieba 分词 + 去停用词)
│   ├── report/
│   │   ├── export_html.py      # 独立 HTML 报告生成
│   │   ├── export_pdf.py       # PDF 导出
│   │   └── export_doc.py       # Word 导出
│   ├── data/
│   │   └── local_loader.py     # 本地上传文件解析 (CSV/XLSX/JSON)
│   └── visualization/
│       └── charts.py           # Plotly 图表（备用）
├── data/                       # 采集数据缓存
├── results/reports/            # 生成的 HTML 报告
└── logs/                       # forum.log 任务日志
```

---

## 测试

```bash
# 运行单元测试与集成测试
pytest tests/
```

### 独立功能测试

```bash
# 测试独立功能而不启动整个流水线
python3 test_agents.py

# 测试论坛 Monitor 与 HOST 触发机制
python3 test_forum.py
```

---

## 技术栈

- **运行时**：Python 3.9+ / PyYAML / Textual (TUI)
- **NLP**：FinBERT / TextBlob / jieba 分词
- **时序预测**：Prophet
- **报告导出**：HTML（内嵌 Chart.js + vis-network）；PDF / DOCX 为可选依赖（需额外安装 `reportlab` / `python-docx`）
- **LLM**：OpenAI 兼容接口（DeepSeek / GPT-4o / Claude / Qwen 等均可）
- **辅助入口**：Streamlit（`main.py`，仅用于独立 Agent 测试）

---

## License

MIT

---

> Built with [BettaFish](https://github.com/your-org/bettafish) multi-agent architecture patterns.
