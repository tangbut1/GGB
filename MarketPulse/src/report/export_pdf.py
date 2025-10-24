import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


class PDFReportGenerator:
    """PDF报告生成器 - 生成专业的分析报告"""
    
    def __init__(self):
        self.page_width = 595  # A4宽度
        self.page_height = 842  # A4高度
        self.margin = 50
        self.line_height = 20
        self.current_y = 0
    
    def create_report(self, sentiment_summary: Dict[str, Any],
                     trend_summary: Dict[str, Any],
                     analyzed_news: List[Dict[str, Any]],
                     trend_data: Dict[str, Any],
                     output_path: str = "results/reports/market_analysis_report.pdf") -> str:
        """
        创建完整的PDF报告
        
        Args:
            sentiment_summary: 情绪分析摘要
            trend_summary: 趋势分析摘要
            analyzed_news: 已分析的新闻数据
            trend_data: 趋势预测数据
            output_path: 输出路径
            
        Returns:
            生成的PDF文件路径
        """
        # 创建PDF文档
        doc = fitz.open()
        page = doc.new_page(width=self.page_width, height=self.page_height)
        
        # 重置位置
        self.current_y = self.margin
        
        # 添加标题页
        self._add_title_page(page, sentiment_summary)
        
        # 添加目录
        self._add_table_of_contents(page)
        
        # 添加执行摘要
        self._add_executive_summary(page, sentiment_summary, trend_summary)
        
        # 添加情绪分析详情
        self._add_sentiment_analysis(page, sentiment_summary, analyzed_news)
        
        # 添加趋势预测
        self._add_trend_prediction(page, trend_summary, trend_data)
        
        # 添加新闻详情
        self._add_news_details(page, analyzed_news)
        
        # 添加结论和建议
        self._add_conclusions(page, sentiment_summary, trend_summary)
        
        # 保存文档
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        doc.close()
        
        print(f"✅ PDF报告已生成: {output_path}")
        return output_path
    
    def _add_title_page(self, page, sentiment_summary: Dict[str, Any]):
        """添加标题页"""
        # 主标题
        title_rect = fitz.Rect(self.margin, 200, self.page_width - self.margin, 250)
        page.insert_textbox(title_rect, "MarketPulse 智能市场分析报告", 
                           fontsize=24, color=(0, 0, 0), align=1)
        
        # 副标题
        subtitle_rect = fitz.Rect(self.margin, 280, self.page_width - self.margin, 320)
        page.insert_textbox(subtitle_rect, "基于AI的市场情绪分析与趋势预测", 
                           fontsize=16, color=(0.2, 0.2, 0.2), align=1)
        
        # 生成时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        time_rect = fitz.Rect(self.margin, 350, self.page_width - self.margin, 380)
        page.insert_textbox(time_rect, f"报告生成时间: {current_time}", 
                           fontsize=12, color=(0.4, 0.4, 0.4), align=1)
        
        # 关键指标
        self.current_y = 450
        self._add_section_title(page, "关键指标概览")
        
        # 指标数据
        metrics = [
            ("总新闻数", str(sentiment_summary.get('total_news', 0))),
            ("积极新闻", str(sentiment_summary.get('positive_count', 0))),
            ("消极新闻", str(sentiment_summary.get('negative_count', 0))),
            ("平均情绪得分", f"{sentiment_summary.get('avg_sentiment', 0):.3f}")
        ]
        
        for i, (label, value) in enumerate(metrics):
            y_pos = 500 + i * 30
            page.insert_text((self.margin, y_pos), f"{label}: {value}", fontsize=12)
    
    def _add_table_of_contents(self, page):
        """添加目录"""
        self.current_y = self.margin
        
        self._add_section_title(page, "目录")
        
        toc_items = [
            "1. 执行摘要",
            "2. 情绪分析详情",
            "3. 趋势预测分析",
            "4. 新闻详情分析",
            "5. 结论与建议"
        ]
        
        for item in toc_items:
            self.current_y += self.line_height
            page.insert_text((self.margin + 20, self.current_y), item, fontsize=12)
    
    def _add_executive_summary(self, page, sentiment_summary: Dict[str, Any], 
                              trend_summary: Dict[str, Any]):
        """添加执行摘要"""
        self.current_y = self.margin
        
        self._add_section_title(page, "1. 执行摘要")
        
        # 情绪分析摘要
        total_news = sentiment_summary.get('total_news', 0)
        positive_count = sentiment_summary.get('positive_count', 0)
        negative_count = sentiment_summary.get('negative_count', 0)
        avg_sentiment = sentiment_summary.get('avg_sentiment', 0)
        
        summary_text = f"""
本报告基于对 {total_news} 条财经新闻的深度分析，通过多模型融合的情绪分析技术，
识别出积极新闻 {positive_count} 条，消极新闻 {negative_count} 条，
整体市场情绪得分为 {avg_sentiment:.3f}。
        """
        
        self._add_text_block(page, summary_text.strip())
        
        # 趋势分析摘要
        if trend_summary.get('status') == 'success':
            trend_direction = trend_summary.get('trend_direction', 'neutral')
            confidence = trend_summary.get('confidence', 0)
            
            trend_text = f"""
基于Prophet时间序列模型的趋势预测显示，市场情绪呈{trend_direction}趋势，
预测置信度为 {confidence:.1%}。
            """
            
            self._add_text_block(page, trend_text.strip())
    
    def _add_sentiment_analysis(self, page, sentiment_summary: Dict[str, Any], 
                               analyzed_news: List[Dict[str, Any]]):
        """添加情绪分析详情"""
        self.current_y = self.margin
        
        self._add_section_title(page, "2. 情绪分析详情")
        
        # 情绪分布统计
        dist = sentiment_summary.get('sentiment_distribution', {})
        sentiment_text = f"""
情绪分布统计:
• 积极新闻: {dist.get('positive', 0)} 条 ({dist.get('positive', 0) / max(sentiment_summary.get('total_news', 1), 1) * 100:.1f}%)
• 消极新闻: {dist.get('negative', 0)} 条 ({dist.get('negative', 0) / max(sentiment_summary.get('total_news', 1), 1) * 100:.1f}%)
• 中性新闻: {dist.get('neutral', 0)} 条 ({dist.get('neutral', 0) / max(sentiment_summary.get('total_news', 1), 1) * 100:.1f}%)
        """
        
        self._add_text_block(page, sentiment_text.strip())
        
        # 情绪得分分析
        avg_sentiment = sentiment_summary.get('avg_sentiment', 0)
        if avg_sentiment > 0.1:
            sentiment_analysis = "市场整体情绪偏向积极，投资者信心较强。"
        elif avg_sentiment < -0.1:
            sentiment_analysis = "市场整体情绪偏向消极，投资者信心不足。"
        else:
            sentiment_analysis = "市场整体情绪相对中性，投资者保持观望态度。"
        
        self._add_text_block(page, f"情绪分析: {sentiment_analysis}")
    
    def _add_trend_prediction(self, page, trend_summary: Dict[str, Any], 
                            trend_data: Dict[str, Any]):
        """添加趋势预测分析"""
        self.current_y = self.margin
        
        self._add_section_title(page, "3. 趋势预测分析")
        
        if trend_summary.get('status') == 'error':
            error_text = f"趋势预测失败: {trend_summary.get('message', '未知错误')}"
            self._add_text_block(page, error_text)
            return
        
        # 预测结果
        trend_direction = trend_summary.get('trend_direction', 'neutral')
        confidence = trend_summary.get('confidence', 0)
        data_points = trend_summary.get('data_points', 0)
        forecast_periods = trend_summary.get('forecast_periods', 0)
        
        prediction_text = f"""
基于 {data_points} 个历史数据点的Prophet模型预测:
• 趋势方向: {trend_direction}
• 预测置信度: {confidence:.1%}
• 预测天数: {forecast_periods} 天
        """
        
        self._add_text_block(page, prediction_text.strip())
        
        # 投资建议
        recommendation = trend_summary.get('recommendation', '')
        if recommendation:
            self._add_text_block(page, f"投资建议: {recommendation}")
    
    def _add_news_details(self, page, analyzed_news: List[Dict[str, Any]]):
        """添加新闻详情"""
        self.current_y = self.margin
        
        self._add_section_title(page, "4. 新闻详情分析")
        
        # 显示前10条重要新闻
        important_news = sorted(analyzed_news, 
                              key=lambda x: abs(x.get('sentiment_score', 0)), 
                              reverse=True)[:10]
        
        for i, news in enumerate(important_news, 1):
            title = news.get('title', '无标题')
            sentiment_score = news.get('sentiment_score', 0)
            sentiment_label = news.get('sentiment_label', 'neutral')
            confidence = news.get('sentiment_confidence', 0)
            
            news_text = f"""
新闻 {i}: {title}
情绪得分: {sentiment_score:.3f} ({sentiment_label})
置信度: {confidence:.3f}
            """
            
            self._add_text_block(page, news_text.strip())
    
    def _add_conclusions(self, page, sentiment_summary: Dict[str, Any], 
                        trend_summary: Dict[str, Any]):
        """添加结论与建议"""
        self.current_y = self.margin
        
        self._add_section_title(page, "5. 结论与建议")
        
        # 综合结论
        avg_sentiment = sentiment_summary.get('avg_sentiment', 0)
        total_news = sentiment_summary.get('total_news', 0)
        
        conclusion_text = f"""
基于对 {total_news} 条新闻的深度分析，当前市场情绪得分为 {avg_sentiment:.3f}。
        """
        
        self._add_text_block(page, conclusion_text.strip())
        
        # 投资建议
        if trend_summary.get('status') == 'success':
            trend_direction = trend_summary.get('trend_direction', 'neutral')
            
            if trend_direction == 'positive':
                advice = "建议关注市场机会，适当增加投资配置。"
            elif trend_direction == 'negative':
                advice = "建议谨慎投资，适当降低风险敞口。"
            else:
                advice = "建议保持观望，等待更明确的市场信号。"
            
            self._add_text_block(page, f"投资建议: {advice}")
        
        # 风险提示
        risk_warning = """
风险提示:
本报告基于历史数据和模型预测，仅供参考，不构成投资建议。
投资有风险，决策需谨慎。
        """
        
        self._add_text_block(page, risk_warning.strip())
    
    def _add_section_title(self, page, title: str):
        """添加章节标题"""
        page.insert_text((self.margin, self.current_y), title, fontsize=16, color=(0, 0, 0))
        self.current_y += self.line_height * 1.5
    
    def _add_text_block(self, page, text: str):
        """添加文本块"""
        lines = text.split('\n')
        for line in lines:
            if line.strip():
                page.insert_text((self.margin, self.current_y), line.strip(), fontsize=12)
                self.current_y += self.line_height
            else:
                self.current_y += self.line_height * 0.5


def generate_pdf_report(sentiment_summary: Dict[str, Any],
                      trend_summary: Dict[str, Any],
                      analyzed_news: List[Dict[str, Any]],
                      trend_data: Dict[str, Any],
                      output_path: str = "results/reports/market_analysis_report.pdf") -> str:
    """
    便捷函数：生成PDF报告
    
    Args:
        sentiment_summary: 情绪分析摘要
        trend_summary: 趋势分析摘要
        analyzed_news: 已分析的新闻数据
        trend_data: 趋势预测数据
        output_path: 输出路径
        
    Returns:
        生成的PDF文件路径
    """
    generator = PDFReportGenerator()
    return generator.create_report(sentiment_summary, trend_summary, 
                                 analyzed_news, trend_data, output_path)
