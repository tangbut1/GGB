from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

__all__ = ["load_local_table"]


COLUMN_ALIASES: Dict[str, List[str]] = {
    "title": ["title", "标题", "新闻标题", "名称", "name"],
    "content": ["content", "正文", "新闻内容", "内容", "text", "文本", "body"],
    "summary": ["summary", "摘要", "简介", "概述", "description"],
    "publish_time": ["publish_time", "发布时间", "时间", "日期", "date", "publish_date"],
    "source": ["source", "来源", "媒体", "渠道", "platform"],
    "category": ["category", "类别", "行业", "类型", "板块"]
}


def load_local_table(uploaded_file) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """Parse a user uploaded table file into standardised news records."""
    if uploaded_file is None:
        return [], pd.DataFrame()

    suffix = Path(uploaded_file.name).suffix.lower()

    try:
        if suffix in {".csv", ".txt"}:
            df = pd.read_csv(uploaded_file)
        elif suffix in {".xls", ".xlsx"}:
            df = pd.read_excel(uploaded_file)
        elif suffix in {".json"}:
            df = pd.read_json(uploaded_file)
        else:
            # attempt to read as csv regardless of suffix
            df = pd.read_csv(uploaded_file)
    except Exception:
        uploaded_file.seek(0)
        content = uploaded_file.getvalue()
        try:
            df = pd.read_csv(StringIO(content.decode("utf-8")))
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(BytesIO(content))

    normalized_df = _normalize_columns(df.copy())
    records: List[Dict[str, Any]] = normalized_df.to_dict(orient="records")
    return records, normalized_df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    column_map: Dict[str, str] = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            for col in df.columns:
                if col.lower() == alias.lower():
                    column_map[col] = target
                    break
            if target in column_map.values():
                break

    df = df.rename(columns=column_map)

    for required in ["title", "content", "summary", "publish_time", "source", "category"]:
        if required not in df.columns:
            df[required] = ""

    # Ensure text columns are string typed
    for text_col in ["title", "content", "summary", "source", "category"]:
        df[text_col] = df[text_col].fillna("").astype(str)

    if "publish_time" in df.columns:
        df["publish_time"] = df["publish_time"].fillna("").astype(str)

    return df[["title", "content", "summary", "publish_time", "source", "category"]]
