import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from datetime import datetime


class ChartGenerator:
    """图表生成器 - 生成各种可视化图表"""
    
    def __init__(self):
        self.color_scheme = {
            'positive': '#2E8B57',  # 海绿色
            'negative': '#DC143C',  # 深红色
            'neutral': '#4682B4',   # 钢蓝色
            'primary': '#1f77b4',   # 蓝色
            'secondary': '#ff7f0e', # 橙色
            'background': '#f8f9fa'
        }
    
    def create_sentiment_distribution_chart(self, sentiment_data: List[Dict[str, Any]]) -> go.Figure:
        """
        创建情绪分布饼图
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            Plotly图表对象
        """
        if not sentiment_data:
            return self._create_empty_chart("无数据")
        
        # 统计情绪分布
        labels = [news.get('sentiment_label', 'neutral') for news in sentiment_data]
        label_counts = pd.Series(labels).value_counts()
        
        # 创建饼图
        fig = go.Figure(data=[go.Pie(
            labels=label_counts.index,
            values=label_counts.values,
            hole=0.3,
            marker_colors=[self.color_scheme[label] for label in label_counts.index]
        )])
        
        fig.update_layout(
            title="情绪分布统计",
            title_x=0.5,
            font=dict(size=14),
            showlegend=True,
            height=400
        )
        
        return fig
    
    def create_sentiment_timeline_chart(self, sentiment_data: List[Dict[str, Any]]) -> go.Figure:
        """
        创建情绪时间线图表
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            Plotly图表对象
        """
        if not sentiment_data:
            return self._create_empty_chart("无数据")
        
        # 准备数据
        df_data = []
        for news in sentiment_data:
            publish_time = news.get('publish_time', datetime.now().strftime('%Y-%m-%d'))
            sentiment_score = news.get('sentiment_score', 0)
            
            try:
                if isinstance(publish_time, str):
                    date_obj = datetime.strptime(publish_time[:10], '%Y-%m-%d')
                else:
                    date_obj = publish_time
            except:
                date_obj = datetime.now()
            
            df_data.append({
                'date': date_obj,
                'sentiment': sentiment_score,
                'title': news.get('title', '')[:50]
            })
        
        df = pd.DataFrame(df_data)
        df = df.sort_values('date')
        
        # 创建散点图
        fig = go.Figure()
        
        # 添加散点
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['sentiment'],
            mode='markers',
            marker=dict(
                size=8,
                color=df['sentiment'],
                colorscale='RdYlGn',
                showscale=True,
                colorbar=dict(title="情绪得分")
            ),
            text=df['title'],
            hovertemplate='<b>%{text}</b><br>日期: %{x}<br>情绪得分: %{y:.3f}<extra></extra>',
            name='新闻情绪'
        ))
        
        # 添加趋势线
        if len(df) > 1:
            z = np.polyfit(range(len(df)), df['sentiment'], 1)
            p = np.poly1d(z)
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=p(range(len(df))),
                mode='lines',
                line=dict(color='red', width=2, dash='dash'),
                name='趋势线'
            ))
        
        fig.update_layout(
            title="情绪时间线分析",
            xaxis_title="日期",
            yaxis_title="情绪得分",
            height=500,
            hovermode='closest'
        )
        
        return fig
    
    def create_trend_prediction_chart(self, trend_data: Dict[str, Any]) -> go.Figure:
        """
        创建趋势预测图表
        
        Args:
            trend_data: 趋势预测数据
            
        Returns:
            Plotly图表对象
        """
        if 'error' in trend_data:
            return self._create_empty_chart(f"预测失败: {trend_data['error']}")
        
        historical = trend_data.get('historical_data', [])
        predictions = trend_data.get('predictions', [])
        
        if not historical and not predictions:
            return self._create_empty_chart("无预测数据")
        
        fig = go.Figure()
        
        # 添加历史数据
        if historical:
            hist_df = pd.DataFrame(historical)
            hist_df['ds'] = pd.to_datetime(hist_df['ds'])
            
            fig.add_trace(go.Scatter(
                x=hist_df['ds'],
                y=hist_df['y'],
                mode='lines+markers',
                name='历史数据',
                line=dict(color=self.color_scheme['primary'], width=2),
                marker=dict(size=6)
            ))
        
        # 添加预测数据
        if predictions:
            pred_df = pd.DataFrame(predictions)
            pred_df['ds'] = pd.to_datetime(pred_df['ds'])
            
            fig.add_trace(go.Scatter(
                x=pred_df['ds'],
                y=pred_df['yhat'],
                mode='lines+markers',
                name='预测值',
                line=dict(color=self.color_scheme['secondary'], width=2, dash='dash'),
                marker=dict(size=6)
            ))
            
            # 添加置信区间
            fig.add_trace(go.Scatter(
                x=pred_df['ds'],
                y=pred_df['yhat_upper'],
                mode='lines',
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ))
            
            fig.add_trace(go.Scatter(
                x=pred_df['ds'],
                y=pred_df['yhat_lower'],
                mode='lines',
                line=dict(width=0),
                fill='tonexty',
                fillcolor='rgba(255, 127, 14, 0.2)',
                name='置信区间',
                hoverinfo='skip'
            ))
        
        fig.update_layout(
            title="市场情绪趋势预测",
            xaxis_title="日期",
            yaxis_title="情绪得分",
            height=500,
            hovermode='x unified'
        )
        
        return fig
    
    def create_sentiment_heatmap(self, sentiment_data: List[Dict[str, Any]]) -> go.Figure:
        """
        创建情绪热力图
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            Plotly图表对象
        """
        if not sentiment_data:
            return self._create_empty_chart("无数据")
        
        # 准备数据
        df_data = []
        for news in sentiment_data:
            publish_time = news.get('publish_time', datetime.now().strftime('%Y-%m-%d'))
            sentiment_score = news.get('sentiment_score', 0)
            
            try:
                if isinstance(publish_time, str):
                    date_obj = datetime.strptime(publish_time[:10], '%Y-%m-%d')
                else:
                    date_obj = datetime.now()
            except:
                date_obj = datetime.now()
            
            df_data.append({
                'date': date_obj.date(),
                'hour': date_obj.hour,
                'sentiment': sentiment_score
            })
        
        df = pd.DataFrame(df_data)
        
        if df.empty:
            return self._create_empty_chart("无数据")
        
        # 按日期和小时聚合
        heatmap_data = df.groupby(['date', 'hour'])['sentiment'].mean().reset_index()
        
        # 创建透视表
        pivot_table = heatmap_data.pivot(index='date', columns='hour', values='sentiment')
        
        # 创建热力图
        fig = go.Figure(data=go.Heatmap(
            z=pivot_table.values,
            x=pivot_table.columns,
            y=pivot_table.index,
            colorscale='RdYlGn',
            colorbar=dict(title="情绪得分")
        ))
        
        fig.update_layout(
            title="情绪热力图",
            xaxis_title="小时",
            yaxis_title="日期",
            height=400
        )
        
        return fig
    
    def create_keywords_wordcloud_data(self, sentiment_data: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        创建词云数据
        
        Args:
            sentiment_data: 情绪分析数据
            
        Returns:
            词频字典
        """
        from collections import Counter
        import jieba
        
        # 提取所有文本
        all_text = ""
        for news in sentiment_data:
            title = news.get('title', '')
            content = news.get('content', '')
            all_text += f" {title} {content}"
        
        # 分词并统计词频
        words = jieba.lcut(all_text)
        word_freq = Counter(words)
        
        # 过滤停用词和短词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        
        filtered_words = {word: freq for word, freq in word_freq.items() 
                         if len(word) > 1 and word not in stop_words and freq > 1}
        
        return dict(list(filtered_words.items())[:50])  # 返回前50个词
    
    def create_summary_dashboard(self, sentiment_summary: Dict[str, Any], 
                               trend_summary: Dict[str, Any]) -> go.Figure:
        """
        创建综合仪表盘
        
        Args:
            sentiment_summary: 情绪分析摘要
            trend_summary: 趋势分析摘要
            
        Returns:
            Plotly图表对象
        """
        # 创建子图
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('情绪分布', '趋势预测', '情绪得分', '分析摘要'),
            specs=[[{"type": "pie"}, {"type": "scatter"}],
                   [{"type": "bar"}, {"type": "table"}]]
        )
        
        # 情绪分布饼图
        if sentiment_summary.get('sentiment_distribution'):
            dist = sentiment_summary['sentiment_distribution']
            fig.add_trace(go.Pie(
                labels=list(dist.keys()),
                values=list(dist.values()),
                name="情绪分布"
            ), row=1, col=1)
        
        # 趋势预测散点图
        if trend_summary.get('status') == 'success':
            fig.add_trace(go.Scatter(
                x=[1, 2, 3],
                y=[0.1, 0.2, 0.3],
                mode='lines+markers',
                name='趋势预测'
            ), row=1, col=2)
        
        # 情绪得分柱状图
        if sentiment_summary.get('avg_sentiment') is not None:
            fig.add_trace(go.Bar(
                x=['平均情绪得分'],
                y=[sentiment_summary['avg_sentiment']],
                name='平均得分'
            ), row=2, col=1)
        
        # 分析摘要表格
        summary_data = [
            ['总新闻数', sentiment_summary.get('total_news', 0)],
            ['积极新闻', sentiment_summary.get('positive_count', 0)],
            ['消极新闻', sentiment_summary.get('negative_count', 0)],
            ['趋势方向', trend_summary.get('trend_direction', 'unknown')],
            ['预测置信度', f"{trend_summary.get('confidence', 0):.3f}"]
        ]
        
        fig.add_trace(go.Table(
            header=dict(values=['指标', '数值']),
            cells=dict(values=list(zip(*summary_data)))
        ), row=2, col=2)
        
        fig.update_layout(
            title="MarketPulse 综合分析仪表盘",
            height=800,
            showlegend=True
        )
        
        return fig
    
    def _create_empty_chart(self, message: str) -> go.Figure:
        """创建空图表"""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False),
            height=300
        )
        return fig
    
    def save_chart(self, fig: go.Figure, file_path: str, format: str = 'html'):
        """
        保存图表
        
        Args:
            fig: 图表对象
            file_path: 保存路径
            format: 保存格式 ('html', 'png', 'pdf')
        """
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'html':
            fig.write_html(file_path)
        elif format == 'png':
            fig.write_image(file_path, width=1200, height=800)
        elif format == 'pdf':
            fig.write_image(file_path, format='pdf', width=1200, height=800)
        
        print(f"✅ 图表已保存到 {file_path}")


def create_sentiment_chart(sentiment_data: List[Dict[str, Any]]) -> go.Figure:
    """
    便捷函数：创建情绪分析图表
    
    Args:
        sentiment_data: 情绪分析数据
        
    Returns:
        图表对象
    """
    generator = ChartGenerator()
    return generator.create_sentiment_distribution_chart(sentiment_data)
