# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Entry Points

- **`MarketPulse/app.py`** — Flask + SocketIO web app (primary). Start with `bash start.sh` or `python3 -m flask run --host=0.0.0.0 --port=5050`. Serves SPA at `/`, SSE at `/stream/<task_id>`, API at `/analyze`, `/followup`, `/status`, `/history`.
- **`MarketPulse/main.py`** — Streamlit standalone dashboard (secondary, for local Agent testing). `streamlit run main.py`.

These two entry points are **completely independent**. `main.py` does not use the multi-agent forum architecture — it calls `src/` modules directly via the older pipeline (NewsCollector → DataCleaner → SentimentAnalyzer → TrendPredictor). `app.py` is the real system.

## Commands

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # then edit with real API keys

# Run web app
bash start.sh

# Run Streamlit dashboard
streamlit run main.py

# Run individual tests (must run from MarketPulse/ directory)
python3 tests/test_agents.py      # CollectAgent standalone
python3 tests/test_forum.py       # Forum Monitor + Host trigger mechanism
```

## Architecture: Multi-Agent Forum System

Five agents plus an orchestrator and a forum monitor, inspired by the BettaFish architecture pattern.

### Agents (extend `BaseAgent`)

Each agent has `run(input_data) → {status, data, summary}` and calls LLM via `call_llm(prompt)` or `call_llm_with_system(sys, usr)`. All use OpenAI-compatible API (configurable per-agent).

| Agent | Role | Key dependency |
|---|---|---|
| `CollectAgent` | Multi-source search (Google RSS → DDG → Bing) + local data merge | `custom_search.py`, `DataCleaner` |
| `SentimentAgent` | SnowNLP scoring + LLM校正 (corrects SnowNLP's positive bias on Chinese financial text) | `SentimentAnalyzer` |
| `TrendAgent` | Prophet time-series prediction + data quality rating | `TrendPredictor` |
| `ReportAgent` | HTML report generation + AI insights JSON + forum debate extraction | `export_html.py`, `EventExtractor` |
| `LLMHost` | Forum moderator — summarizes agent findings, identifies blind spots, guides next round | Called by `ForumMonitor` |

### Pipeline (`OrchestratorAgent.run_pipeline()`)

```
Collect → Sentiment → Trend → [wait Monitor triggers Host] → optional Round 2 (if Host feedback) → Report (HTML + event graph)
```

- Trend failure is **non-fatal** — injects degraded fallback summary so downstream stages still get data.
- If no real search results, CollectAgent injects **mock data** to keep the pipeline running.

### Forum Mechanism

- **`LogManager`**: Thread-safe file append to `logs/forum_{task_id}.log`. Every agent writes findings here.
- **`ForumMonitor`**: Daemon thread polls log, counts non-HOST/non-SYSTEM messages. Triggers Host LLM when ≥5 agent messages or 10s idle since last message.
- **Host guidance** is written back to the forum log and read by the orchestrator for Round 2 iteration.

### Configuration Hierarchy (env vars override config.yaml)

```
MP_{AGENT}_MODEL / MP_{AGENT}_BASE_URL   (per-agent, highest)
  → MP_GLOBAL_MODEL / MP_GLOBAL_BASE_URL  (global)
    → config.yaml defaults                 (lowest)
```

Each of the 5 agents + forum_host gets its own API key via `MP_{COLLECT|SENTIMENT|TREND|REPORT|FORUM_HOST}_AGENT_API_KEY`.

### Frontend

Single HTML file (`templates/index.html`). Left panel: keyword input, mode selector (social/news), agent status indicators. Right panel: 4 tabs — Overview, Charts (Chart.js), Event Graph (vis-network directed causal graph), AI Insights (SSE streaming follow-up). SocketIO pushes agent status updates and log lines in real time.

## Key Patterns

- **All LLM calls** go through `BaseAgent._call_llm_inner()` → OpenAI-compatible `/chat/completions` endpoint, 60s timeout, no retry.
- **JSON extraction from LLM responses** uses 4-level fallback: direct parse → strip code fences → find `{...}` slice → regex match. The ReportAgent adds a 5th level: Markdown structure parsing when JSON is entirely absent.
- **Sentiment correction**: SnowNLP systematically under-reports negative sentiment for Chinese financial/political text. SentimentAgent sends SnowNLP results + samples to LLM for correction, then applies label redistribution sorted by score.
- **`src/config.yaml`** uses `${ENV_VAR}` placeholders expanded at startup by `_expand_env()` in `app.py`.
- The `data/` directory caches search results; `results/reports/` holds generated HTML reports.
