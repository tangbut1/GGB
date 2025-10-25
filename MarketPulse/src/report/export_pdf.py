from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF


ChartPaths = Dict[str, Path]


class PDFReportGenerator:
    """PDF报告生成器，提供多页中文友好的市场分析报告。"""

    def __init__(self) -> None:
        self.page_width = 595  # A4 portrait width in points
        self.page_height = 842
        self.margin = 50
        self.doc: Optional[fitz.Document] = None
        self.page: Optional[fitz.Page] = None
        self.current_y: float = self.margin
        self.font_name: str = "helv"
        self.heading_sizes = {1: 22, 2: 18, 3: 14}
        self.body_size = 12
        self.line_spacing_factor = 1.4

    def create_report(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
        analyzed_news: List[Dict[str, Any]],
        trend_data: Dict[str, Any],
        output_path: str = "results/reports/market_analysis_report.pdf",
        chart_paths: Optional[ChartPaths] = None,
    ) -> str:
        chart_paths = chart_paths or {}

        self.doc = fitz.open()
        self.font_name = self._load_font(self.doc)

        self._start_new_page()
        self._render_title_page(sentiment_summary)

        self._start_new_page()
        self._render_table_of_contents()

        self._start_new_page()
        self._render_executive_summary(sentiment_summary, trend_summary)

        self._start_new_page()
        self._render_sentiment_details(sentiment_summary, analyzed_news)

        self._start_new_page()
        self._render_trend_analysis(trend_summary, trend_data)

        self._start_new_page()
        self._render_news_details(analyzed_news)

        self._start_new_page()
        self._render_conclusions(sentiment_summary, trend_summary)

        if chart_paths:
            self._render_chart_gallery(chart_paths)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        assert self.doc is not None
        self.doc.save(str(output))
        self.doc.close()
        return str(output)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _load_font(self, doc: fitz.Document) -> str:
        """加载支持中文的字体，找不到则回退到默认字体。"""
        # Windows系统常见中文字体路径
        candidate_paths = [
            Path("C:/Windows/Fonts/simsun.ttc"),  # 宋体
            Path("C:/Windows/Fonts/simhei.ttf"),  # 黑体
            Path("C:/Windows/Fonts/msyh.ttc"),    # 微软雅黑
            Path("C:/Windows/Fonts/simkai.ttf"), # 楷体
            Path("C:/Windows/Fonts/simfang.ttf"), # 仿宋
            Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSansSC-Regular.otf",
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ]

        for font_path in candidate_paths:
            if font_path.exists():
                try:
                    # 使用正确的方法加载字体
                    font_name = doc._insert_font(str(font_path))
                    print(f"✅ 成功加载字体: {font_path} -> {font_name}")
                    return font_name
                except (RuntimeError, AttributeError, TypeError) as e:
                    print(f"⚠️ 字体加载失败: {font_path} - {e}")
                    continue
        
        print("⚠️ 未找到中文字体，使用默认字体（可能显示乱码）")
        return "helv"

    def _start_new_page(self) -> None:
        if self.doc is None:
            raise ValueError("Document not initialised")
        self.page = self.doc.new_page(width=self.page_width, height=self.page_height)
        self.current_y = self.margin

    def _ensure_space(self, line_height: float) -> None:
        if self.current_y + line_height > self.page_height - self.margin:
            self._start_new_page()

    def _write_text(self, text: str, fontsize: float) -> None:
        if not text:
            self.current_y += fontsize * (self.line_spacing_factor / 2)
            return
        line_height = fontsize * self.line_spacing_factor
        self._ensure_space(line_height)
        assert self.page is not None
        self.page.insert_text(
            fitz.Point(self.margin, self.current_y),
            text,
            fontsize=fontsize,
            fontname=self.font_name,
            color=(0, 0, 0),
            encoding=0,
        )
        self.current_y += line_height

    def _write_paragraph(self, text: str, fontsize: Optional[float] = None) -> None:
        fontsize = fontsize or self.body_size
        for line in text.splitlines():
            self._write_text(line.strip(), fontsize)
        self.current_y += fontsize * 0.2

    def _write_heading(self, text: str, level: int = 1) -> None:
        fontsize = self.heading_sizes.get(level, self.body_size)
        self._write_text(text, fontsize)
        self.current_y += fontsize * 0.2

    def _write_bullet_list(self, items: List[str]) -> None:
        for item in items:
            self._write_text(f"• {item}", self.body_size)
        self.current_y += self.body_size * 0.3

    def _write_key_value(self, pairs: List[tuple[str, str]]) -> None:
        for key, value in pairs:
            self._write_text(f"{key}: {value}", self.body_size)
        self.current_y += self.body_size * 0.3

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------
    def _render_title_page(self, sentiment_summary: Dict[str, Any]) -> None:
        assert self.page is not None
        title_rect = fitz.Rect(self.margin, 200, self.page_width - self.margin, 250)
        self.page.insert_textbox(
            title_rect,
            "MarketPulse 智能市场分析报告",
            fontsize=28,
            fontname=self.font_name,
            align=fitz.TEXT_ALIGN_CENTER,
            encoding=0,
        )

        subtitle_rect = fitz.Rect(self.margin, 270, self.page_width - self.margin, 310)
        self.page.insert_textbox(
            subtitle_rect,
            "基于AI的情绪洞察与趋势预测",
            fontsize=18,
            fontname=self.font_name,
            align=fitz.TEXT_ALIGN_CENTER,
            encoding=0,
        )

        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        time_rect = fitz.Rect(self.margin, 330, self.page_width - self.margin, 360)
        self.page.insert_textbox(
            time_rect,
            f"报告生成时间：{current_time}",
            fontsize=12,
            fontname=self.font_name,
            align=fitz.TEXT_ALIGN_CENTER,
            encoding=0,
        )

        self.current_y = 420
        self._write_heading("关键指标概览", level=2)
        pairs = [
            ("总新闻数", str(sentiment_summary.get("total_news", 0))),
            ("积极新闻", str(sentiment_summary.get("positive_count", 0))),
            ("消极新闻", str(sentiment_summary.get("negative_count", 0))),
            ("平均情绪得分", f"{sentiment_summary.get('avg_sentiment', 0):.3f}"),
        ]
        self._write_key_value(pairs)

    def _render_table_of_contents(self) -> None:
        self._write_heading("目录", level=1)
        entries = [
            "1. 执行摘要",
            "2. 情绪分析详情",
            "3. 趋势预测分析",
            "4. 新闻详情分析",
            "5. 结论与建议",
            "6. 图表合集",
        ]
        self._write_bullet_list(entries)

    def _render_executive_summary(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
    ) -> None:
        self._write_heading("1. 执行摘要", level=1)
        total_news = sentiment_summary.get("total_news", 0)
        positive = sentiment_summary.get("positive_count", 0)
        negative = sentiment_summary.get("negative_count", 0)
        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)

        summary_text = (
            f"本次报告对 {total_news} 条新闻信息进行了清洗与多模型情绪分析，"
            f"识别出积极新闻 {positive} 条、消极新闻 {negative} 条，"
            f"整体市场情绪得分为 {avg_sentiment:.3f}。"
        )
        self._write_paragraph(summary_text)

        if trend_summary.get("status") == "success":
            trend_direction = trend_summary.get("trend_direction", "neutral")
            confidence = trend_summary.get("confidence", 0)
            trend_text = (
                f"基于Prophet模型的趋势预测显示，未来市场情绪呈现 {trend_direction} 趋势，"
                f"预测置信度为 {confidence:.1%}。"
            )
            self._write_paragraph(trend_text)
        elif trend_summary.get("message"):
            self._write_paragraph(f"趋势预测未成功：{trend_summary['message']}")

    def _render_sentiment_details(
        self,
        sentiment_summary: Dict[str, Any],
        analyzed_news: List[Dict[str, Any]],
    ) -> None:
        self._write_heading("2. 情绪分析详情", level=1)
        dist = sentiment_summary.get("sentiment_distribution", {})
        total = sentiment_summary.get("total_news", 1) or 1

        distribution_lines = [
            f"积极新闻：{dist.get('positive', 0)} 条，占比 {dist.get('positive', 0) / total * 100:.1f}%",
            f"消极新闻：{dist.get('negative', 0)} 条，占比 {dist.get('negative', 0) / total * 100:.1f}%",
            f"中性新闻：{dist.get('neutral', 0)} 条，占比 {dist.get('neutral', 0) / total * 100:.1f}%",
        ]
        self._write_bullet_list(distribution_lines)

        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)
        if avg_sentiment > 0.1:
            insight = "市场情绪整体偏积极，投资者信心较强。"
        elif avg_sentiment < -0.1:
            insight = "市场情绪整体偏消极，投资者风险偏好下降。"
        else:
            insight = "市场情绪相对中性，投资者以观望为主。"
        self._write_paragraph(f"情绪解读：{insight}")

        ai_scores = [n.get("ai_sentiment_score") for n in analyzed_news if n.get("ai_sentiment_score") is not None]
        if ai_scores:
            avg_ai = sum(ai_scores) / len(ai_scores)
            self._write_paragraph(f"AI增强分析平均情绪得分：{avg_ai:.3f}（覆盖 {len(ai_scores)} 条文本）")

    def _render_trend_analysis(
        self,
        trend_summary: Dict[str, Any],
        trend_data: Dict[str, Any],
    ) -> None:
        self._write_heading("3. 趋势预测分析", level=1)
        if trend_summary.get("status") != "success":
            message = trend_summary.get("message", "数据量不足，无法完成趋势预测。")
            self._write_paragraph(message)
            return

        direction = trend_summary.get("trend_direction", "neutral")
        confidence = trend_summary.get("confidence", 0.0)
        data_points = trend_summary.get("data_points", 0)
        forecast_periods = trend_summary.get("forecast_periods", 0)

        items = [
            f"趋势方向：{direction}",
            f"预测置信度：{confidence:.1%}",
            f"训练数据点：{data_points}",
            f"预测天数：{forecast_periods}",
        ]
        self._write_bullet_list(items)

        recommendation = trend_summary.get("recommendation")
        if recommendation:
            self._write_paragraph(f"投资建议：{recommendation}")

        predictions = trend_data.get("predictions", []) if isinstance(trend_data, dict) else []
        if predictions:
            last_prediction = predictions[-1]
            value = last_prediction.get("yhat", 0)
            self._write_paragraph(f"最新预测情绪得分：{value:.3f}")

    def _render_news_details(self, analyzed_news: List[Dict[str, Any]]) -> None:
        self._write_heading("4. 新闻详情分析", level=1)
        if not analyzed_news:
            self._write_paragraph("暂无新闻详情数据。")
            return

        important_news = sorted(
            analyzed_news,
            key=lambda item: abs(item.get("sentiment_score", 0)),
            reverse=True,
        )[:10]

        for idx, news in enumerate(important_news, start=1):
            title = news.get("original_title") or news.get("title", "无标题")
            score = news.get("sentiment_score", 0.0)
            label = news.get("sentiment_label", "neutral")
            confidence = news.get("sentiment_confidence", 0.0)
            publish_time = news.get("publish_time", "未知")
            category = news.get("category", "未分类") or "未分类"

            self._write_heading(f"4.{idx} {title}", level=3)
            details = [
                f"情绪得分：{score:.3f}（{label}）",
                f"情绪置信度：{confidence:.3f}",
                f"发布时间：{publish_time}",
                f"所属类别：{category}",
                f"来源：{news.get('source', '未知')}",
            ]
            self._write_bullet_list(details)

            summary = news.get("original_summary") or news.get("summary", "")
            if summary:
                self._write_paragraph(f"摘要：{summary[:200]}{'...' if len(summary) > 200 else ''}")

    def _render_conclusions(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
    ) -> None:
        self._write_heading("5. 结论与建议", level=1)
        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)
        total_news = sentiment_summary.get("total_news", 0)

        self._write_paragraph(
            f"综合 {total_news} 条新闻的情绪分析，当前市场情绪得分为 {avg_sentiment:.3f}。"
        )

        if trend_summary.get("status") == "success":
            direction = trend_summary.get("trend_direction", "neutral")
            if direction == "positive":
                advice = "情绪趋势向上，可关注优质资产的增持机会。"
            elif direction == "negative":
                advice = "情绪趋于下行，建议保持谨慎并控制仓位。"
            else:
                advice = "情绪稳定，建议耐心等待新的市场信号。"
            self._write_paragraph(f"投资建议：{advice}")

        self._write_paragraph(
            "风险提示：本报告基于历史数据和模型预测，仅供参考，不构成投资建议。投资有风险，决策需谨慎。"
        )

    def _render_chart_gallery(self, chart_paths: ChartPaths) -> None:
        chart_titles = {
            "sentiment_distribution": "情绪分布图",
            "sentiment_timeline": "情绪时间线",
            "trend_prediction": "趋势预测曲线",
            "sentiment_heatmap": "情绪热力图",
        }

        for key, path in chart_paths.items():
            chart_file = Path(path)
            if not chart_file.exists():
                continue

            self._start_new_page()
            title = chart_titles.get(key, chart_file.stem)
            self._write_heading(f"6. {title}", level=1)

            available_height = self.page_height - self.margin - self.current_y
            image_height = available_height
            image_width = self.page_width - 2 * self.margin
            if available_height <= 0:
                self._start_new_page()
                image_height = self.page_height - 2 * self.margin
                image_width = self.page_width - 2 * self.margin

            rect = fitz.Rect(
                self.margin,
                self.current_y,
                self.margin + image_width,
                self.current_y + image_height,
            )
            assert self.page is not None
            self.page.insert_image(rect, filename=str(chart_file), keep_proportion=True)
            self.current_y = rect.br.y + self.body_size


def generate_pdf_report(
    sentiment_summary: Dict[str, Any],
    trend_summary: Dict[str, Any],
    analyzed_news: List[Dict[str, Any]],
    trend_data: Dict[str, Any],
    output_path: str = "results/reports/market_analysis_report.pdf",
    chart_paths: Optional[ChartPaths] = None,
) -> str:
    generator = PDFReportGenerator()
    return generator.create_report(
        sentiment_summary,
        trend_summary,
        analyzed_news,
        trend_data,
        output_path,
        chart_paths,
    )
