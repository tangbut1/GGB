"""追问的中断与续跑。

追问是红→蓝→裁判三次串行 LLM 往返，一次几十秒。用户点了"停止"之后要能
真的停下来，而且已经跑出来的发言不能丢——"继续"要接着那里往下跑，而不是
把整轮重问一遍（重问会多花一次 LLM 费用，且论坛日志里出现重复发言）。

这里全部用桩替换 Agent.run，不发任何网络请求。
"""

import shutil
import tempfile
from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.forum.log_manager import LogManager


class _StubMonitor:
    def start(self):
        pass

    def stop(self):
        pass

    def wait_for_host_guidance(self, timeout=10):
        return ""


@pytest.fixture
def logdir():
    """论坛日志目录。必须活到测试结束——orchestrator 在整个测试过程里
    都在往这个目录里的文件追加发言，提前删掉会让 write 抛 FileNotFoundError。"""
    path = tempfile.mkdtemp(prefix="mp_fu_test_")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_orchestrator(logdir, task_id="task_fu", keyword="测试事件"):
    config = {
        "agent_llm": {
            "collect_agent": {},
            "sentiment_agent": {},
            "trend_agent": {},
            "report_agent": {},
            "forum_host": {},
        }
    }
    forum = LogManager(task_id, log_dir=logdir)
    return OrchestratorAgent(
        task_id=task_id, keyword=keyword, config=config,
        forum_manager=forum, monitor=_StubMonitor(),
    )


def _patch_agents(orch, red_text="红方复辩：制度性风险正在累积",
                  blue_text="蓝方复辩：市占率数据不支持这个判断"):
    """红蓝双方各发言一次，裁判给一份降级终裁（无网络）。"""

    def fake_red(payload):
        rnd = getattr(orch.sentiment_agent, "iteration_count", 1)
        orch.forum_manager.write("SentimentAgent", rnd, red_text)
        return {"status": "success"}

    def fake_blue(payload):
        rnd = getattr(orch.trend_agent, "iteration_count", 1)
        orch.forum_manager.write("TrendAgent", rnd, blue_text)
        return {"status": "success"}

    orch.sentiment_agent.run = MagicMock(side_effect=fake_red)
    orch.trend_agent.run = MagicMock(side_effect=fake_blue)
    orch.host.render_verdict = MagicMock(return_value={
        "stance": "neutral", "confidence": 0.5, "summary": "补充裁定",
        "key_disagreements": ["分歧"], "recommendation": "继续观察",
        "red_strongest": red_text, "blue_strongest": blue_text,
    })


def test_followup_runs_all_three_steps(logdir):
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]

    result = orch.run_followup_debate("红方观点是否成立？")

    assert result["status"] == "success"
    assert [t["role"] for t in result["turns"]] == ["red", "blue", "judge"]
    assert result["turns"][0]["round"] == 3
    assert result["verdict"]["stance"] == "neutral"
    # 完整跑完要清掉续跑现场，否则下一个追问会带着 resume 语义回来
    assert orch._followup_state is None


def test_cancel_before_red_stops_immediately(logdir):
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]
    orch.request_cancel()

    result = orch.run_followup_debate("这个问题不想问了")

    assert result["status"] == "cancelled"
    assert result["turns"] == []
    # 一次 LLM 都不该发
    assert orch.sentiment_agent.run.call_count == 0
    assert orch.trend_agent.run.call_count == 0
    assert orch.host.render_verdict.call_count == 0


def test_cancel_after_red_keeps_red_speech(logdir):
    """红方已经说完才停：那段话是真跑出来的，必须交出去。"""
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]

    original = orch.sentiment_agent.run

    def red_then_cancel(payload):
        out = original(payload)
        orch.request_cancel()  # 红方发言返回的瞬间用户点了停止
        return out

    orch.sentiment_agent.run = MagicMock(side_effect=red_then_cancel)
    result = orch.run_followup_debate("这个问题不想问了")

    assert result["status"] == "cancelled"
    assert [t["role"] for t in result["turns"]] == ["red"]
    assert result["turns"][0]["content"].startswith("红方复辩")
    # 蓝方和裁判都不该跑
    assert orch.trend_agent.run.call_count == 0
    assert orch.host.render_verdict.call_count == 0


def test_resume_skips_finished_steps(logdir):
    """"继续"不能把已经说完的一方再问一遍。"""
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]

    # 第一轮：红方说完就停
    original_red = orch.sentiment_agent.run

    def red_then_cancel(payload):
        out = original_red(payload)
        orch.request_cancel()
        return out

    orch.sentiment_agent.run = MagicMock(side_effect=red_then_cancel)
    first = orch.run_followup_debate("红方观点是否成立？")
    assert first["status"] == "cancelled"
    red_calls_after_first = orch.sentiment_agent.run.call_count

    # 第二段：续跑。红方不该再被问一次，蓝方和裁判接着跑。
    second = orch.run_followup_debate("", resume=True)

    assert second["status"] == "success"
    assert orch.sentiment_agent.run.call_count == red_calls_after_first
    assert [t["role"] for t in second["turns"]] == ["red", "blue", "judge"]
    # 轮次沿用中断那一次，不新开一轮
    assert second["turns"][0]["round"] == first["turns"][0]["round"] == 3
    # 红方的发言内容还是原来那段
    assert second["turns"][0]["content"] == first["turns"][0]["content"]


def test_new_question_after_cancel_clears_event(logdir):
    """停止之后又发新问题，是在下新指令，不能继续停着。"""
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]
    orch.request_cancel()
    assert orch.run_followup_debate("不想问这个")["status"] == "cancelled"

    result = orch.run_followup_debate("换个问题：蓝方的数据依据是什么")
    assert result["status"] == "success"
    # 新一轮从第 4 轮起算，和上一轮连成一条时间线
    assert result["turns"][0]["round"] == 4


def test_resume_without_prior_state_starts_new_round(logdir):
    """没有可续的现场时，resume 退化成一次普通追问，不能崩。"""
    orch = _make_orchestrator(logdir)
    _patch_agents(orch)
    orch.news_data = [{"title": "t", "summary": "s"}]

    result = orch.run_followup_debate("直接开始", resume=True)
    assert result["status"] == "success"
    assert result["turns"][0]["round"] == 3
