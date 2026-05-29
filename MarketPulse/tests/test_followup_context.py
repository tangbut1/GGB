import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.followup_context import build_followup_user_prompt


def test_followup_prompt_includes_historical_event_context_when_available():
    prompt = build_followup_user_prompt(
        mode_desc="专业新闻媒体报道",
        context_headline="供应链风险升温",
        insight={"title": "交付风险", "claim": "短期风险抬升", "evidence": "负面新闻增加"},
        question="这个风险会持续多久？",
        knowledge_context="历史事件上下文：\n[event:1] 华为交付风险升温",
    )

    assert "历史事件上下文" in prompt
    assert "[event:1] 华为交付风险升温" in prompt
    assert "用户追问：这个风险会持续多久？" in prompt


if __name__ == "__main__":
    test_followup_prompt_includes_historical_event_context_when_available()
