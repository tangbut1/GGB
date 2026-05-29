# MarketPulse Knowledge Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first production slice of the approved nashsu-inspired upgrade: source-aware collection, persistent event knowledge, stronger event graph metadata, and reliable Host-guided second-round orchestration.

**Architecture:** Keep the existing Flask + SocketIO + multi-agent pipeline. Add small backend modules around current code instead of replacing it: a collection provider facade, a SQLite-backed event store, and graph enrichment utilities consumed by the existing orchestrator/report flow.

**Tech Stack:** Python stdlib, SQLite, existing Flask/Agent modules, existing vis-network-compatible node/edge JSON, `unittest` for focused tests.

---

### Task 1: Source-Aware Collection Provider

**Files:**
- Create: `MarketPulse/src/collect/providers.py`
- Modify: `MarketPulse/src/agents/collect_agent.py`
- Test: `MarketPulse/tests/test_collect_providers.py`

- [ ] **Step 1: Write failing tests**

Add tests that verify provider output gets stable `source_id`, `source_ref`, `url`, `domain`, `collected_at`, and `content_hash` fields.

- [ ] **Step 2: Run red test**

Run: `python3 tests/test_collect_providers.py` from `MarketPulse/`.
Expected: FAIL because `src.collect.providers` does not exist.

- [ ] **Step 3: Implement minimal provider layer**

Create `SourceAwareCollector` around `CustomSearchCollector`, plus pure helpers for URL/domain/hash normalization. Modify `CollectAgent` to use it and pass `collect_meta.sources`.

- [ ] **Step 4: Run green test**

Run: `python3 tests/test_collect_providers.py`.
Expected: PASS.

### Task 2: Persistent Event Store

**Files:**
- Create: `MarketPulse/src/knowledge/event_store.py`
- Create: `MarketPulse/src/knowledge/__init__.py`
- Test: `MarketPulse/tests/test_event_store.py`

- [ ] **Step 1: Write failing tests**

Add tests for storing one task's analyzed events with source references and loading them by keyword.

- [ ] **Step 2: Run red test**

Run: `python3 tests/test_event_store.py`.
Expected: FAIL because `src.knowledge.event_store` does not exist.

- [ ] **Step 3: Implement SQLite store**

Create `EventStore` with `save_task_events()` and `find_recent_by_keyword()`. Store task id, keyword, title, summary, sentiment, score, source refs, published time, created time, and content hash.

- [ ] **Step 4: Run green test**

Run: `python3 tests/test_event_store.py`.
Expected: PASS.

### Task 3: Event Graph Enrichment

**Files:**
- Modify: `MarketPulse/src/analysis/event_extractor.py`
- Test: `MarketPulse/tests/test_event_graph.py`

- [ ] **Step 1: Write failing tests**

Add tests that expect graph nodes to include `source_refs`, `evidence_count`, and `relevance_score`, and edges to include `relation_signals`.

- [ ] **Step 2: Run red test**

Run: `python3 tests/test_event_graph.py`.
Expected: FAIL because current graph output lacks these fields.

- [ ] **Step 3: Implement enrichment**

Keep existing frontend-compatible fields. Add source reference aggregation and relation signal scoring based on shared source refs, platform match, sentiment alignment, and date proximity.

- [ ] **Step 4: Run green test**

Run: `python3 tests/test_event_graph.py`.
Expected: PASS.

### Task 4: Host Wait and Knowledge Persistence Wiring

**Files:**
- Modify: `MarketPulse/src/forum/monitor.py`
- Modify: `MarketPulse/src/agents/orchestrator.py`
- Test: `MarketPulse/tests/test_host_wait.py`

- [ ] **Step 1: Write failing tests**

Add tests around a fake monitor/forum manager proving the orchestrator can wait for Host guidance without fixed `sleep(3)`.

- [ ] **Step 2: Run red test**

Run: `python3 tests/test_host_wait.py`.
Expected: FAIL because `ForumMonitor.wait_for_host_guidance` does not exist.

- [ ] **Step 3: Implement wait API and persistence**

Add a threading event to `ForumMonitor`, expose `wait_for_host_guidance(timeout)`, update orchestrator to use it, trigger second-round collection when Host guidance exists, and persist analyzed news through `EventStore`.

- [ ] **Step 4: Run green test**

Run: `python3 tests/test_host_wait.py`.
Expected: PASS.

### Task 5: Verification

**Files:**
- No production changes.

- [ ] **Step 1: Run focused tests**

Run:
`python3 tests/test_collect_providers.py`
`python3 tests/test_event_store.py`
`python3 tests/test_event_graph.py`
`python3 tests/test_host_wait.py`

- [ ] **Step 2: Check existing smoke tests**

Run:
`python3 tests/test_forum.py`
`python3 tests/test_agents.py`

Expected: existing tests may still require dependency/path cleanup; record exact failures instead of hiding them.
