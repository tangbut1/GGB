## 2.2 核心模块设计
为保障市场脉搏分析平台在复杂资讯环境下的稳定运行，系统从数据入口到知识产出构建了层层递进的模块化结构。各核心模块既保持功能内聚，又通过标准化的数据接口进行耦合，对研究生阶段的实证研究形成可靠支撑。以下从数据采集与输入管理、情绪建模与结果呈现两个维度展开阐述，并细化至关键类与方法。

### 2.2.1 多源数据采集与输入管理模块
该模块聚焦于为后续分析提供高覆盖率且格式化的语料来源，涵盖在线 RSS 抓取、自定义关键词搜索与本地文件导入三种模式，并通过统一的数据结构实现无缝切换。

#### 架构概览
- **数据源调度层**：`main.py` 中的 `DATA_SOURCE_CHOICES` 与 `run_pipeline()` 将用户选择映射为采集策略，支持“在线”“自定义搜索”“本地”“混合”四种模式。
- **采集执行层**：由 `NewsCollector`（RSS）与 `CustomSearchCollector`（关键词搜索）分别负责，从不同渠道获取原始资讯。
- **标准化接入层**：利用 `load_local_table()` 与 `deduplicate_news()` 将各来源统一为字段完整、去重后的标准化字典列表。

#### 关键组件与方法
- **RSS 批量采集子系统（`src.collect.news_collector.NewsCollector`）**
  - `__init__(categories)`：根据用户选择或默认类别（科技、金融、国际、股票）初始化源表，并设置 `min_results=100` 与三日时间窗口，确保数据新鲜度。
  - `fetch_latest()`：逐源调用 `_collect_feed_entries()`，记录成功/失败源数；当目标样本量不足时自动补充未选类别，实现弹性扩充。
  - `_collect_feed_entries(category, url)`：使用 `feedparser` 解析 RSS，针对每条目提取标题、链接、摘要、正文等字段，结合 `_is_recent_news()` 过滤过期资讯，并记录日志。
  - `clean_and_deduplicate(news_list)`：以链接为主键、来源加标题的 MD5 为退路，去除重复报道；返回去重列表并输出统计。
  - `save_news(news_list)`：将原始数据序列化至 `data/raw/raw_news.json`，为实验复现提供数据快照。
  - `run_full_pipeline()`：串联“抓取 → 去重 → 落盘”流程，并在源完全失效时调用 `create_sample_data()` 生成示例集，保证管线可继续执行。

- **关键词搜索补偿子系统（`src.collect.custom_search.CustomSearchCollector`）**
  - `run_custom_search(keyword, max_results=120)`：融合 DuckDuckGo 新闻接口与 Bing HTML 抓取；当主搜索结果不足时自动触发 `_search_generic()` 补全。
  - `_search_duckduckgo()` 与 `_search_generic()`：分别负责结构化 API 与半结构化网页解析，并通过 `_parse_datetime()` 将多样时间格式统一为 `datetime` 对象。
  - `_enrich_news_content(news_items)`：以线程池并发调用 `_extract_article_text()` 补全正文与摘要，限制最大抓取条数与文本长度，兼顾效率与质量。
  - `_deduplicate_news(news_list)`：按链接与来源联合主键去重，保留跨媒体的差异化报道。
  - `save_news(news_list, keyword)`：对关键词进行文件名安全化处理，将结果保存至 `data/raw/custom_search_*`，附带时间戳便于追踪。

- **本地数据导入接口（`src.data.local_loader.load_local_table`）**
  - 文件解析：支持 CSV、XLS/XLSX、JSON 及未知后缀的回退解析；在读取失败时自动二次尝试（`StringIO` / `BytesIO`），提高适配性。
  - `_normalize_columns(df)`：通过 `COLUMN_ALIASES` 对中文/英文列名进行语义映射，缺失字段则补齐空列，确保输出字段集为 `title/content/summary/publish_time/source/category`。
  - 返回值：输出标准化记录列表与预览用 `DataFrame`；前者直接供 `run_pipeline()` 消费，后者可在前端提供前 20 行展示以辅助用户检验数据质量。

