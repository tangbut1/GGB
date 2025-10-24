import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from .charts import ChartGenerator

# 设置企业级深色主题
pio.templates.default = "plotly_dark"


class DashboardManager:
    """仪表盘管理器 - 管理Streamlit仪表盘的显示和交互"""
    
    def __init__(self):
        self.chart_generator = ChartGenerator()
    
    def render_sentiment_overview(self, sentiment_summary: Dict[str, Any]):
        """
        渲染情绪分析概览
        
        Args:
            sentiment_summary: 情绪分析摘要
        """
        st.subheader("📊 情绪分析概览")
        
        # 创建指标卡片
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="总新闻数",
                value=sentiment_summary.get('total_news', 0),
                delta=None
            )
        
        with col2:
            st.metric(
                label="积极新闻",
                value=sentiment_summary.get('positive_count', 0),
                delta=f"{sentiment_summary.get('positive_count', 0) / max(sentiment_summary.get('total_news', 1), 1) * 100:.1f}%"
            )
        
        with col3:
            st.metric(
                label="消极新闻",
                value=sentiment_summary.get('negative_count', 0),
                delta=f"{sentiment_summary.get('negative_count', 0) / max(sentiment_summary.get('total_news', 1), 1) * 100:.1f}%"
            )
        
        with col4:
            avg_sentiment = sentiment_summary.get('avg_sentiment', 0)
            sentiment_emoji = "😊" if avg_sentiment > 0.1 else "😐" if avg_sentiment > -0.1 else "😞"
            st.metric(
                label="平均情绪",
                value=f"{avg_sentiment:.3f}",
                delta=sentiment_emoji
            )
    
    def render_trend_analysis(self, trend_summary: Dict[str, Any]):
        """
        渲染趋势分析
        
        Args:
            trend_summary: 趋势分析摘要
        """
        st.subheader("📈 趋势分析")
        
        if trend_summary.get('status') == 'error':
            st.error(f"趋势分析失败: {trend_summary.get('message', '未知错误')}")
            return
        
        col1, col2 = st.columns(2)
        
        with col1:
            trend_direction = trend_summary.get('trend_direction', 'neutral')
            confidence = trend_summary.get('confidence', 0)
            
            # 趋势方向指示器
            if trend_direction == 'positive':
                st.success("📈 积极趋势")
                st.write("市场情绪呈上升趋势，建议关注投资机会")
            elif trend_direction == 'negative':
                st.error("📉 消极趋势")
                st.write("市场情绪呈下降趋势，建议谨慎投资")
            else:
                st.info("➡️ 稳定趋势")
                st.write("市场情绪相对稳定，建议保持观望")
        
        with col2:
            st.metric("预测置信度", f"{confidence:.1%}")
            st.metric("数据点数", trend_summary.get('data_points', 0))
            st.metric("预测天数", trend_summary.get('forecast_periods', 0))
    
    def render_charts_section(self, sentiment_data: List[Dict[str, Any]], 
                            trend_data: Dict[str, Any]):
        """
        渲染图表区域
        
        Args:
            sentiment_data: 情绪分析数据
            trend_data: 趋势预测数据
        """
        st.subheader("📊 可视化图表")
        st.markdown("---")
        
        # 创建标签页
        tab1, tab2, tab3, tab4 = st.tabs(["情绪分布", "时间线", "趋势预测", "热力图"])
        
        with tab1:
            # 情绪分布饼图
            try:
                fig_pie = self.chart_generator.create_sentiment_distribution_chart(sentiment_data)
                st.plotly_chart(fig_pie, use_container_width=True, key="sentiment_distribution_chart")
            except Exception as e:
                st.error(f"情绪分布图绘制失败：{e}")
        
        with tab2:
            # 情绪时间线
            try:
                fig_timeline = self.chart_generator.create_sentiment_timeline_chart(sentiment_data)
                st.plotly_chart(fig_timeline, use_container_width=True, key="sentiment_timeline_chart")
            except Exception as e:
                st.error(f"情绪时间线绘制失败：{e}")
        
        with tab3:
            # 趋势预测图
            try:
                fig_trend = self.chart_generator.create_trend_prediction_chart(trend_data)
                st.plotly_chart(fig_trend, use_container_width=True, key="trend_prediction_chart")
            except Exception as e:
                st.error(f"趋势预测图绘制失败：{e}")
        
        with tab4:
            # 情绪热力图
            try:
                fig_heatmap = self.chart_generator.create_sentiment_heatmap(sentiment_data)
                st.plotly_chart(fig_heatmap, use_container_width=True, key="sentiment_heatmap_chart")
            except Exception as e:
                st.error(f"情绪热力图绘制失败：{e}")
        
        st.markdown("---")
        st.info("✅ 图表渲染完成，可在上方切换查看不同分析结果。")
    
    def render_news_details(self, analyzed_news: List[Dict[str, Any]], 
                          max_display: int = 10):
        """
        渲染新闻详情
        
        Args:
            analyzed_news: 已分析的新闻数据
            max_display: 最大显示数量
        """
        st.subheader("📰 新闻详情分析")
        
        if not analyzed_news:
            st.info("暂无新闻数据")
            return
        
        # 创建筛选器
        col1, col2 = st.columns(2)
        
        with col1:
            sentiment_filter = st.selectbox(
                "情绪筛选",
                ["全部", "积极", "消极", "中性"],
                key="sentiment_filter"
            )
        
        with col2:
            sort_by = st.selectbox(
                "排序方式",
                ["时间", "情绪得分", "置信度"],
                key="sort_by"
            )
        
        # 筛选数据
        filtered_news = analyzed_news.copy()
        
        if sentiment_filter != "全部":
            sentiment_map = {"积极": "positive", "消极": "negative", "中性": "neutral"}
            filtered_news = [news for news in filtered_news 
                           if news.get('sentiment_label') == sentiment_map[sentiment_filter]]
        
        # 排序数据
        if sort_by == "情绪得分":
            filtered_news.sort(key=lambda x: x.get('sentiment_score', 0), reverse=True)
        elif sort_by == "置信度":
            filtered_news.sort(key=lambda x: x.get('sentiment_confidence', 0), reverse=True)
        else:  # 时间排序
            filtered_news.sort(key=lambda x: x.get('publish_time', ''), reverse=True)
        
        # 显示新闻
        for i, news in enumerate(filtered_news[:max_display]):
            with st.expander(f"新闻 {i+1}: {news.get('title', '无标题')[:60]}..."):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    sentiment_score = news.get('sentiment_score', 0)
                    sentiment_label = news.get('sentiment_label', 'neutral')
                    
                    # 情绪得分颜色
                    if sentiment_score > 0.1:
                        color = "🟢"
                    elif sentiment_score < -0.1:
                        color = "🔴"
                    else:
                        color = "🟡"
                    
                    st.write(f"**情绪得分**: {color} {sentiment_score:.3f}")
                    st.write(f"**情绪标签**: {sentiment_label}")
                
                with col2:
                    confidence = news.get('sentiment_confidence', 0)
                    st.write(f"**置信度**: {confidence:.3f}")
                    st.write(f"**发布时间**: {news.get('publish_time', '未知')}")
                
                with col3:
                    st.write(f"**来源**: {news.get('source', '未知')}")
                    if news.get('url'):
                        st.write(f"**链接**: [查看原文]({news.get('url')})")
                
                # 新闻内容
                content = news.get('content', '无内容')
                if content:
                    st.write("**内容摘要**:")
                    st.write(content[:300] + "..." if len(content) > 300 else content)
    
    def render_keywords_analysis(self, sentiment_data: List[Dict[str, Any]]):
        """
        渲染关键词分析
        
        Args:
            sentiment_data: 情绪分析数据
        """
        st.subheader("🔍 关键词分析")
        
        # 生成词云数据
        wordcloud_data = self.chart_generator.create_keywords_wordcloud_data(sentiment_data)
        
        if not wordcloud_data:
            st.info("暂无关键词数据")
            return
        
        # 显示关键词频率
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**高频关键词**")
            for word, freq in list(wordcloud_data.items())[:20]:
                st.write(f"• {word}: {freq}次")
        
        with col2:
            # 创建关键词频率柱状图
            words = list(wordcloud_data.keys())[:15]
            freqs = list(wordcloud_data.values())[:15]
            
            fig = go.Figure(data=[
                go.Bar(x=words, y=freqs, marker_color='lightblue')
            ])
            
            fig.update_layout(
                title="关键词频率分布",
                xaxis_title="关键词",
                yaxis_title="出现次数",
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True, key="keywords_frequency_chart")
    
    def render_export_section(self, sentiment_summary: Dict[str, Any], 
                            trend_summary: Dict[str, Any],
                            analyzed_news: List[Dict[str, Any]]):
        """
        渲染导出功能
        
        Args:
            sentiment_summary: 情绪分析摘要
            trend_summary: 趋势分析摘要
            analyzed_news: 已分析的新闻数据
        """
        st.subheader("📄 报告导出")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 生成PDF报告", key="export_pdf"):
                st.info("PDF报告生成功能将在后续版本中实现")
        
        with col2:
            if st.button("📝 生成DOCX报告", key="export_docx"):
                st.info("DOCX报告生成功能将在后续版本中实现")
        
        # 显示导出选项
        st.write("**可导出的数据:**")
        st.write("• 情绪分析摘要")
        st.write("• 趋势预测结果")
        st.write("• 新闻详情数据")
        st.write("• 可视化图表")
    
    def render_complete_dashboard(self, sentiment_summary: Dict[str, Any],
                                trend_summary: Dict[str, Any],
                                analyzed_news: List[Dict[str, Any]],
                                trend_data: Dict[str, Any]):
        """
        渲染完整仪表盘
        
        Args:
            sentiment_summary: 情绪分析摘要
            trend_summary: 趋势分析摘要
            analyzed_news: 已分析的新闻数据
            trend_data: 趋势预测数据
        """
        # 页面标题
        st.title("🎯 MarketPulse 智能市场分析仪表盘")
        st.markdown("---")
        
        # 情绪分析概览
        self.render_sentiment_overview(sentiment_summary)
        st.markdown("---")
        
        # 趋势分析
        self.render_trend_analysis(trend_summary)
        st.markdown("---")
        
        # 图表区域
        self.render_charts_section(analyzed_news, trend_data)
        st.markdown("---")
        
        # 新闻详情
        self.render_news_details(analyzed_news)
        st.markdown("---")
        
        # 关键词分析
        self.render_keywords_analysis(analyzed_news)
        st.markdown("---")
        
        # 导出功能
        self.render_export_section(sentiment_summary, trend_summary, analyzed_news)


def create_dashboard(sentiment_summary: Dict[str, Any],
                    trend_summary: Dict[str, Any],
                    analyzed_news: List[Dict[str, Any]],
                    trend_data: Dict[str, Any]):
    """
    便捷函数：创建仪表盘
    
    Args:
        sentiment_summary: 情绪分析摘要
        trend_summary: 趋势分析摘要
        analyzed_news: 已分析的新闻数据
        trend_data: 趋势预测数据
    """
    dashboard = DashboardManager()
    dashboard.render_complete_dashboard(
        sentiment_summary, trend_summary, analyzed_news, trend_data
    )
