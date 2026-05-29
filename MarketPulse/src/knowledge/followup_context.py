from __future__ import annotations

from typing import Any, Dict


def build_followup_user_prompt(
    mode_desc: str,
    context_headline: str,
    insight: Dict[str, Any],
    question: str,
    knowledge_context: str = "",
) -> str:
    context_block = ""
    if knowledge_context:
        context_block = f"\n\n可引用的历史事件：\n{knowledge_context}"

    return f"""数据源类型：{mode_desc}
背景分析结论：{context_headline}
{context_block}

用户关注的洞察：
- 标题：{insight.get('title', '')}
- 判断：{insight.get('claim', '')}
- 依据：{insight.get('evidence', '')}

用户追问：{question}"""