#### 数据质量与稳健性策略
1. **时间窗口约束**：无论 RSS 还是搜索结果，均通过 `_is_recent_news()` 和 `_parse_datetime()` 控制在近三天内，避免历史噪声。
2. **多级去重**：既在采集阶段处理重复链接，也在 `main.py` 中调用 `deduplicate_news()` 进行最终归一化，保证情绪计算基数准确。
3. **失效回退机制**：当外部接口失效时，RSS 模块提供示例数据，搜索模块通过多关键词与双通道补偿，确保实验流程可持续。
4. **可追溯存档**：所有原始与清洗后数据均落盘至 `data/raw` 与 `data/processed`，配合日志输出便于后续溯源与复现。

### 2.2.2 情绪建模与可视化呈现模块
该模块负责将标准化文本转换为可量化的情绪指数、趋势预测与可视化报告，覆盖文本预处理、情绪推断、时间序列建模、AI 辅助解读、交互式呈现等关键环节。

#### 处理流程概述
1. **文本清洗**：`DataCleaner` 对标题、正文、摘要进行分词与停用词过滤，生成干净语料并保留原文备份。
2. **情绪估计**：`SentimentAnalyzer` 基于词典、SnowNLP、TextBlob 三元融合得出情绪得分与置信度。
3. **趋势建模**：`TrendPredictor` 将情绪序列对齐为 Prophet 所需结构，输出未来 30 天的走势预测并提供基线回退方案。
4. **AI 辅助分析**：`AIClient` 自适应调用 OpenAI / HuggingFace / 自定义接口，为部分样本追加模型评分与自然语言解读。
5. **可视化与报告**：`ChartGenerator`、`DashboardManager`、`PDFReportGenerator`、`DOCXReportGenerator` 等组件将结果以图表、仪表盘与文档形式呈现。

#### 核心组件与方法
- **文本预处理模块（`src.preprocess.cleaner.DataCleaner`）**
  - `clean_text(text)`：执行 HTML 标签剥离、特殊字符约束、数字短语过滤，并依据是否包含中文选择分词策略；中文文本采用结巴分词与财经停用词表强化语义噪声过滤。
  - `clean_news_batch(news_list)`：批量处理新闻记录，分别清洗标题、内容、摘要，若清洗结果为空则回退原文；保留 `original_*` 字段以支持对照研究。
  - `save_cleaned_data(cleaned_news)`：将清洗结果保存至 `data/processed/cleaned_news.json`，便于后续模型训练或人工审阅。
  - `extract_keywords(text, top_k)`：提供高频词提取能力，为词云图与主题分析提供数据基础。

- **情绪分析模块（`src.analysis.sentiment_analysis.SentimentAnalyzer`）**
  - `analyze_single(text)`：分别调用 `_dict_based_sentiment()`（词典法）、`_snownlp_sentiment()`（中文情绪模型）、`_textblob_sentiment()`（英文情绪模型），再用均值融合并以标准差估置信度；根据阈值输出 `positive/neutral/negative` 标签。
  - `analyze_news_batch(news_list)`：对清洗后的新闻逐条融合标题、内容、摘要进行分析，并将情绪指标写回原结构，便于下游使用。
  - `get_sentiment_summary(analyzed_news)`：统计总样本量、各情绪类别数量与平均得分，为仪表盘指标卡提供数据来源。
  - `save_analysis_results(analyzed_news, summary)`：以 JSON 形式持久化详细结果与摘要至 `results/logs/sentiment_analysis.json`，支撑后续论文或报告引用。

