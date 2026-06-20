import datetime
import io
from typing import Dict, Any
from .base_agent import BaseAgent
from ..collect.custom_search import CustomSearchCollector
from ..preprocess.cleaner import DataCleaner
from ..data.local_loader import load_local_table


class CollectAgent(BaseAgent):
    # 按模式动态设采集量上限
    MODE_MAX_RESULTS = {
        "social": 500,
        "news": 300,
    }
    MODE_MIN_RESULTS = {
        "social": 300,
        "news": 200,
    }

    def _get_system_prompt(self) -> str:
        return (
            "你是一名专业的舆情数据采集专员(CollectAgent)。"
            "你的任务是从多个数据源并行采集与关键词相关的公开信息，"
            "统一去重清洗后，识别出可能影响市场的核心突发事件或异常线索，"
            "并用简明扼要的一句话向论坛报告你的发现。不要长篇大论。"
        )

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        keyword = input_data.get("keyword", "")
        src_mode = input_data.get("src_mode", "news")
        max_results = input_data.get(
            "max_results",
            self.MODE_MAX_RESULTS.get(src_mode, 300)
        )
        min_results = self.MODE_MIN_RESULTS.get(src_mode, 200)
        local_data_path = input_data.get("local_data_path", "")

        # ── 线上多源并行采集 ──
        collector = CustomSearchCollector()
        raw_news = collector.run_custom_search(keyword, max_results=max_results)
        seen_urls = {n.get("link", "") for n in raw_news}
        seen_titles = {n.get("title", "")[:30] for n in raw_news}

        # 不足时补充采集：使用差异化查询避免重复
        if len(raw_news) < min_results:
            import datetime as _dt
            self.write_to_forum_log(
                f"首轮采集仅获 {len(raw_news)} 条（目标 ≥{min_results}），"
                f"用差异化关键词启动补充采集..."
            )
            now = _dt.datetime.now()
            # 差异化搜索词：换表述 + 换时间窗口，不走同一批数据
            supplement_terms = [
                f"{keyword} 报道",
                f"{keyword} 分析",
            ]
            for m in [1, 2]:
                supplement_terms.append(
                    f"{keyword} {now.year}年{(now.month - m - 1) % 12 + 1}月"
                )
            net_added = 0
            for term in supplement_terms:
                if len(raw_news) >= min_results:
                    break
                batch = collector.run_custom_search(term, max_results=40)
                new_in_batch = 0
                for n in batch:
                    url = n.get("link", "")
                    title_prefix = n.get("title", "")[:30]
                    if url and url not in seen_urls and title_prefix not in seen_titles:
                        raw_news.append(n)
                        seen_urls.add(url)
                        seen_titles.add(title_prefix)
                        new_in_batch += 1
                net_added += new_in_batch
                if new_in_batch > 0:
                    self.write_to_forum_log(
                        f"  补充词 '{term}' → +{new_in_batch} 条新数据"
                    )
            self.write_to_forum_log(
                f"补充采集完成，净增 {net_added} 条，合并去重后共 {len(raw_news)} 条"
            )

        cleaner = DataCleaner()
        cleaned_news = cleaner.clean_news_batch(raw_news) if raw_news else []

        # ── 本地数据加载 ──
        local_records = []
        if local_data_path:
            try:
                from pathlib import Path
                local_path = Path(local_data_path)
                if local_path.exists():
                    raw_bytes = local_path.read_bytes()
                    wrapper = io.BytesIO(raw_bytes)
                    wrapper.name = local_path.name  # type: ignore
                    local_records, _ = load_local_table(wrapper)
                    self.write_to_forum_log(
                        f"已加载本地数据 {len(local_records)} 条，将与线上 {len(cleaned_news)} 条数据融合分析。"
                    )
            except Exception as e:
                self.write_to_forum_log(f"本地数据加载失败: {e}")

        # ── 融合线上与本地数据 ──
        all_data = cleaned_news + [
            {
                "title": r.get("title", ""),
                "summary": r.get("summary", r.get("content", "")),
                "url": "",
                "publish_time": r.get("publish_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "source": r.get("source", "本地数据"),
                "category": r.get("category", "本地"),
            }
            for r in local_records
        ]

        # ── 数据为空时直接失败（无模拟数据注入） ──
        if not all_data:
            msg = f"所有搜索源均未返回关于 '{keyword}' 的真实数据，采集失败。"
            self.write_to_forum_log(msg)
            return {"status": "error", "summary": msg}

        total_count = len(all_data)
        source_count = len(set(n.get("source", "") for n in all_data))
        date_range = self._compute_date_range(all_data)
        sample_texts = [f"标题:{n.get('title')} 摘要:{n.get('summary')}" for n in all_data[:15]]

        llm_prompt = (
            f"采集任务：关键词='{keyword}'，模式={src_mode}，共采集 {total_count} 条数据，"
            f"时间跨度 {date_range}，来自 {source_count} 个数据源。\n"
            f"样本:\n" + "\n".join(sample_texts) +
            "\n请提炼一个值得警惕或关注的线索，一句话概括。"
        )

        insight = self.call_llm(llm_prompt)

        if insight and "Error" not in insight:
            self.write_to_forum_log(
                f"我已完成数据采集（共 {total_count} 条，{source_count} 源，"
                f"时间跨度 {date_range}）。我发现: {insight}"
            )
        else:
            self.write_to_forum_log(
                f"我已完成数据采集（共 {total_count} 条，{source_count} 源，"
                f"时间跨度 {date_range}）。暂未发现明显异常。"
            )

        return {
            "status": "success",
            "agent": self.name,
            "data": {
                "news": all_data,
                "local_records": local_records,
                "collect_meta": {
                    "total_count": total_count,
                    "source_count": source_count,
                    "date_range": date_range,
                    "src_mode": src_mode,
                }
            },
            "summary": (
                f"成功采集并清洗了 {total_count} 条关于 {keyword} 的数据"
                f"（线上 {len(cleaned_news)} + 本地 {len(local_records)}），"
                f"来自 {source_count} 个数据源，时间跨度 {date_range}。"
            )
        }

    @staticmethod
    def _compute_date_range(all_data: list) -> str:
        dates = []
        for n in all_data:
            pub = n.get("publish_time", "")
            if pub:
                try:
                    if isinstance(pub, str) and len(pub) >= 10:
                        dates.append(pub[:10])
                except Exception:
                    pass
        if not dates:
            return "未知"
        dates.sort()
        return f"{dates[0]} ~ {dates[-1]}" if len(dates) > 1 else dates[0]
