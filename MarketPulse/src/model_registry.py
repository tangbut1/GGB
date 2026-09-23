"""用户自配模型的注册表。

config.yaml 里的 ``agent_llm`` 是部署时写死的一套配置（6 个 Agent 各自一个
Key）。这个模块提供另一层：用户在前端设置面板里加进来的模型，按需切换。

和 config.yaml 的分工：

- config.yaml 是**默认值**，没在面板里选模型时照常生效；
- 面板里选的模型是一次**请求级的全局覆盖**——把它写进每个 Agent 的
  base_url / api_key / model，红蓝双方和裁判都用它。

不做"某个 Agent 单独用某个模型"的细粒度配置：那不是用户要的，而且会让
"我到底在用哪个模型"变成一个需要查表才能回答的问题。

落盘是一个 JSON 文件而不是数据库：条目是个位数、写频率是分钟级，引入
sqlite 只会多一处需要迁移的 schema。API Key 明文存放——它本来就只有
本机进程能读，加密起来反而给用户一个"很安全"的错觉，而密钥就在同一台
机器上。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .net_safety import validate_public_url

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _PROJECT_ROOT / "data" / "models.json"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 单个模型的字段白名单。面板提交什么就存什么，但只认这些键——多出来的
# 一律丢掉，否则用户能往配置文件里塞任意结构，下游读取方就要各自防御。
_FIELDS = ("name", "base_url", "api_key", "model", "temperature", "timeout",
           "max_retries", "note")


def _mask(key: str) -> str:
    """Key 只回显后 4 位。前端要能判断"这个 Key 是不是刚改过"，全遮住就
    只能靠猜；全显示则等于把密钥摊在接口上。"""
    if not key:
        return ""
    tail = key[-4:]
    return f"{'*' * 12}{tail}"


def _slug(text: str) -> str:
    """把模型名转成 id 的安全部分。中文名转不出 ASCII，退回随机后缀。"""
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:24]
    return ascii_part or "model"


class ModelRegistry:
    """线程安全的模型配置存取。所有方法都过同一把锁，避免并发写丢条目。"""

    def __init__(self, path: str | os.PathLike | None = None):
        self._path = Path(path) if path else _DEFAULT_PATH
        # RLock：set_active 里要读一次再写一次，普通 Lock 会自己锁死
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {"active_id": None, "models": []}
        self._load()

    # ── 读写 ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        models = raw.get("models")
        if isinstance(models, list):
            self._data = {
                "active_id": raw.get("active_id"),
                "models": [m for m in models if isinstance(m, dict)],
            }

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        # 先写临时文件再原子替换：直接覆盖会让"读到一半的 JSON"成为可能，
        # 而下一次启动 _load 解析失败就等于所有模型配置静默消失。
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    # ── 查询 ─────────────────────────────────────────────────────────────

    def list_models(self) -> List[Dict[str, Any]]:
        """全部模型，Key 已遮罩。这是唯一能出到前端的视图。"""
        with self._lock:
            out = []
            for entry in self._data["models"]:
                out.append(self._public_view(entry))
            return out

    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        """取完整条目（含明文 Key）。只供服务端内部使用，不要直接返回给前端。"""
        with self._lock:
            for entry in self._data["models"]:
                if entry.get("id") == model_id:
                    return dict(entry)
            return None

    def get_active(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            active_id = self._data.get("active_id")
            if not active_id:
                return None
            for entry in self._data["models"]:
                if entry.get("id") == active_id:
                    return dict(entry)
            return None

    def active_id(self) -> Optional[str]:
        with self._lock:
            return self._data.get("active_id")

    # ── 变更 ─────────────────────────────────────────────────────────────

    def upsert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """新增或更新一个模型。返回遮罩后的视图。

        ``payload['id']`` 存在则更新，否则新建。更新是**按字段合并**的：
        表单只提交用户改过的字段也合法，没提交的保持原值。其中 api_key 是
        特例——前端表单里它是遮罩回显的，用户没动它就会把一串星号提交上来，
        所以遮罩串一律当作"没提供"，保留旧 Key。
        """
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是对象")

        model_id = str(payload.get("id") or "").strip()
        creating = not model_id

        with self._lock:
            existing = None
            if creating:
                model_id = ""
            else:
                for candidate in self._data["models"]:
                    if candidate.get("id") == model_id:
                        existing = candidate
                        break
                if existing is None:
                    raise ValueError(f"模型不存在: {model_id}")

            entry = self._validate(payload, existing)

            if existing is None:
                model_id = f"{_slug(entry['name'])}_{uuid.uuid4().hex[:6]}"
                new_entry = {"id": model_id, "created_at": _now_iso()}
                new_entry.update(entry)
                self._data["models"].append(new_entry)
            else:
                existing.update(entry)
                existing["updated_at"] = _now_iso()
                new_entry = existing

            # 第一个模型自动成为当前选用：面板里刚加完却还是"未选择"，
            # 用户会以为没保存成功。
            if not self._data.get("active_id"):
                self._data["active_id"] = model_id

            self._save_locked()
            return self._public_view(new_entry)

    def delete(self, model_id: str) -> bool:
        with self._lock:
            before = len(self._data["models"])
            self._data["models"] = [
                m for m in self._data["models"] if m.get("id") != model_id
            ]
            if len(self._data["models"]) == before:
                return False
            if self._data.get("active_id") == model_id:
                # 删的是当前选用的那个：不要留一个指向不存在条目的 active_id，
                # 否则每次请求都会静默回落到 config.yaml，用户看不出为什么
                # 换了模型没反应。改指剩下的第一个，没有就置空。
                remaining = self._data["models"]
                self._data["active_id"] = remaining[0]["id"] if remaining else None
            self._save_locked()
            return True

    def set_active(self, model_id: Optional[str]) -> None:
        """设置当前选用的模型。传空表示"用 config.yaml 的默认配置"。"""
        with self._lock:
            if model_id in (None, ""):
                self._data["active_id"] = None
            else:
                if not any(m.get("id") == model_id for m in self._data["models"]):
                    raise ValueError(f"模型不存在: {model_id}")
                self._data["active_id"] = model_id
            self._save_locked()

    # ── 校验 ─────────────────────────────────────────────────────────────

    def _validate(self, payload: Dict[str, Any],
                  existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """校验并抽出要写入的字段。

        ``existing`` 为 None 表示新建：四个核心字段一个都不能少，否则这个
        模型从一开始就调不通。非 None 表示更新：只校验提交上来的字段，没
        提交的留在原条目里不动。
        """
        creating = existing is None
        entry: Dict[str, Any] = {}

        name = str(payload.get("name") or "").strip()
        if name:
            if len(name) > 60:
                raise ValueError("模型名称过长（≤60 字符）")
            entry["name"] = name
        elif creating:
            raise ValueError("模型名称不能为空")
        elif "name" in payload:
            # 显式提交了空名 = 想把名字清空，那不行
            raise ValueError("模型名称不能为空")

        base_url = str(payload.get("base_url") or "").strip()
        if base_url:
            # 和 BaseAgent 调用 LLM 走同一道校验：这里提前拒掉内网地址，
            # 用户当场看到错误，而不是等第一次分析跑了一半才失败。
            # MP_ALLOW_PRIVATE_LLM_ENDPOINTS 的逃生口也共用同一判据——
            # 本地 Ollama / vLLM 是合理配置，但默认必须是关的。
            try:
                validate_public_url(base_url)
            except ValueError as e:
                raise ValueError(f"Base URL 不被允许: {e}") from e
            entry["base_url"] = base_url.rstrip("/")
        elif creating:
            raise ValueError("Base URL 不能为空")
        elif "base_url" in payload:
            raise ValueError("Base URL 不能为空")

        api_key = str(payload.get("api_key") or "").strip()
        if api_key.startswith("*"):
            # 遮罩串被原样提交回来了（用户没改 Key）。当成"未提供"处理，
            # 保留旧值——把星号存进去会让这个模型从此再也调不通。
            api_key = ""
        if api_key:
            if creating and len(api_key) < 8:
                raise ValueError("API Key 过短，疑似填写不完整")
            entry["api_key"] = api_key
        elif creating:
            raise ValueError("API Key 不能为空")

        model = str(payload.get("model") or "").strip()
        if model:
            entry["model"] = model
        elif creating:
            raise ValueError("模型 ID 不能为空")
        elif "model" in payload:
            raise ValueError("模型 ID 不能为空")

        for key in ("temperature", "timeout", "max_retries"):
            if payload.get(key) in (None, ""):
                continue
            try:
                entry[key] = type(_defaults()[key])(payload[key])
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} 必须是数字") from e
        if "temperature" in entry:
            entry["temperature"] = min(max(float(entry["temperature"]), 0.0), 2.0)
        if "timeout" in entry:
            entry["timeout"] = min(max(int(entry["timeout"]), 10), 600)
        if "max_retries" in entry:
            entry["max_retries"] = min(max(int(entry["max_retries"]), 1), 5)

        note = str(payload.get("note") or "").strip()[:200]
        if note or "note" in payload:
            entry["note"] = note

        return entry

    # ── 视图 ─────────────────────────────────────────────────────────────

    def _public_view(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        out = {
            "id": entry.get("id", ""),
            "name": entry.get("name", ""),
            "base_url": entry.get("base_url", ""),
            "model": entry.get("model", ""),
            "temperature": entry.get("temperature", 0.7),
            "timeout": entry.get("timeout", 120),
            "max_retries": entry.get("max_retries", 2),
            "note": entry.get("note", ""),
            "api_key_masked": _mask(entry.get("api_key", "")),
            "has_api_key": bool(entry.get("api_key")),
        }
        if entry.get("created_at"):
            out["created_at"] = entry["created_at"]
        if entry.get("updated_at"):
            out["updated_at"] = entry["updated_at"]
        return out


def _defaults() -> Dict[str, Any]:
    return {"temperature": 0.7, "timeout": 120, "max_retries": 2}


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat()


def config_override(entry: Dict[str, Any]) -> Dict[str, Any]:
    """把一个模型条目转成 agent_llm 条目的覆盖字段。

    只取 LLM 调用真正会读的五个键。多一个键就多一处"用户以为改了其实
    没用"的可能。
    """
    return {
        "base_url": entry.get("base_url", ""),
        "api_key": entry.get("api_key", ""),
        "model": entry.get("model", ""),
        "temperature": entry.get("temperature", 0.7),
        "timeout": entry.get("timeout", 120),
        "max_retries": entry.get("max_retries", 2),
    }