- **趋势预测模块（`src.analysis.trend_prediction.TrendPredictor`）**
  - `prepare_data(sentiment_data)`：将情绪结果按发布日期聚合为日均值，并进行缺失值线性插值，确保时间序列连续。
  - `train_model(df)`：优先训练 Prophet 模型；若外部依赖缺失或训练失败则调用 `_build_baseline_model()` 生成线性回归方案，增强鲁棒性。
  - `predict_trend(periods)`：基于成功训练的模型输出未来情绪预测区间（`yhat`, `yhat_lower`, `yhat_upper`），并计算趋势方向与置信度。
  - `analyze_market_sentiment_trend(sentiment_data, periods)`：封装“准备 → 训练 → 预测”链路，返回包含历史数据、预测结果及元信息的综合摘要；`save_prediction_results()` 将结果固化至 `results/logs/trend_prediction.json`。
  - `get_trend_summary(results)`：对预测结果进行语义化解读，生成“积极/消极/稳定”趋势及对应建议。

- **AI 辅助解读模块（`src.ai_integration.AIClient`）**
  - `auto_detect()`：依据环境变量自动确定提供商及模型（OpenAI / HuggingFace / 自定义 / 无 AI），减少配置成本。
  - `classify_sentiment(texts)`：按提供商分别调用 `_classify_with_openai()`、`_classify_with_huggingface()` 或 `_classify_with_custom_endpoint()`；在模型不可用时退回 `_rule_based_scores()`，保障输出稳定。
  - `generate_insights(sentiment_summary, trend_summary)`：当可用时调用文本生成模型，产生结构化的“情绪解读”与“趋势点评”；否则调用 `_rule_based_commentary()` 输出模板化分析。

- **可视化与报告模块**
  - `src.visualization.charts.ChartGenerator`：提供情绪分布饼图、时间线散点图、趋势预测曲线、热力图及关键词柱状图等多种 Plotly 图形，`save_chart(fig, path, format)` 可导出 PNG/HTML 供线下引用。
  - `src.visualization.dashboard.DashboardManager`：在 Streamlit 前端组织指标卡、图表标签页、新闻详情筛选与关键词分析等交互，关键方法包括 `render_sentiment_overview()`、`render_charts_section()`、`render_news_details()` 等。
  - `src.report.export_pdf.PDFReportGenerator` 与 `src.report.export_doc.DOCXReportGenerator`：基于 ReportLab 与 python-docx 构建标准化报告结构，包含标题页、目录、执行摘要、情绪详情、趋势分析、案例分析与图表集，实现成果固化与分享。

- **运行调度与状态管理（`main.py` 核心函数）**
  - `ensure_dirs()`：在程序启动时创建 `results/charts`、`results/logs`、`results/reports`、`data/processed` 等必要目录，避免文件写入异常。
  - `generate_chart_assets(sentiment_data, trend_data)`：驱动 `ChartGenerator` 输出情绪/趋势图，并将路径缓存于 `chart_paths`。
  - `run_pipeline(...)`：整合上述模块，执行“采集 → 清洗 → 情绪分析 → 趋势建模 → AI 增强 → 图表生成”的完整流程；通过 `st.session_state` 缓存阶段性结果，供仪表盘、报告导出及后续交互调用。

#### 数据流与接口规范
- 输入：标准化新闻记录 `List[Dict[str, Any]]`，字段统一为标题、正文、摘要、时间、来源、类别、链接。
- 中间结果：
  - 清洗结果保留 `original_*` 字段，便于对照与回溯；
  - 情绪分析输出新增 `sentiment_score`、`sentiment_confidence`、`sentiment_label`、`ai_sentiment_score`（可选）；
  - 趋势预测返回 `historical_data` 与 `predictions`，同时附带 `trend_direction`、`confidence` 等摘要指标。
- 输出：图表文件（PNG/HTML）、日志文件（JSON）、报告文档（PDF/DOCX）及 Streamlit 仪表盘实时展示。

通过上述多层协同，系统能够在复杂多变的市场资讯环境中持续稳定地输出高质量情绪指标，并以图文形式助力研究者开展深入分析。