# 🧩 MarketPulse 全自动环境与结构初始化流程

## 🎯 项目目标
- 删除旧依赖与环境，重建干净的虚拟环境
- 构建企业级 MarketPulse 结构
- 接入 AI 模型扩展接口（OpenAI / Meta / HuggingFace）
- 实现高质量趋势预测、情绪分析与可视化仪表盘
- 支持报告导出（PDF / DOCX）

---

## 🧠 一键初始化命令脚本（直接粘贴到 Cursor 终端执行）

```bash
# ==============================
# 🧩 MarketPulse 全自动环境与结构初始化流程
# ==============================

# 1️⃣ 删除旧虚拟环境
Remove-Item -Recurse -Force ./venv

# 2️⃣ 创建并激活新虚拟环境
python -m venv venv
./venv/Scripts/activate

# 3️⃣ 升级基础工具
python -m pip install --upgrade pip setuptools wheel

# 4️⃣ 安装核心依赖（统一到 requirements.txt）
pip install streamlit pandas numpy matplotlib plotly seaborn scikit-learn prophet transformers torch torchvision torchaudio beautifulsoup4 requests jieba snownlp wordcloud PyMuPDF python-docx

# 5️⃣ 生成新的 requirements.txt
pip freeze > requirements.txt

# 6️⃣ 设置项目环境变量
set PYTHONPATH=${PWD}

# 7️⃣ 创建主运行文件 main.py（Cursor 自动生成）
# main.py 用于启动 Streamlit 仪表盘与 AI 模型预测

# 8️⃣ 增强特性说明：
# - 自动检测可用 AI 模型（OpenAI / Meta / HuggingFace）
# - 统一接口 ai_integration.py
# - 日志、模型、图表输出路径：./results, ./models, ./charts
# - 实时可视化与预测
# - 报告导出支持（PDF / DOCX）

# 9️⃣ 启动命令
streamlit run main.py
```

---

## ⚙️ Cursor 操作建议
1. 打开项目文件夹 `MarketPulse`
2. 删除旧的 `venv/`
3. 将上方脚本复制进 Cursor 的命令执行框
4. 等待环境安装完毕后运行：
   ```bash
   streamlit run main.py
   ```
5. 浏览器将自动打开 MarketPulse 智能市场分析仪表盘

---

## 💎 模块说明

| 模块 | 功能 | 技术亮点 |
|------|------|-----------|
| `src/collect` | 新闻 & 舆情采集 | 多源采集（API + RSS + 网页抓取） |
| `src/preprocess` | 数据清洗与存储 | NLP 预处理 + 缓存机制 |
| `src/analysis` | 市场趋势与情绪分析 | Prophet + Transformer 模型融合 |
| `src/visualization` | 图表与仪表盘展示 | Plotly + Streamlit 动态交互 |
| `src/report` | 报告导出 | 支持 PDF / DOCX 一键导出 |
| `src/ai_integration.py` | AI 模型接口 | 兼容 OpenAI / Meta / HuggingFace |
| `results/` | 输出结果 | 自动保存分析图与日志 |
| `models/` | 模型缓存 | 本地持久化与热更新支持 |

---

## 🚀 下一步可选任务
- [ ] 生成 `main.py`：自动化仪表盘控制中心
- [ ] 生成 `src/ai_integration.py`：统一 AI 接口模块
- [ ] 生成 `src/config.yaml`：配置模型与参数
