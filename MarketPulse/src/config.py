"""Unified config access — reads config.yaml + env vars, no more dict drilling.

Import this instead of reading config.yaml directly. All values resolve to one source of truth.
Requires: app.py calls `init_config()` once at startup before any agent runs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

_config: Dict[str, Any] | None = None


# ── init ────────────────────────────────────────────────────────────────────

def init_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load + resolve config.yaml once. Called by app.py at import time."""
    global _config

    # Load .env manually since start.sh is deleted
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')

    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    _config = _expand_env(_config)
    _apply_env_overrides(_config)
    return _config


def reload_config(config: dict) -> None:
    """Replace in-memory config (e.g. for testing)."""
    global _config
    _config = config


def _cfg() -> dict:
    if _config is None:
        return {}  # allow standalone usage with built-in defaults
    return _config


# ── env expansion ────────────────────────────────────────────────────────────

def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _apply_env_overrides(config: dict) -> None:
    for agent_key in config.get("agent_llm", {}):
        cfg = config["agent_llm"][agent_key]
        ek = agent_key.upper()

        env_var = f"MP_{ek}_API_KEY"
        if os.environ.get(env_var):
            cfg["api_key"] = os.environ[env_var]

        if os.environ.get("MP_GLOBAL_BASE_URL"):
            cfg["base_url"] = os.environ["MP_GLOBAL_BASE_URL"]
        if os.environ.get("MP_GLOBAL_MODEL"):
            cfg["model"] = os.environ["MP_GLOBAL_MODEL"]

        for suffix in ("BASE_URL", "MODEL", "TIMEOUT", "TEMPERATURE", "MAX_RETRIES"):
            env_var = f"MP_{ek}_{suffix}"
            if os.environ.get(env_var):
                cfg[suffix.lower()] = _coerce_number(os.environ[env_var])


def _coerce_number(v: str) -> str | int | float:
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


# ── typed accessors ──────────────────────────────────────────────────────────

def agent(name: str) -> Dict[str, Any]:
    """Return {base_url, api_key, model, timeout, temperature, max_retries} for one agent."""
    return _cfg().get("agent_llm", {}).get(name, {})


def agent_base_url(name: str) -> str:
    return agent(name).get("base_url", "https://api.openai.com/v1")


def agent_api_key(name: str) -> str:
    return agent(name).get("api_key", "")


def agent_model(name: str) -> str:
    return agent(name).get("model", "gpt-4o-mini")


def agent_timeout(name: str) -> int:
    return int(agent(name).get("timeout", 60))


def agent_temperature(name: str) -> float:
    return float(agent(name).get("temperature", 0.7))


def agent_max_retries(name: str) -> int:
    return int(agent(name).get("max_retries", 1))


def agent_endpoint(name: str) -> str:
    """Return the /chat/completions URL for an agent."""
    base = agent_base_url(name).rstrip("/")
    if not base.endswith("/chat/completions"):
        base = f"{base}/chat/completions"
    return base


# ── sections ─────────────────────────────────────────────────────────────────

def data_dir(key: str, default: str = "") -> str:
    return _cfg().get("data", {}).get(key, default)


def collect() -> dict:
    return _cfg().get("collect", {})


def collect_max(mode: str) -> int:
    return _cfg().get("collect", {}).get("max_results", {}).get(mode, 300)


def collect_min(mode: str) -> int:
    return _cfg().get("collect", {}).get("min_results", {}).get(mode, 200)


def collect_retries() -> int:
    return _cfg().get("collect", {}).get("retries", 3)


def collect_timeout() -> int:
    return _cfg().get("collect", {}).get("timeout", 15)


def host_research_max() -> int:
    return _cfg().get("collect", {}).get("host_research_max_results", 60)


def collect_cache_ttl() -> int:
    return _cfg().get("collect", {}).get("cache_ttl", 3600)


def analysis_forecast_periods(default: int = 30) -> int:
    return _cfg().get("analysis", {}).get("forecast_periods", default)


def analysis_use_prophet() -> bool:
    return _cfg().get("analysis", {}).get("use_prophet", True)


def report_pdf() -> bool:
    return _cfg().get("report", {}).get("enable_pdf", True)


def report_docx() -> bool:
    return _cfg().get("report", {}).get("enable_docx", True)


def report_html() -> bool:
    return _cfg().get("report", {}).get("enable_html", True)


def forum_trigger_threshold() -> int:
    return _cfg().get("agent_llm", {}).get("forum_host", {}).get("trigger_threshold", 5)


def forum_wait_timeout() -> int:
    return _cfg().get("agent_llm", {}).get("forum_host", {}).get("wait_timeout", 15)


def knowledge_db_path() -> str:
    return _cfg().get("data", {}).get(
        "knowledge_db_path", "data/knowledge/events.sqlite3"
    )


def results_dir() -> str:
    return _cfg().get("data", {}).get("results_dir", "results")

import logging
import sys

def setup_logger(name: str = "MarketPulse") -> logging.Logger:
    """Set up and return a standard unified logger for the system."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s')
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Optional: Add file handler
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "system.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

logger = setup_logger()

class SimpleLoguruWrapper:
    def __init__(self, name="MarketPulse"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s - %(message)s')
            
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(log_dir / "system.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _format(self, msg, *args):
        if args:
            if "{}" in msg:
                # Naive replacement of {} with %s
                msg = msg.replace("{}", "%s")
            return msg % args
        return msg

    def info(self, msg, *args):
        self.logger.info(self._format(msg, *args))

    def debug(self, msg, *args):
        self.logger.debug(self._format(msg, *args))

    def warning(self, msg, *args):
        self.logger.warning(self._format(msg, *args))

    def error(self, msg, *args):
        self.logger.error(self._format(msg, *args))

    def success(self, msg, *args):
        # logging has no success, use info
        self.logger.info(self._format("[SUCCESS] " + msg, *args))

logger = SimpleLoguruWrapper()
