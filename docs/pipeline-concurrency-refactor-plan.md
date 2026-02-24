# Pipeline Concurrency Refactor Plan

## Problem Statement

Our Dagster pipeline uses **one run per partition** (one subprocess per Airtable record).
Each run spawns a full Python process that consumes:

| Resource per run         | Cost           |
| ------------------------ | -------------- |
| RAM                      | ~100–200 MB    |
| DB connections           | ~5 (dagster event log, run storage, postgres_io, pgvector_io, matchmaking) |
| Startup overhead         | ~2–3 seconds   |

With 200 candidates, a backfill creates 200 subprocesses. On our 16 GB machine with
PostgreSQL `max_connections=200`, we're capped at ~30 concurrent runs and we still
hit swap pressure.

**Meanwhile, the actual work is I/O-bound** — we're waiting on OpenRouter LLM calls
(~3–10s each) and Airtable API calls (~200ms each). CPU usage per run is negligible.
We're paying a heavy process overhead to wait on network I/O.

---

## Current Architecture

```
Backfill (200 partitions)
  └─ Run 1 (subprocess, PID 1001) ── partition rec_abc
  │    └─ airtable_candidates → raw_candidates → normalized_candidates → candidate_vectors → ...
  │    └─ 5 DB connections, ~150 MB RAM
  └─ Run 2 (subprocess, PID 1002) ── partition rec_def
  │    └─ (same pipeline, same overhead)
  └─ ... × 200
```

**Concurrency is limited by system resources, not by API rate limits.**

---

## Target Architecture

Process multiple records within a **single run** using async I/O, reducing subprocess
count from N to 1 (or a small number of chunked runs).

```
Single Run (1 subprocess)
  └─ airtable_candidates (batch fetch: 200 records in 1 API call)
  └─ raw_candidates (concurrent PDF extraction: 30 async tasks)
  └─ normalized_candidates (concurrent LLM calls: 30 async tasks)
  └─ candidate_vectors (batch embedding: 1 API call)
  └─ airtable_candidate_sync (batch PATCH: batches of 10)
  └─ Total: 1 subprocess, 5 DB connections, ~300 MB RAM
```

---

## Refactor Phases

### Phase 1: Batch-mode assets (unpartitioned path)

**Goal**: Add a batch execution mode alongside the existing partitioned mode, so a
single run can process many records without spawning N subprocesses.

**Approach**: Each asset already receives a single partition key and processes one record.
We add a **non-partitioned code path** that fetches all pending records and processes
them in a loop with concurrency control.

```python
@asset(
    io_manager_key="postgres_io",
    required_resource_keys={"openrouter"},
    tags={"dagster/concurrency_key": "openrouter_api"},
)
def normalized_candidates_batch(
    context: AssetExecutionContext,
    raw_candidates_batch: list[dict],
) -> list[dict]:
    """Normalize all candidates in a single run with async concurrency."""
    semaphore = asyncio.Semaphore(30)  # max 30 concurrent LLM calls

    async def normalize_one(record):
        async with semaphore:
            return await normalize_cv_async(record, context.resources.openrouter)

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(
        asyncio.gather(*[normalize_one(r) for r in raw_candidates_batch])
    )
    return results
```

**Resource savings**:

| Metric                | Before (200 partitions) | After (1 batch run) |
| --------------------- | ---------------------- | ------------------- |
| Subprocesses          | 200                    | 1                   |
| DB connections        | 1,000                  | 5                   |
| RAM                   | 20–40 GB               | ~300 MB             |
| Concurrent LLM calls  | 30 (limited by runs)  | 30 (limited by semaphore) |

**Partition updates**: The batch asset still writes partition-level materializations
to the Dagster event log so the asset catalog stays consistent. We use
`context.instance.report_runless_asset_event` or output metadata per partition key.

---

### Phase 2: Async HTTP clients in resources

**Goal**: Replace synchronous `httpx.Client` (created per request) with a shared
`httpx.AsyncClient` that pools connections.

**Current** (in `AirtableResource` and `OpenRouterResource`):
```python
with httpx.Client() as client:
    response = client.get(url, headers=headers)
```
A new TCP connection is created, TLS handshake happens, and the connection is torn
down for every single API call.

**Target**:
```python
class AirtableResource(ConfigurableResource):
    _client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"https://api.airtable.com/v0/{self.base_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                timeout=30.0,
            )
        return self._client
```

**Benefits**:
- Connection reuse (HTTP/2 multiplexing where supported)
- Bounded connection pool (no runaway TCP connections)
- Works naturally with `asyncio.Semaphore` for rate limiting

---

### Phase 3: Connection pooling for application DB

**Goal**: Explicitly configure SQLAlchemy connection pool sizes so they don't grow
unboundedly.

**Current**: IO managers create engines with SQLAlchemy defaults (`pool_size=5`,
`max_overflow=10` — up to 15 connections per engine). With 3 engines
(postgres_io, pgvector_io, matchmaking), that's up to 45 connections from a single run.

**Target**: Set explicit pool sizes appropriate for batch mode:

