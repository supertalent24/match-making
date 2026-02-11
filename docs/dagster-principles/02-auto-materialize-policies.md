# Principle: Auto-Materialization Policies

## Problem

Manually clicking "Materialize" in the UI works for development, but in production you want assets to update automatically when their dependencies change.

## Solution

Auto-materialize policies let Dagster automatically decide when to re-run assets based on upstream changes.

## Implementation

### Eager Policy (Default Recommendation)

Materialize as soon as any upstream asset changes:

```python
from dagster import asset, AutoMaterializePolicy

@asset(
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def normalized_candidates(raw_candidates):
    """Runs automatically when raw_candidates is updated."""
    ...
```

### Lazy Policy

Only materialize when explicitly requested (useful for expensive operations):

```python
@asset(
    auto_materialize_policy=AutoMaterializePolicy.lazy(),
)
def candidate_vectors(normalized_candidates):
    """Only runs when manually triggered, even if upstream changed."""
    ...
```

## Policy Comparison

| Policy | Behavior | Use Case |
|--------|----------|----------|
| `eager()` | Run immediately when upstream changes | Real-time pipelines, cheap operations |
| `lazy()` | Wait for manual trigger | Expensive LLM calls, batch processing |
| None | Never auto-materialize | Development, debugging |

## Production Setup

For auto-materialization to work, you must run the **dagster-daemon**:

```bash
# In production, run both services:
dagster-webserver -h 0.0.0.0 -p 3000 &
dagster-daemon run &
```

The daemon monitors asset state and triggers materializations based on policies.

## Combining with Schedules

You can also use schedules for time-based materialization:

```python
from dagster import ScheduleDefinition, define_asset_job

candidate_job = define_asset_job(
    name="refresh_candidates",
    selection=["raw_candidates", "normalized_candidates", "candidate_vectors"],
)

# Run every hour
hourly_refresh = ScheduleDefinition(
    job=candidate_job,
    cron_schedule="0 * * * *",
)
```

## Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| Eager auto-materialize | Real-time updates | May trigger too often |
| Lazy auto-materialize | Cost control | Data can become stale |
| Scheduled | Predictable timing | Fixed delay |

## Related Concepts

- [Code Versioning](01-code-versioning.md)
- [Sensors for Event-Driven Pipelines](04-sensors.md)
