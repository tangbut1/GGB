from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.collect.news_collector import NewsCollector
from src.preprocess.cleaner import DataCleaner
from src.analysis.sentiment_analysis import SentimentAnalyzer
from src.analysis.trend_prediction import TrendPredictor
from src.visualization.charts import ChartGenerator
from src.visualization.dashboard import DashboardManager
from src.report.export_pdf import PDFReportGenerator
from src.report.export_doc import DOCXReportGenerator
from src.ai_integration import AIClient
from src.data.local_loader import load_local_table


def load_config():
    import yaml
    cfg_path = Path(__file__).parent / "src" / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs():
    for p in ["results/charts", "results/logs", "results/reports", "data/processed"]:
        Path(p).mkdir(parents=True, exist_ok=True)


DEFAULT_CATEGORIES = ["科技", "金融", "国际", "股票"]
DATA_SOURCE_CHOICES: Dict[str, str] = {
    "在线新闻采集": "online",
    "本地表格数据": "local",
    "在线 + 本地数据": "hybrid"
}
AI_PROVIDER_CHOICES: Dict[str, str] = {
    "自动检测": "auto",
    "禁用AI": "none",
    "OpenAI": "openai",
    "HuggingFace": "huggingface",
    "自定义接口": "custom"
}


def generate_chart_assets(sentiment_data: List[Dict[str, Any]],
                          trend_data: Dict[str, Any]) -> Dict[str, Path]:
    generator = ChartGenerator()
    charts_dir = Path("results/charts")
    charts_dir.mkdir(parents=True, exist_ok=True)

    charts: Dict[str, Path] = {}
    figures = {
        "sentiment_distribution": generator.create_sentiment_distribution_chart(sentiment_data),
        "sentiment_timeline": generator.create_sentiment_timeline_chart(sentiment_data),
        "trend_prediction": generator.create_trend_prediction_chart(trend_data),
        "sentiment_heatmap": generator.create_sentiment_heatmap(sentiment_data)
    }

    for name, fig in figures.items():
        try:
            output_path = charts_dir / f"{name}.png"
            generator.save_chart(fig, str(output_path), format="png")
            charts[name] = output_path
        except Exception as exc:  # noqa: BLE001
            st.warning(f"图表 {name} 保存失败: {exc}")
    return charts


