# Dagster Pipeline Principles

This documentation captures the key architectural patterns and principles for building production-grade data pipelines with Dagster.

## Principles Index

| # | Principle | Summary |
|---|-----------|---------|
| [01](01-code-versioning.md) | **Code Versioning & Staleness** | Track code changes to avoid unnecessary re-runs |
| [02](02-auto-materialize-policies.md) | **Auto-Materialization** | Automatically trigger runs when dependencies change |
| [03](03-freshness-policies.md) | **Deterministic Staleness** | Stale = input changed OR code changed (NOT time-based) |
| [04](04-sensors.md) | **Sensors** | React to external events (new records, files, webhooks) |
| [05](05-dynamic-partitions.md) | **Dynamic Partitions** | Process records individually as they arrive |
| [06](06-cross-join-matching.md) | **Cross-Join Matching** | Match new entities against all existing entities |
| [07](07-llm-cost-tracking.md) | **LLM Cost Tracking** | Track costs per asset/run, estimate before deploying |

### Troubleshooting

| Doc | Topic |
|-----|-------|
| [Dagster termination thread / semaphore issue](../dagster-termination-thread-semaphore-issue.md) | macOS semaphore exhaustion with multiprocess executor; investigation and workarounds |

## Quick Reference

### Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Command | `dagster dev` | `dagster-webserver` + `dagster-daemon` |
| Storage | Temporary SQLite | PostgreSQL |
| Sensors | Manual trigger | Auto-running |
| Auto-materialize | Disabled | Enabled |

### When to Use Each Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                    Pattern Selection Guide                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  "I want to avoid re-running unchanged assets"              │
│  └── Use Code Versioning (01) + Staleness detection        │
│                                                             │
│  "I want assets to update automatically"                    │
│  └── Use Auto-Materialize Policies (02)                    │
│                                                             │
│  "I want staleness based on actual changes, not time"       │
│  └── Use Deterministic Staleness (03)                      │
│                                                             │
│  "I want to react when new data arrives"                    │
│  └── Use Sensors (04)                                      │
│                                                             │
│  "I want to process records individually"                   │
│  └── Use Dynamic Partitions (05)                           │
│                                                             │
│  "I want to match new X against all Y"                      │
│  └── Use Cross-Join Pattern (06)                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Talent Matching Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Asset Dependency Graph                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CANDIDATE PIPELINE              JOB PIPELINE               │
│                                                             │
│  raw_candidates ──────┐     ┌────── raw_jobs               │
│        │              │     │           │                   │
│        ▼              │     │           ▼                   │
│  normalized_candidates│     │    normalized_jobs            │
│        │              │     │           │                   │
│        ▼              │     │           ▼                   │
│  candidate_vectors    │     │      job_vectors              │
│        │              │     │           │                   │
│        └──────────────┼─────┼───────────┘                   │
│                       │     │                               │
│                       ▼     ▼                               │
│                    ┌─────────────┐                          │
│                    │   matches   │                          │
│                    └─────────────┘                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Resources

- [Dagster Documentation](https://docs.dagster.io/)
- [Dagster GitHub](https://github.com/dagster-io/dagster)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
