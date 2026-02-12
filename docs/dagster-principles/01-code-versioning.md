# Principle: Code Versioning & Staleness Detection

## Problem

When running a data pipeline, you want to avoid re-processing data when nothing has changed. Re-running unchanged assets wastes compute resources and LLM API credits.

## Solution

Dagster tracks **staleness** automatically based on:
1. Whether the asset's code changed
2. Whether upstream assets were re-materialized
3. Whether configuration changed

### Visual Indicator in UI

| Status | Meaning |
|--------|---------|
| Green checkmark | Asset is up-to-date |
| Yellow warning | Asset is stale (needs re-running) |
| Gray | Asset was never materialized |

## Implementation

### Automatic (Default Behavior)

Dagster automatically detects code changes by hashing the asset function. When you modify the code and save, the asset becomes stale.

### Explicit Code Versions

For more control, add a `code_version` to your assets:

```python
@asset(
    code_version="1.0.0",  # Bump this when logic changes
)
def normalized_candidates(raw_candidates):
    # Processing logic
    ...
```

**Important**: Always use literal string versions (e.g., `"1.0.0"`) rather than variable references. This enables the pre-commit hook to verify versions are updated.

**When to bump the version:**
- Changed the LLM prompt template
- Modified the normalization logic
- Updated the scoring algorithm

**When NOT to bump:**
- Refactored code without changing output
- Added logging or comments
- Fixed a bug that didn't affect output

## Pre-commit Hook

A pre-commit hook enforces that `code_version` is updated when asset code changes:

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run manually
python scripts/check_dagster_code_versions.py --verbose
```

The hook will fail if you:
1. Modify an asset's function body
2. Without bumping the `code_version` string

This prevents accidentally breaking staleness detection.

## Usage

Instead of clicking **"Materialize all"**, use **"Materialize stale"** in the UI to only run assets that actually need updating.

## Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| Automatic detection | Zero config, always accurate | May over-trigger on refactors |
| Explicit versions | Full control, pre-commit enforced | Manual maintenance |

## Related Concepts

- [Auto-Materialization Policies](02-auto-materialize-policies.md)
- [Deterministic Staleness](03-freshness-policies.md)