def deduplicate_news(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for item in news_list:
        title = str(item.get("title") or item.get("original_title") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key not in unique:
            unique[key] = item
    return list(unique.values())


def build_ai_client(ai_config: Optional[Dict[str, Any]]) -> AIClient:
    ai_config = ai_config or {}
    provider = ai_config.get("provider", "auto")
    if provider == "auto":
        return AIClient.auto_detect()
    if provider == "none":
        return AIClient(provider="none")
    return AIClient(
        provider=provider,
        model=ai_config.get("model"),
        api_key=ai_config.get("api_key"),
        endpoint=ai_config.get("endpoint")
    )


def run_pipeline(data_source: str,
                 selected_categories: List[str],
                 local_records: Optional[List[Dict[str, Any]]] = None,
                 ai_config: Optional[Dict[str, Any]] = None,
                 local_preview: Optional[pd.DataFrame] = None) -> None:
    st.session_state.setdefault("news", [])
    st.session_state.setdefault("cleaned_news", [])
    st.session_state.setdefault("sentiment_results", [])
    st.session_state.setdefault("sentiment_summary", {})
    st.session_state.setdefault("trend_results", {})
    st.session_state.setdefault("trend_summary", {})
    st.session_state.setdefault("chart_paths", {})
    st.session_state.setdefault("ai_summary", {})

    st.write("🚀 MarketPulse: 数据分析流程启动...")

    local_records = local_records or []
    aggregated_news: List[Dict[str, Any]] = []
    collector = NewsCollector(categories=selected_categories)

    # 1️⃣ 数据采集
    if data_source in {"online", "hybrid"}:
        with st.spinner("正在采集新闻数据..."):
            online_news = collector.run_full_pipeline()
            if online_news:
                st.success(f"✅ 已采集 {len(online_news)} 条财经新闻！")
                aggregated_news.extend(online_news)
            else:
                st.warning("⚠️ 未能获取在线新闻，请检查网络或RSS源。")

    # 额外合并本地数据
    if data_source in {"local", "hybrid"} and local_records:
        st.success(f"✅ 已加载 {len(local_records)} 条本地数据。")
        for record in local_records:
            aggregated_news.append({
                "title": record.get("title", ""),
                "content": record.get("content", ""),
                "summary": record.get("summary", ""),
                "publish_time": record.get("publish_time", ""),
                "source": record.get("source", "本地数据"),
                "category": record.get("category", "本地数据"),
                "link": record.get("url") or record.get("link", "")
            })
    elif data_source in {"local", "hybrid"} and not local_records:
        st.warning("⚠️ 未检测到本地数据，请先上传表格或选择在线采集。")

    aggregated_news = deduplicate_news(aggregated_news)

    if not aggregated_news:
        st.error("❌ 没有可用的数据，终止分析流程。")
        return

    # 2️⃣ 数据清洗
    with st.spinner("正在清洗数据..."):
        cleaner = DataCleaner()
        cleaned_news = cleaner.clean_news_batch(aggregated_news)
        cleaner.save_cleaned_data(cleaned_news)
        st.success(f"✅ 已清洗 {len(cleaned_news)} 条新闻数据！")

    if not cleaned_news:
        st.error("❌ 清洗后没有可用的数据。")
        return

    # 3️⃣ 情绪分析
    with st.spinner("正在进行情绪分析..."):
        sentiment_analyzer = SentimentAnalyzer()
        analyzed_news = sentiment_analyzer.analyze_news_batch(cleaned_news)
        sentiment_summary = sentiment_analyzer.get_sentiment_summary(analyzed_news)
        sentiment_analyzer.save_analysis_results(analyzed_news, sentiment_summary)
        st.success(f"✅ 情绪分析完成！平均情绪得分: {sentiment_summary['avg_sentiment']}")

    # 4️⃣ 趋势预测
    with st.spinner("正在进行趋势预测..."):
        trend_predictor = TrendPredictor()
        trend_results = trend_predictor.analyze_market_sentiment_trend(analyzed_news)
        trend_summary = trend_predictor.get_trend_summary(trend_results)
        if 'error' not in trend_results:
            trend_predictor.save_prediction_results(trend_results)
        st.success(f"✅ 趋势预测完成！趋势方向: {trend_summary.get('trend_direction', 'unknown')}")

    # 5️⃣ AI增强分析（可选）
    ai_client = build_ai_client(ai_config)
    ai_scores: List[float] = []
    if ai_client.provider != "none":
        with st.spinner("正在进行AI增强分析..."):
            texts = [
                (news.get('original_title') or news.get('title', '')) + " " +
                (news.get('original_content') or news.get('content', ''))
                for news in cleaned_news[:100]
            ]
            try:
                ai_scores = ai_client.classify_sentiment(texts)
                for item, score in zip(analyzed_news, ai_scores):
                    item['ai_sentiment_score'] = score
                st.success(f"✅ AI分析完成！分析了 {len(ai_scores)} 条文本")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"AI分析失败：{exc}")

    ai_summary: Dict[str, Any] = {}
    if ai_scores:
        ai_summary = {
            "average": sum(ai_scores) / len(ai_scores),
            "maximum": max(ai_scores),
            "minimum": min(ai_scores),
            "model": ai_client.model or ai_client.provider
        }

    # 6️⃣ 生成图表资源
    chart_paths = generate_chart_assets(analyzed_news, trend_results)

    # 保存状态
    st.session_state["news"] = aggregated_news
    st.session_state["cleaned_news"] = cleaned_news
    st.session_state["sentiment_results"] = analyzed_news
    st.session_state["sentiment_summary"] = sentiment_summary
    st.session_state["trend_results"] = trend_results
    st.session_state["trend_summary"] = trend_summary
    st.session_state["chart_paths"] = chart_paths
    st.session_state["ai_summary"] = ai_summary
    st.session_state["data_source"] = data_source
    st.session_state["selected_categories"] = selected_categories
    st.session_state["local_data_preview"] = local_preview.head(20) if isinstance(local_preview, pd.DataFrame) else None
    st.session_state["generated_pdf_path"] = ""
    st.session_state["generated_docx_path"] = ""

    st.success("🎉 分析完成！结果已保存到 results/ 文件夹")


def render_ai_summary(ai_summary: Optional[Dict[str, Any]]) -> None:
    if not ai_summary:
        return

    st.markdown("---")
    st.subheader("🧠 AI增强分析摘要")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("平均情绪", f"{ai_summary.get('average', 0):.3f}")
    col2.metric("最高情绪", f"{ai_summary.get('maximum', 0):.3f}")
    col3.metric("最低情绪", f"{ai_summary.get('minimum', 0):.3f}")
    col4.metric("使用模型", ai_summary.get("model", "-"))


def render_local_preview(preview_df: Optional[pd.DataFrame]) -> None:
    if preview_df is None or preview_df.empty:
        return

    st.markdown("---")
    st.subheader("📂 本地数据预览（前20行）")
    st.dataframe(preview_df)


def render_report_exports() -> None:
    sentiment_summary = st.session_state.get("sentiment_summary")
    if not sentiment_summary:
        return

    trend_summary = st.session_state.get("trend_summary", {})
    analyzed_news = st.session_state.get("sentiment_results", [])
    trend_results = st.session_state.get("trend_results", {})
    chart_paths = st.session_state.get("chart_paths", {})

    st.markdown("---")
    st.subheader("📄 报告导出")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 生成PDF报告", key="export_pdf_btn"):
            try:
                pdf_path = PDFReportGenerator().create_report(
                    sentiment_summary,
                    trend_summary,
                    analyzed_news,
                    trend_results,
                    chart_paths=chart_paths
                )
                st.session_state["generated_pdf_path"] = pdf_path
                st.success(f"✅ PDF报告已生成: {pdf_path}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF生成失败: {exc}")

        pdf_path = st.session_state.get("generated_pdf_path")
        if pdf_path and Path(pdf_path).exists():
            with open(pdf_path, "rb") as pdf_file:
                st.download_button(
                    "下载PDF报告",
                    data=pdf_file.read(),
                    file_name=Path(pdf_path).name,
                    mime="application/pdf",
                    key="download_pdf_button"
                )

    with col2:
        if st.button("📝 生成DOCX报告", key="export_docx_btn"):
            try:
                docx_path = DOCXReportGenerator().create_report(
                    sentiment_summary,
                    trend_summary,
                    analyzed_news,
                    trend_results,
                    chart_paths=chart_paths
                )
                st.session_state["generated_docx_path"] = docx_path
                st.success(f"✅ DOCX报告已生成: {docx_path}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"DOCX生成失败: {exc}")

        docx_path = st.session_state.get("generated_docx_path")
        if docx_path and Path(docx_path).exists():
            with open(docx_path, "rb") as docx_file:
                st.download_button(
                    "下载DOCX报告",
                    data=docx_file.read(),
                    file_name=Path(docx_path).name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="download_docx_button"
                )


def display_results() -> None:
    sentiment_summary = st.session_state.get("sentiment_summary")
    if not sentiment_summary:
        st.info("请先配置参数并运行分析流程。")
        return

    trend_summary = st.session_state.get("trend_summary", {})
    analyzed_news = st.session_state.get("sentiment_results", [])
    trend_results = st.session_state.get("trend_results", {})
    chart_paths = st.session_state.get("chart_paths", {})

    dashboard = DashboardManager()
    dashboard.render_complete_dashboard(
        sentiment_summary,
        trend_summary,
        analyzed_news,
        trend_results,
        chart_paths
    )

    render_ai_summary(st.session_state.get("ai_summary"))
    render_local_preview(st.session_state.get("local_data_preview"))
    render_report_exports()


def main():
    st.set_page_config(page_title="MarketPulse", layout="wide")
    ensure_dirs()
    cfg = load_config()
    st.title("MarketPulse 智能市场分析仪表盘")

    state = st.session_state
    state.setdefault("selected_categories", DEFAULT_CATEGORIES)
    state.setdefault("data_source", "online")
    state.setdefault("ai_provider", "auto")
    state.setdefault("ai_model", cfg.get("ai", {}).get("openai_model", ""))
    state.setdefault("ai_endpoint", "")
    state.setdefault("ai_api_key", "")
    state.setdefault("generated_pdf_path", "")
    state.setdefault("generated_docx_path", "")

    local_records: List[Dict[str, Any]] = []
    local_preview_df: Optional[pd.DataFrame] = None

    with st.sidebar:
        st.header("分析配置")

        data_source_labels = list(DATA_SOURCE_CHOICES.keys())
        current_source_label = next(
            (label for label, value in DATA_SOURCE_CHOICES.items() if value == state.get("data_source", "online")),
            data_source_labels[0]
        )
        data_source_label = st.selectbox(
            "数据源选择",
            data_source_labels,
            index=data_source_labels.index(current_source_label)
        )
        data_source = DATA_SOURCE_CHOICES[data_source_label]

        category_options = list(DEFAULT_CATEGORIES)
        selected_categories = st.multiselect(
            "新闻类别",
            category_options,
            default=state.get("selected_categories", DEFAULT_CATEGORIES)
        )
        if not selected_categories:
            st.warning("至少选择一个类别，已默认选择全部。")
            selected_categories = DEFAULT_CATEGORIES

        if data_source in {"local", "hybrid"}:
            st.caption("支持CSV、XLS/XLSX或JSON格式，需包含标题、内容等字段。")
            uploaded_file = st.file_uploader(
                "上传本地数据文件",
                type=["csv", "xls", "xlsx", "json"],
                key="local_uploader"
            )
            if uploaded_file is not None:
                local_records, local_preview_df = load_local_table(uploaded_file)
                st.caption(f"已读取 {len(local_records)} 条本地数据。")
            else:
                local_records, local_preview_df = [], None

        ai_labels = list(AI_PROVIDER_CHOICES.keys())
        current_ai_label = next(
            (label for label, value in AI_PROVIDER_CHOICES.items() if value == state.get("ai_provider", "auto")),
            ai_labels[0]
        )
        ai_provider_label = st.selectbox(
            "AI模型提供方",
            ai_labels,
            index=ai_labels.index(current_ai_label)
        )
        ai_provider = AI_PROVIDER_CHOICES[ai_provider_label]

        ai_model = state.get("ai_model") or cfg.get("ai", {}).get(
            "openai_model" if ai_provider == "openai" else "hf_model", ""
        )
        ai_endpoint = state.get("ai_endpoint", "")
        ai_api_key = state.get("ai_api_key", "")

        if ai_provider in {"openai", "huggingface"}:
            default_model = cfg.get("ai", {}).get(
                "openai_model" if ai_provider == "openai" else "hf_model", ""
            )
            ai_model = st.text_input("模型名称", value=ai_model or default_model, key="ai_model_input")

        if ai_provider == "openai":
            ai_api_key = st.text_input("OpenAI API Key", value=ai_api_key, type="password", key="ai_api_key_input")
            ai_endpoint = st.text_input("API 接口地址 (可选)", value=ai_endpoint, key="ai_endpoint_input")
        elif ai_provider == "huggingface":
            ai_api_key = st.text_input("HuggingFace Token (可选)", value=ai_api_key, type="password", key="ai_api_key_input")
            ai_endpoint = st.text_input("推理端点 (可选)", value=ai_endpoint, key="ai_endpoint_input")
        elif ai_provider == "custom":
            ai_endpoint = st.text_input("自定义接口地址", value=ai_endpoint, key="ai_endpoint_input")
            ai_api_key = st.text_input("接口密钥 (可选)", value=ai_api_key, type="password", key="ai_api_key_input")
            ai_model = st.text_input("模型标识 (可选)", value=ai_model, key="ai_model_input_custom")

        st.markdown("---")
        st.caption("提示：若选择自动检测或禁用AI，将使用默认设置或跳过AI分析。")

    state["data_source"] = data_source
    state["selected_categories"] = selected_categories
    state["ai_provider"] = ai_provider
    state["ai_model"] = ai_model
    state["ai_endpoint"] = ai_endpoint
    state["ai_api_key"] = ai_api_key

    ai_config: Dict[str, Any] = {"provider": ai_provider}
    if ai_provider in {"openai", "huggingface"} and ai_model:
        ai_config["model"] = ai_model
    if ai_provider in {"openai", "huggingface", "custom"} and ai_api_key:
        ai_config["api_key"] = ai_api_key
    if ai_provider in {"openai", "huggingface", "custom"} and ai_endpoint:
        ai_config["endpoint"] = ai_endpoint

    st.markdown("### 🔄 运行分析")
    if st.button("运行分析", type="primary", use_container_width=True):
        run_pipeline(
            data_source,
            selected_categories,
            local_records,
            ai_config,
            local_preview_df
        )

    display_results()


if __name__ == "__main__":
    main()
