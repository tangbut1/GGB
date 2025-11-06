# MarketPulse 市场情绪分析模型

MarketPulse 是一个围绕 Streamlit 构建的市场资讯分析模型项目，目标是探索从新闻采集、数据清洗、情绪分析、趋势预测到可视化与报告导出的完整流程。项目聚焦于方法论与代码结构，方便二次开发和实验验证。

## 项目结构

```text
.
├── README.md
└── MarketPulse/
    ├── assets/              # 静态资源（Logo、样式等）
    ├── data/                # 示例数据：raw/ 与 processed/
    ├── docs/                # 设计与说明文档草稿
    ├── results/             # 运行产物（图表、日志、报告），默认忽略版本控制
    ├── main.py              # Streamlit 应用入口
    ├── requirements.txt     # 所需 Python 依赖
    └── src/
        ├── analysis/        # 情绪分析、趋势预测等逻辑
        ├── collect/         # RSS/自定义搜索采集器
        ├── data/            # 本地数据加载工具
        ├── preprocess/      # 数据清洗与去重
        ├── report/          # PDF/DOCX 报告生成
        ├── visualization/   # 图表生成与仪表盘展示
        └── ai_integration.py# AI 服务封装
```

## 快速开始

1. **克隆仓库并进入根目录**
   ```bash
   git clone https://github.com/your-username/MarketPulse.git
   cd MarketPulse
   ```

2. **创建并激活虚拟环境**（建议使用 Python 3.9+）
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```

3. **安装依赖**（从应用目录读取）
   ```bash
   pip install -r MarketPulse/requirements.txt
   ```
   > 依赖中包含 prophet、torch 等科学计算/深度学习库，首次安装可能需要额外的系统环境或更长时间。如仅需基础功能，可根据需求裁剪 `requirements.txt`。

4. **启动 Streamlit 应用**
   ```bash
   streamlit run MarketPulse/main.py
   ```
   或者先进入应用目录再运行：
   ```bash
   cd MarketPulse
   streamlit run main.py
   ```

5. **访问应用**：默认浏览器中打开 `http://localhost:8501`。

## 配置与自定义

- 所有基础配置集中在 `src/config.yaml` 中，可调整采集源、默认分类、AI 供应商等参数。
- Streamlit 页面支持选择「在线新闻」「自定义关键词搜索」「本地表格数据」等多种数据来源，混合模式可同时结合自定义搜索与本地上传数据。
- `src/ai_integration.py` 提供了 OpenAI、HuggingFace 等服务的统一封装，如需实际调用请在环境变量或配置文件中写入 API Key。
- `docs/` 目录包含设计思路与使用手册草稿，可作为扩展功能的起点。

## 数据与输出

- `data/raw/` 内附示例 JSON，可用于离线体验数据清洗与情绪分析流程。上传自己的 CSV/Excel 数据亦可通过界面解析。
- 清洗后的结果会写入 `data/processed/`，日志与可视化资源会进入 `results/` 目录。
- 报告导出功能支持 PDF 与 DOCX 两种格式，文件保存在 `results/reports/` 下。

## 常见问题

- **安装 prophet/torch 失败**：请参考官方文档安装 C++/Fortran 编译环境或使用已有的深度学习运行时；亦可临时在 `requirements.txt` 中注释相关依赖。
- **未获取到在线新闻**：检查本地网络、RSS 源可用性或在界面选择自定义搜索/本地数据。
- **生成报告失败**：确认已创建 `results/` 目录并具备写入权限，同时检查 PyMuPDF、python-docx 是否正确安装。


如果这个项目对你有所启发，欢迎点亮 ⭐️ 支持！
