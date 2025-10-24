import json
from pathlib import Path

import streamlit as st

from src.collect.news_collector import NewsCollector
from src.preprocess.cleaner import DataCleaner, clean_text
from src.analysis.sentiment_analysis import SentimentAnalyzer
from src.analysis.trend_prediction import TrendPredictor
from src.visualization.charts import ChartGenerator
from src.visualization.dashboard import DashboardManager
from src.report.export_pdf import PDFReportGenerator
from src.report.export_doc import DOCXReportGenerator
from src.ai_integration import AIClient


def load_config():
    import yaml
    cfg_path = Path(__file__).parent / "src" / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs():
    for p in ["results/charts", "results/logs", "results/reports", "data/processed"]:
        Path(p).mkdir(parents=True, exist_ok=True)


def run_pipeline():
    st.session_state.setdefault("news", [])
    st.session_state.setdefault("cleaned_news", [])
    st.session_state.setdefault("sentiment_results", [])
    st.session_state.setdefault("sentiment_summary", {})
    st.session_state.setdefault("trend_results", {})
    st.session_state.setdefault("trend_summary", {})

    st.write("🚀 MarketPulse: 数据分析流程启动...")
    
    # 1️⃣ 数据采集
    with st.spinner("正在采集新闻数据..."):
        collector = NewsCollector()
        news_list = collector.run_full_pipeline()
        if not news_list:
            st.error("❌ 新闻采集失败，请检查网络连接")
            return
        st.success(f"✅ 已采集 {len(news_list)} 条财经新闻！")
    
    # 2️⃣ 数据清洗
    with st.spinner("正在清洗数据..."):
        cleaner = DataCleaner()
        cleaned_news = cleaner.clean_news_batch(news_list)
        cleaner.save_cleaned_data(cleaned_news)
        st.success(f"✅ 已清洗 {len(cleaned_news)} 条新闻数据！")
    
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
        trend_predictor.save_prediction_results(trend_results)
        st.success(f"✅ 趋势预测完成！趋势方向: {trend_summary.get('trend_direction', 'unknown')}")
    
    # 5️⃣ AI增强分析（可选）
    cfg = load_config()
    provider = cfg.get("ai", {}).get("provider", "auto")
    if provider != "none":
        with st.spinner("正在进行AI增强分析..."):
            if provider == "auto":
                ai = AIClient.auto_detect()
            else:
                ai = AIClient(provider=provider, model=cfg.get("ai", {}).get("openai_model"))
            
            # 提取文本进行AI分析
            texts = [f"{news.get('title', '')} {news.get('content', '')}" for news in cleaned_news[:50]]
            ai_scores = ai.classify_sentiment(texts)
            st.success(f"✅ AI分析完成！分析了 {len(ai_scores)} 条文本")
    
    # 保存状态
    st.session_state["news"] = news_list
    st.session_state["cleaned_news"] = cleaned_news
    st.session_state["sentiment_results"] = analyzed_news
    st.session_state["sentiment_summary"] = sentiment_summary
    st.session_state["trend_results"] = trend_results
    st.session_state["trend_summary"] = trend_summary
    
    # 使用仪表盘管理器显示完整结果
    dashboard = DashboardManager()
    dashboard.render_complete_dashboard(
        sentiment_summary, trend_summary, analyzed_news, trend_results
    )
    
    st.info("🎉 分析完成！结果已保存到 results/ 文件夹")


def main():
    st.set_page_config(page_title="MarketPulse", layout="wide")
    ensure_dirs()
    st.title("MarketPulse 智能市场分析仪表盘")

    if st.button("运行全流程"):
        run_pipeline()

    # 显示历史结果
    if st.session_state.get("sentiment_summary"):
        st.write("### 📈 分析结果概览")
        summary = st.session_state["sentiment_summary"]
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("总新闻数", summary.get('total_news', 0))
        with col2:
            st.metric("积极新闻", summary.get('positive_count', 0))
        with col3:
            st.metric("消极新闻", summary.get('negative_count', 0))
        with col4:
            st.metric("平均情绪", f"{summary.get('avg_sentiment', 0):.3f}")
        
        # 添加报告导出按钮
        st.write("### 📄 报告导出")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 生成PDF报告", key="export_pdf_btn"):
                try:
                    pdf_generator = PDFReportGenerator()
                    pdf_path = pdf_generator.create_report(
                        st.session_state["sentiment_summary"],
                        st.session_state.get("trend_summary", {}),
                        st.session_state.get("sentiment_results", []),
                        st.session_state.get("trend_results", {})
                    )
                    st.success(f"✅ PDF报告已生成: {pdf_path}")
                except Exception as e:
                    st.error(f"PDF生成失败: {e}")
        
        with col2:
            if st.button("📝 生成DOCX报告", key="export_docx_btn"):
                try:
                    docx_generator = DOCXReportGenerator()
                    docx_path = docx_generator.create_report(
                        st.session_state["sentiment_summary"],
                        st.session_state.get("trend_summary", {}),
                        st.session_state.get("sentiment_results", []),
                        st.session_state.get("trend_results", {})
                    )
                    st.success(f"✅ DOCX报告已生成: {docx_path}")
                except Exception as e:
                    st.error(f"DOCX生成失败: {e}")
    
    if st.session_state.get("news"):
        st.write("### 📰 最新新闻样例")
        for i, n in enumerate(st.session_state["news"][:5]):
            st.write(f"{i+1}. {n.get('title', '无标题')}")


if __name__ == "__main__":
    main()