```python
engine = create_engine(
    connection_string,
    pool_size=3,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=1800,
)
```

With batch mode (1 run), 3 engines × 5 max connections = 15 total application
connections, plus ~10 for Dagster internals = ~25 total. Well within 200.

---

### Phase 4: Chunked batch runs (scaling beyond single machine)

**Goal**: For very large backlogs (1000+ records), split into chunked runs of
50–100 records each so that a single failure doesn't require reprocessing everything.

**Approach**: A sensor or op determines the pending records, chunks them, and
launches N batch runs (each processing 50–100 records):

```
Sensor detects 500 new candidates
  └─ Batch Run 1: records 1–100 (30 concurrent LLM calls)
  └─ Batch Run 2: records 101–200
  └─ ... × 5 runs total
```

**Resource usage**: 5 runs × 5 connections = 25 DB connections, 5 × 300 MB = 1.5 GB RAM.
Still processes 30 LLM calls concurrently within each run.

---

### Phase 5: Rate limit awareness

**Goal**: Handle API rate limits gracefully with backpressure instead of relying on
Dagster's retry policy (which retries the entire asset step, not individual API calls).

**Approach**: Add a rate-limit-aware wrapper:

```python
class RateLimitedClient:
    def __init__(self, max_concurrent: int = 30, rpm_limit: int = 500):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rpm_limit = rpm_limit
        self._request_times: deque[float] = deque()

    async def request(self, coro):
        async with self.semaphore:
            await self._wait_for_rate_limit()
            return await coro
```

This replaces the current approach of using Dagster concurrency pools
(`dagster/concurrency_key`) for per-request rate limiting — those pools limit
concurrent *runs*, not concurrent *requests within a run*.

---

## Migration Strategy

The refactor is **additive** — we keep the existing partitioned assets and jobs
so nothing breaks. New batch-mode assets coexist alongside them.

```
Phase 1 ──────────────────────────────────────────────── 2–3 days
  - Add batch-mode candidate pipeline (unpartitioned)
  - Add batch-mode job pipeline (unpartitioned)
  - Add batch job definitions
  - Keep partitioned jobs for single-record reruns

Phase 2 ──────────────────────────────────────────────── 1 day
  - Refactor AirtableResource to use async client
  - Refactor OpenRouterResource to use async client
  - Add shared httpx.AsyncClient lifecycle

Phase 3 ──────────────────────────────────────────────── 0.5 day
  - Add explicit pool_size to all create_engine calls
  - Fix OpenRouter cost tracking (shared engine, not per-write)

Phase 4 ──────────────────────────────────────────────── 1 day
  - Add chunking sensor/op
  - Configurable chunk_size via run config

Phase 5 ──────────────────────────────────────────────── 0.5 day
  - Add RateLimitedClient wrapper
  - Integrate with OpenRouter and Airtable resources
```

---

## Concurrency Tuning Guide

After the refactor, the knobs to tune are:

| Knob                        | Where                     | Default | Meaning |
| --------------------------- | ------------------------- | ------- | ------- |
| `LLM_CONCURRENCY`          | Env var / run config      | 30      | Max concurrent LLM calls per run |
| `AIRTABLE_CONCURRENCY`     | Env var / run config      | 10      | Max concurrent Airtable API calls per run |
| `BATCH_CHUNK_SIZE`          | Sensor config             | 100     | Records per batch run |
| `max_concurrent_runs`       | dagster.yaml              | 5       | Max simultaneous batch runs (was 30 for single-record runs) |
| `pool_size`                 | IO manager config         | 3       | SQLAlchemy connections per engine |
| `max_connections`           | postgresql.conf           | 200     | Total PostgreSQL connection slots |

**Relationship**: `max_concurrent_runs × (3 engines × (pool_size + max_overflow)) + dagster_overhead < max_connections`

Example: `5 runs × 15 conns + 25 overhead = 100 < 200` — comfortable headroom.

---

## Rollback Plan

Every phase is independent and additive:

- **Phase 1**: New batch jobs live alongside old partitioned jobs. Remove batch jobs to roll back.
- **Phase 2**: Async clients are internal to resources. Revert the resource files.
- **Phase 3**: Pool size changes are configuration only.
- **Phase 4**: Chunking sensor is a new sensor. Disable it to roll back.
- **Phase 5**: Rate limiter wraps existing calls. Remove the wrapper to roll back.

---

## Expected Outcome

| Metric                     | Current (30 partitioned runs) | Target (1 batch run) | Improvement |
| -------------------------- | ----------------------------- | -------------------- | ----------- |
| DB connections             | 150                           | 25                   | 6×          |
| RAM usage                  | 3–6 GB                        | ~300 MB              | 10–20×      |
| Subprocess count           | 30                            | 1                    | 30×         |
| Concurrent LLM calls       | 30                           | 30                   | Same        |
| Throughput (records/min)    | ~30 (limited by runs)        | ~30 (limited by semaphore) | Same, with room to increase |
| Startup overhead           | 60–90s (30 processes)         | 2–3s (1 process)     | 30×         |
| Max records before OOM     | ~80                           | 1000+                | 12×         |
