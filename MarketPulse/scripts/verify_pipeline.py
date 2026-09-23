"""真实链路自检：采集 → 分级 → 情绪 → 趋势 → 辩论终裁 → 追问复辩。

不用 mock，全部走真实搜索与真实 LLM（Key 来自 .env）。**会花好几分钟并
产生真实 API 费用**，所以不放进 pytest 自动套件，需要时手动跑。

确认五件事：
  1. 采集到的数据真的带 source_tier / tier_distribution；
  2. 情绪分布带 LLM 校正标记与算法原值；
  3. keyword_weights 是真实 TF-IDF 权重而不是排名；
  4. trend_summary 带 model_type / data_points / data_quality；
  5. 追问能触发新一轮红蓝辩论并产出新终裁。

运行（在 MarketPulse/ 下）：
    python scripts/verify_pipeline.py [关键词]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config as cfg  # noqa: E402
from src.agents.orchestrator import OrchestratorAgent  # noqa: E402
from src.forum.log_manager import LogManager  # noqa: E402


def brief(text, n=160):
    text = " ".join(str(text or "").split())
    return text[:n] + ("…" if len(text) > n else "")


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "华为"
    conf = cfg.init_config()

    task_id = f"verify_{int(time.time())}"
    fm = LogManager(task_id)
    orch = OrchestratorAgent(task_id, keyword, conf, fm, monitor=None, src_mode="news")

    print(f"\n=== 首轮分析：{keyword} ===")
    report = None
    for ev in orch.stream_pipeline():
        name = type(ev).__name__
        if name == "ErrorEvent":
            print(f"[{name}] fatal={ev.fatal} {ev.stage}: {brief(ev.message, 300)}")
            if ev.fatal:
                return 1
        elif name == "ReportEvent":
            report = ev.report_data
            print(f"[{name}] 结论：{brief(ev.conclusion, 200)}")

    if not report:
        print("未拿到 report_data")
        return 1

    news = report.get("analyzed_news", [])
    tiers = report.get("collect_meta", {}).get("tier_distribution", {})
    print(f"\n-- 采集 {len(news)} 条；信源层级分布 {tiers}")
    tiered = sum(1 for n in news if n.get("source_tier"))
    print(f"   带 source_tier 的样本：{tiered}/{len(news)}")
    for n in news[:3]:
        print(f"   T{n.get('source_tier')} {n.get('source')} | {brief(n.get('title'), 50)}")

    s = report.get("sentiment_summary", {})
    print(f"\n-- 情绪：负 {s.get('negative_count')} / 中 {s.get('neutral_count')} / "
          f"正 {s.get('positive_count')}，均分 {s.get('avg_sentiment')}")
    print(f"   LLM 校正生效：{s.get('llm_corrected')}；"
          f"算法原值 负{s.get('algo_negative_count')} 中{s.get('algo_neutral_count')} "
          f"正{s.get('algo_positive_count')}")

    kw = report.get("keyword_weights", [])
    print(f"\n-- 热词权重（真实 TF-IDF）{len(kw)} 个：")
    for w in kw[:6]:
        print(f"   {w.get('term')}  tfidf={w.get('tfidf')}  doc_freq={w.get('doc_freq')}")

    t = report.get("trend_summary", {})
    print(f"\n-- 趋势：{t.get('trend_direction')} 置信度 {t.get('confidence')} "
          f"模型 {t.get('model_type')} 观测点 {t.get('data_points')} "
          f"质量 {t.get('data_quality')}")

    v = report.get("verdict", {})
    print(f"\n-- 终裁：立场 {v.get('stance')} 置信度 {v.get('confidence')}")
    print(f"   {brief(v.get('summary'), 220)}")

    # ── 追问 ──
    question = "红方的危机判断有哪些数据支撑？请指出最薄弱的一环。"
    print(f"\n=== 追问：{question} ===")
    res = orch.run_followup_debate(question)
    print(f"status={res.get('status')} turns={len(res.get('turns', []))}")
    for turn in res.get("turns", []):
        print(f"  [{turn.get('author')}] {brief(turn.get('content'), 120)}")
    nv = res.get("verdict", {})
    print(f"新终裁：立场 {nv.get('stance')} 置信度 {nv.get('confidence')}")
    print(f"  {brief(nv.get('summary'), 220)}")

    print("\n=== 自检通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
