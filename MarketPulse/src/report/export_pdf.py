from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ChartPaths = Dict[str, Path]


class PDFReportGenerator:
    """基于 ReportLab 的 PDF 报告生成器，原生支持中文字体。"""

    def __init__(self) -> None:
        self._register_fonts()
        self.styles = self._build_styles()
        self.doc: Optional[SimpleDocTemplate] = None

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
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        self.doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        story: List[Any] = []
        story.extend(self._build_title_page(sentiment_summary))
        story.append(PageBreak())
        story.extend(self._build_table_of_contents())
        story.append(PageBreak())
        story.extend(self._build_executive_summary(sentiment_summary, trend_summary))
        story.append(PageBreak())
        story.extend(self._build_sentiment_details(sentiment_summary, analyzed_news))
        story.append(PageBreak())
        story.extend(self._build_trend_analysis(trend_summary, trend_data))
        story.append(PageBreak())
        story.extend(self._build_news_details(analyzed_news))
        story.append(PageBreak())
        story.extend(self._build_conclusions(sentiment_summary, trend_summary))

        if chart_paths:
            story.append(PageBreak())
            story.extend(self._build_chart_gallery(chart_paths))

        assert self.doc is not None
        self.doc.build(story, onFirstPage=self._add_page_number, onLaterPages=self._add_page_number)
        return str(output)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _register_fonts(self) -> None:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        except Exception:  # noqa: BLE001
            pass

    def _build_styles(self):
        styles = getSampleStyleSheet()
        target_styles = ["Normal", "BodyText", "Heading1", "Heading2", "Heading3", "Title", "Bullet"]
        for name in target_styles:
            if name in styles:
                styles[name].fontName = "STSong-Light"
                styles[name].leading = styles[name].fontSize * 1.35

        styles.add(
            ParagraphStyle(
                name="Small", parent=styles["Normal"], fontSize=9, leading=11, textColor=colors.grey
            )
        )
        styles.add(
            ParagraphStyle(
                name="Metric",
                parent=styles["Heading3"],
                fontSize=12,
                leading=15,
                textColor=colors.HexColor("#0D47A1"),
            )
        )
        styles.add(
            ParagraphStyle(
                name="BulletItem",
                parent=styles["Normal"],
                leftIndent=10,
                bulletIndent=0,
                bulletFontName="STSong-Light",
            )
        )
        return styles

    def _doc_width(self) -> float:
        assert self.doc is not None
        return self.doc.width

    def _add_page_number(self, canvas, doc) -> None:  # type: ignore[override]
        canvas.saveState()
        canvas.setFont("STSong-Light", 9)
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.bottomMargin / 2, f"第 {doc.page} 页")
        canvas.restoreState()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_title_page(self, sentiment_summary: Dict[str, Any]) -> List[Any]:
        story: List[Any] = []
        story.append(Spacer(1, 45 * mm))
        story.append(Paragraph("MarketPulse 智能市场分析报告", self.styles["Title"]))
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("基于AI的情绪洞察与趋势预测", self.styles["Heading2"]))
        story.append(Spacer(1, 25 * mm))
        story.append(
            Paragraph(
                f"报告生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}",
                self.styles["Normal"],
            )
        )
        story.append(Spacer(1, 20 * mm))

        data = [
            ["总新闻数", str(sentiment_summary.get("total_news", 0))],
            ["积极新闻", str(sentiment_summary.get("positive_count", 0))],
            ["消极新闻", str(sentiment_summary.get("negative_count", 0))],
            ["平均情绪得分", f"{sentiment_summary.get('avg_sentiment', 0):.3f}"],
        ]
        table = Table(data, colWidths=[50 * mm, 40 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F2FD")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0D47A1")),
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FBFF")]),
                ]
            )
        )
        story.append(table)
        return story

    def _build_table_of_contents(self) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("目录", self.styles["Heading1"]))
        story.append(Spacer(1, 6 * mm))
        items = [
            Paragraph("1. 执行摘要", self.styles["Normal"]),
            Paragraph("2. 情绪分析详情", self.styles["Normal"]),
            Paragraph("3. 趋势预测分析", self.styles["Normal"]),
            Paragraph("4. 新闻详情分析", self.styles["Normal"]),
            Paragraph("5. 结论与建议", self.styles["Normal"]),
            Paragraph("6. 图表合集", self.styles["Normal"]),
        ]
        story.append(ListFlowable(items, bulletType="1", start="1"))
        return story

    def _build_executive_summary(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
    ) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("1. 执行摘要", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        total_news = sentiment_summary.get("total_news", 0)
        positive = sentiment_summary.get("positive_count", 0)
        negative = sentiment_summary.get("negative_count", 0)
        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)

        overview = (
            f"本次分析共处理 {total_news} 条新闻，识别出积极新闻 {positive} 条、"
            f"消极新闻 {negative} 条，整体情绪得分为 {avg_sentiment:.3f}。"
        )
        story.append(Paragraph(overview, self.styles["BodyText"]))
        story.append(Spacer(1, 2 * mm))

        if trend_summary.get("status") == "success":
            trend_direction = trend_summary.get("trend_direction", "neutral")
            confidence = trend_summary.get("confidence", 0.0)
            summary = (
                f"基于时间序列模型的预测结果显示，市场情绪呈 {trend_direction} 走势，"
                f"预测置信度约为 {confidence:.1%}。"
            )
            story.append(Paragraph(summary, self.styles["BodyText"]))
        elif trend_summary.get("message"):
            story.append(Paragraph(f"趋势预测未能完成：{trend_summary['message']}", self.styles["BodyText"]))

        return story

    def _build_sentiment_details(
        self,
        sentiment_summary: Dict[str, Any],
        analyzed_news: List[Dict[str, Any]],
    ) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("2. 情绪分析详情", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        distribution = sentiment_summary.get("sentiment_distribution", {})
        total = max(sentiment_summary.get("total_news", 1), 1)
        lines = [
            Paragraph(
                f"积极新闻：{distribution.get('positive', 0)} 条，占比 {distribution.get('positive', 0) / total * 100:.1f}%",
                self.styles["Normal"],
            ),
            Paragraph(
                f"消极新闻：{distribution.get('negative', 0)} 条，占比 {distribution.get('negative', 0) / total * 100:.1f}%",
                self.styles["Normal"],
            ),
            Paragraph(
                f"中性新闻：{distribution.get('neutral', 0)} 条，占比 {distribution.get('neutral', 0) / total * 100:.1f}%",
                self.styles["Normal"],
            ),
        ]
        story.append(ListFlowable(lines, bulletType="bullet"))
        story.append(Spacer(1, 3 * mm))

        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)
        if avg_sentiment > 0.1:
            insight = "市场情绪整体偏积极，投资者信心较强。"
        elif avg_sentiment < -0.1:
            insight = "市场情绪整体偏消极，投资者风险偏好下降。"
        else:
            insight = "市场情绪相对中性，投资者以观望为主。"
        story.append(Paragraph(insight, self.styles["BodyText"]))

        ai_scores = [item.get("ai_sentiment_score") for item in analyzed_news if item.get("ai_sentiment_score") is not None]
        if ai_scores:
            ai_avg = sum(ai_scores) / len(ai_scores)
            story.append(
                Paragraph(
                    f"AI 模型辅助评分覆盖 {len(ai_scores)} 条文本，平均情绪得分 {ai_avg:.3f}。",
                    self.styles["BodyText"],
                )
            )
        return story

    def _build_trend_analysis(
        self,
        trend_summary: Dict[str, Any],
        trend_data: Dict[str, Any],
    ) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("3. 趋势预测分析", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        if trend_summary.get("status") != "success":
            message = trend_summary.get("message", "数据量不足，无法完成趋势预测。")
            story.append(Paragraph(message, self.styles["BodyText"]))
            return story

        direction = trend_summary.get("trend_direction", "neutral")
        confidence = trend_summary.get("confidence", 0.0)
        data_points = trend_summary.get("data_points", 0)
        forecast_periods = trend_summary.get("forecast_periods", 0)

        items = [
            Paragraph(f"趋势方向：{direction}", self.styles["Normal"]),
            Paragraph(f"预测置信度：{confidence:.1%}", self.styles["Normal"]),
            Paragraph(f"训练数据点：{data_points}", self.styles["Normal"]),
            Paragraph(f"预测天数：{forecast_periods}", self.styles["Normal"]),
        ]
        story.append(ListFlowable(items, bulletType="bullet"))
        story.append(Spacer(1, 3 * mm))

        recommendation = trend_summary.get("recommendation")
        if recommendation:
            story.append(Paragraph(f"投资建议：{recommendation}", self.styles["BodyText"]))

        predictions = []
        if isinstance(trend_data, dict):
            predictions = trend_data.get("predictions", []) or trend_data.get("forecast", [])
        if predictions:
            latest = predictions[-1]
            value = latest.get("yhat") or latest.get("value")
            if value is not None:
                story.append(Paragraph(f"最新预测情绪得分：{float(value):.3f}", self.styles["BodyText"]))

        return story

    def _build_news_details(self, analyzed_news: List[Dict[str, Any]]) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("4. 新闻详情分析", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        if not analyzed_news:
            story.append(Paragraph("暂无新闻数据。", self.styles["BodyText"]))
            return story

        top_news = sorted(
            analyzed_news,
            key=lambda item: abs(item.get("sentiment_score", 0.0)),
            reverse=True,
        )[:10]

        for idx, news in enumerate(top_news, start=1):
            title = news.get("original_title") or news.get("title") or "无标题"
            story.append(Paragraph(f"4.{idx} {title}", self.styles["Heading3"]))

            score = news.get("sentiment_score", 0.0)
            label = news.get("sentiment_label", "neutral")
            confidence = news.get("sentiment_confidence", 0.0)
            publish_time = news.get("publish_time", "未知")
            category = news.get("category", "未分类") or "未分类"

            bullet_items = [
                Paragraph(f"情绪得分：{score:.3f}（{label}）", self.styles["BulletItem"]),
                Paragraph(f"情绪置信度：{confidence:.3f}", self.styles["BulletItem"]),
                Paragraph(f"发布时间：{publish_time}", self.styles["BulletItem"]),
                Paragraph(f"所属类别：{category}", self.styles["BulletItem"]),
                Paragraph(f"来源：{news.get('source', '未知')}", self.styles["BulletItem"]),
            ]
            story.append(ListFlowable(bullet_items, bulletType="bullet"))

            summary = news.get("original_summary") or news.get("summary") or news.get("content", "")
            if summary:
                trimmed = summary[:400] + ("..." if len(summary) > 400 else "")
                story.append(Paragraph(trimmed, self.styles["BodyText"]))
            story.append(Spacer(1, 2 * mm))

        return story

    def _build_conclusions(
        self,
        sentiment_summary: Dict[str, Any],
        trend_summary: Dict[str, Any],
    ) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("5. 结论与建议", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        avg_sentiment = sentiment_summary.get("avg_sentiment", 0.0)
        total_news = sentiment_summary.get("total_news", 0)
        story.append(
            Paragraph(
                f"综合 {total_news} 条新闻的情绪分析，当前市场情绪得分为 {avg_sentiment:.3f}。",
                self.styles["BodyText"],
            )
        )

        if trend_summary.get("status") == "success":
            direction = trend_summary.get("trend_direction", "neutral")
            if direction == "positive":
                advice = "情绪趋势向上，可关注优质资产的增持机会。"
            elif direction == "negative":
                advice = "情绪趋于下行，建议保持谨慎并控制仓位。"
            else:
                advice = "情绪稳定，建议耐心等待新的市场信号。"
            story.append(Paragraph(f"投资建议：{advice}", self.styles["BodyText"]))

        story.append(
            Paragraph(
                "风险提示：本报告基于历史数据和模型预测，仅供参考，不构成投资建议。",
                self.styles["BodyText"],
            )
        )
        return story

    def _build_chart_gallery(self, chart_paths: ChartPaths) -> List[Any]:
        story: List[Any] = []
        story.append(Paragraph("6. 图表合集", self.styles["Heading1"]))
        story.append(Spacer(1, 4 * mm))

        chart_titles = {
            "sentiment_distribution": "情绪分布图",
            "sentiment_timeline": "情绪时间线",
            "trend_prediction": "趋势预测曲线",
            "sentiment_heatmap": "情绪热力图",
        }

        for key, chart_path in chart_paths.items():
            path = Path(chart_path)
            if not path.exists():
                continue

            story.append(Paragraph(chart_titles.get(key, path.stem), self.styles["Heading3"]))
            story.append(Spacer(1, 2 * mm))

            img = Image(str(path))
            img._restrictSize(self._doc_width(), A4[1] - 60 * mm)
            story.append(img)
            story.append(Spacer(1, 6 * mm))

        return story


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
