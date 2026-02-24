"""Skill normalization LLM operations.

Two operations used by the periodic skill_normalization job:

1. assign_skills_to_bags — given existing bags (canonical + aliases) and unprocessed
   skill names, the LLM assigns each name to an existing canonical or to new_groups.

2. cluster_new_skills — given a list of unmatched skill names (the new_groups from
   step 1), the LLM groups equivalent names into clusters, picking a canonical for
   each. This solves the cold-start problem when no existing bags exist yet.
"""

import json
from itertools import groupby
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

DEFAULT_MODEL = "openai/gpt-4o-mini"

MAX_BATCH_SIZE = 400


def _first_letter(name: str) -> str:
    return name[0].upper() if name else ""


def _chunk_by_letter(names: list[str]) -> list[list[str]]:
    """Sort names alphabetically, group by first letter, then merge adjacent
    letter groups into batches up to MAX_BATCH_SIZE.  Same-letter skills are
    never split across batches."""
    sorted_names = sorted(names, key=_first_letter)
    letter_groups = [list(group) for _, group in groupby(sorted_names, key=_first_letter)]

    batches: list[list[str]] = []
    current: list[str] = []
    for lg in letter_groups:
        if current and len(current) + len(lg) > MAX_BATCH_SIZE:
            batches.append(current)
            current = []
        current.extend(lg)
    if current:
        batches.append(current)
    return batches


def _parse_llm_json(
    content: str,
    *,
    operation: str,
    chunk_idx: int,
    total_chunks: int,
    prompt: str,
    dagster_log: Any = None,
) -> dict[str, Any]:
    """Parse JSON from LLM response, logging diagnostics on failure."""
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        msg = f"{operation} LLM returned {type(parsed).__name__}, expected dict"
        if dagster_log is not None:
            dagster_log.error(msg)
        raise ValueError(msg)
    return parsed


# ---------------------------------------------------------------------------
# 1. Assign unprocessed names to existing bags
# ---------------------------------------------------------------------------


def _build_assign_prompt(existing_bags: list[dict[str, Any]], unprocessed_names: list[str]) -> str:
    bags_text = json.dumps(existing_bags)
    names_text = json.dumps(unprocessed_names)
    return f"""We have existing **alias bags** (each bag has one canonical skill name and a list of equivalent aliases). Below are **new skill names** that are not yet in any bag. For each new name, assign it to the canonical of an existing bag if it means the same thing (e.g. "Typescript" → TypeScript, "ReactJS" → React). If no existing bag fits, put the name in new_groups. Use only canonicals from the existing bags; do not invent names.

Existing bags:
{bags_text}

Unprocessed skill names (assign each to a bag or to new_groups):
{names_text}

Return valid JSON only with exactly two keys:
- "assignments": array of {{ "skill_name": "<string>", "assign_to_canonical": "<existing canonical name>" }}
- "new_groups": array of skill names that did not match any existing bag

Every unprocessed name must appear in exactly one of assignments (with an existing canonical) or new_groups."""


async def assign_skills_to_bags(
    openrouter: "OpenRouterResource",
    existing_bags: list[dict[str, Any]],
    unprocessed_names: list[str],
    model: str | None = None,
    dagster_log: Any = None,
) -> dict[str, Any]:
    """Assign unprocessed skill names to existing bags or new_groups via LLM.

    Args:
        openrouter: OpenRouter resource for API calls.
        existing_bags: List of { "canonical": str, "aliases": list[str] }.
        unprocessed_names: List of skill names not yet in any bag.
        model: Model to use; defaults to gpt-4o-mini.
        dagster_log: Optional Dagster logger for error diagnostics.

    Returns:
        { "assignments": [ { "skill_name": str, "assign_to_canonical": str } ],
          "new_groups": [ str ] }
    """
    if not unprocessed_names:
        return {"assignments": [], "new_groups": []}

    all_assignments: list[dict[str, Any]] = []
    all_new_groups: list[str] = []

    chunks = _chunk_by_letter(unprocessed_names)
    for chunk_idx, chunk in enumerate(chunks):
        prompt = _build_assign_prompt(existing_bags, chunk)
        response = await openrouter.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model or DEFAULT_MODEL,
            operation="skill_normalization",
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=16_384,
        )
        content = response["choices"][0]["message"]["content"]
        data = _parse_llm_json(
            content,
            operation="skill_normalization",
            chunk_idx=chunk_idx,
            total_chunks=len(chunks),
            prompt=prompt,
            dagster_log=dagster_log,
        )
        all_assignments.extend(data.get("assignments") or [])
        all_new_groups.extend(data.get("new_groups") or [])

    return {"assignments": all_assignments, "new_groups": all_new_groups}


# ---------------------------------------------------------------------------
# 2. Cluster unmatched names into new bags
# ---------------------------------------------------------------------------


def _build_cluster_prompt(skill_names: list[str]) -> str:
    names_text = json.dumps(skill_names)
    return f"""Group the following skill names into clusters of equivalent or synonymous skills. For each cluster, pick the most standard/common form as the "canonical" and list the rest as "aliases". If a skill name has no equivalents in this list, include it as a cluster with an empty aliases array.

Skill names:
{names_text}

Return valid JSON only with exactly one key:
- "clusters": array of {{ "canonical": "<best name>", "aliases": ["<other name>", ...] }}

Rules:
- Every skill name must appear exactly once across all clusters (either as canonical or as alias).
- Do not invent names; use only names from the list above.
- Only group names that genuinely mean the same skill (e.g. "Node" and "Node.js" are the same; "Node" and "Angular" are not)."""


async def cluster_new_skills(
    openrouter: "OpenRouterResource",
    skill_names: list[str],
    model: str | None = None,
    dagster_log: Any = None,
) -> list[dict[str, Any]]:
    """Cluster unmatched skill names into groups of equivalents via LLM.

    Solves the cold-start problem: when no existing bags exist, this creates
    initial bags by grouping equivalent names together.

    Args:
        openrouter: OpenRouter resource for API calls.
        skill_names: Unmatched skill names (new_groups from assign_skills_to_bags).
        model: Model to use; defaults to gpt-4o-mini.
        dagster_log: Optional Dagster logger for error diagnostics.

    Returns:
        List of { "canonical": str, "aliases": [str, ...] }.
        Clusters with empty aliases are singletons (no equivalents found).
    """
    if not skill_names:
        return []

    all_clusters: list[dict[str, Any]] = []

    chunks = _chunk_by_letter(skill_names)
    for chunk_idx, chunk in enumerate(chunks):
        prompt = _build_cluster_prompt(chunk)
        response = await openrouter.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model or DEFAULT_MODEL,
            operation="skill_clustering",
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=16_384,
        )
        content = response["choices"][0]["message"]["content"]
        data = _parse_llm_json(
            content,
            operation="skill_clustering",
            chunk_idx=chunk_idx,
            total_chunks=len(chunks),
            prompt=prompt,
            dagster_log=dagster_log,
        )
        all_clusters.extend(data.get("clusters") or [])

    return all_clusters
