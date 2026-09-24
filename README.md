# MarketPulse — 红蓝辩论式多智能体舆情分析系统

输入一个关键词，系统采集多源新闻，让两个立场对立的 Agent 围绕**同一批数据**展开两轮辩论，最后由裁判输出结构化终裁。

- **红方** `SentimentAgent`：危机分析师，看空、放大风险
- **蓝方** `TrendAgent`：理性分析师，看多、寻找破局点
- **裁判** `LLMHost`：中期引导 + 结构化终裁

## 快速启动

系统是两个独立进程，需同时运行：

```bash
# 后端（默认 :5050）
cd MarketPulse
pip install -r requirements.txt
cp .env.example .env        # 填入 API Key；没有 Key 也能跑，进入本地降级模式
python app.py

# 前端（默认 :5173）
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173/ 。后端端口可用 `PORT` 环境变量覆盖，改端口需同步修改 `frontend/vite.config.js` 的 proxy target。

Windows 下也可直接运行 `MarketPulse/start.bat` 启动后端。

## 辩论流程

```
采集（多源新闻 + 补充词，受总预算约束）
  → 红方立论（SnowNLP 实测情绪分布）
  → 蓝方立论（Prophet 时序预测）
  → 裁判中期引导（失败则无引导继续，不中断流水线）
  → 红方反驳（点名回应蓝方的具体数据）
  → 蓝方反驳（点名回应红方的具体数据）
  → 裁判终裁（结构化 verdict）
  → 报告定稿 + 独立 HTML 报告
```

两条硬规则：趋势预测失败**非致命**，注入降级摘要让下游继续；采集不到真实结果时直接报错，**不注入假数据**。

## 核心特性

- **真辩论，不是轮流发言**：第二轮必须点名回应对方上一轮的具体数据
- **降级不失声**：无 API Key 时红蓝双方仍基于本地算法（SnowNLP / Prophet）的实测值发言，裁判输出启发式终裁，不会变成单方陈述
- **信源可信度分级**：每条数据按域名后缀归入 T1-T4，情绪分布按层级分开统计——把自媒体推文和央媒快讯算成同一个样本，正负比例就没有解释力
- **可复现的算法输出**：情感带 Wilson 95% 置信区间，趋势标注模型类型与降级原因，热词用真实 TF-IDF 权重；拿不到数据时明确说明"本次运行未取得"，不画假的
- **追问引发复辩**：追问不是让一个模型再答一遍，而是红蓝双方各自复辩、裁判出补充裁定，轮次从 3 起算，复用首轮数据
- **SSRF 防护**：所有外发请求统一经 `src/net_safety.py` 校验，拒绝环回/私有/CGNAT/保留地址

## 演示案例

[`cases/zcode-privacy-event/`](cases/zcode-privacy-event/) 保存了一次完整运行的实录：以「zcode后端偷偷上传用户隐私」为关键词，采集 9 条样本、两轮红蓝辩论、终裁中性（综合风险分 45.7/100，行动信号 watch_out）。目录内含 13 张界面截图、机器可读的全量运行结果（`case-data.json`）与后端生成的 HTML 报告（`report.html`），三者同源，可离线对照复核。采集结果随时间变化，复现时数值以当次运行为准。

## 配置

模型配置三层覆盖，优先级从高到低：

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   （单个 Agent）
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL （全局）
    → config.yaml 默认值
```

6 个 Agent 各自独立 Key：`MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST|STEPFUN}_AGENT_API_KEY`，全部走 OpenAI 兼容接口。

常用环境变量：`MP_SEARCH_BUDGET`（整个采集阶段总秒数，默认 150）、`MP_SEARCH_TIMEOUT`（单请求秒数，默认 15）、`MP_TASK_STORE_DIR`（任务注册表目录）。

StepFun Agent（`step-5-preview`）只接追问上下文补全等独立环节，未配 Key 时自动回落，**不构成硬依赖**。

## 项目结构

```
MarketPulse/              Flask + SocketIO 后端（红蓝辩论内核）
  app.py                  入口：/analyze、/followup、/debate_followup
  src/agents/             Orchestrator + 5 个 Agent + 裁判 LLMHost
  src/collect/            多源采集、信源分级、本地数据合并
  src/analysis/           SnowNLP 情感分析、Prophet 趋势预测
  src/knowledge/          任务持久化（TaskStore）
  src/net_safety.py       外发请求统一校验
  tests/                  pytest 测试
  scripts/                手动诊断脚本（打真实搜索与 LLM，耗时花钱）
frontend/                 React 18 + Vite 前端（研判工作台）
  src/components/Layout/  主布局 + 侧栏拖拽调宽
  src/components/LeftSidebar/  分析记录 + 主题切换 + 设置入口
  src/components/CenterWorkspace/  终裁卡 + 辩论发言 + 输入框 + 追问
  src/components/RightInsightPanel/  趋势 / 证据（含热词） / 事件脉络 / 数据质量 四个 Tab
  src/components/Settings/  模型与会话设置面板
```

前端界面是研判工作台：终裁卡在中栏，右侧四个 Tab 各对应一种可复现的算法输出，缺数据时明确说明而不是展示假数据。

## 测试

```bash
cd MarketPulse && python -m pytest tests/ -q
```

`scripts/` 下的诊断脚本不在 pytest 里，会打真实搜索与真实 LLM，按需手动运行：

```bash
python scripts/check_stepfun.py       # StepFun Key 连通性
python scripts/verify_pipeline.py 华为  # 采集→分级→情绪→趋势→终裁→追问 全链路
```

## 追问的两种路径

| 路径 | 行为 |
|---|---|
| `/followup` | 让一个模型读结论后回答，快，但只有一方声音 |
| `/debate_followup` | 红蓝双方就追问各自复辩、裁判出补充裁定，慢，但是真辩论 |
