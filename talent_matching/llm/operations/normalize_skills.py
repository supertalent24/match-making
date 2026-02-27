"""Skill normalization LLM operations.

Two operations used by the periodic skill_normalization job:

1. assign_skills_to_bags — given existing bags (canonical + aliases) and unprocessed
   skill names, the LLM assigns each name to an existing canonical or to new_groups.

2. cluster_new_skills — given a list of unmatched skill names (the new_groups from
   step 1), the LLM groups equivalent names into clusters, picking a canonical for
   each. This solves the cold-start problem when no existing bags exist yet.
"""

import json
import logging
from itertools import groupby
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-4o"
MAX_OUTPUT_TOKENS = 16_384

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


async def _llm_call_with_bisect(
    openrouter: "OpenRouterResource",
    build_prompt_fn: Any,
    items: list[str],
    *,
    prompt_args: tuple = (),
    operation: str,
    result_keys: list[str],
    model: str,
    dagster_log: Any = None,
) -> dict[str, list]:
    """Make an LLM call; if the output is truncated (finish_reason='length'),
    bisect the item list and retry each half recursively.

    Args:
        build_prompt_fn: Callable that builds the prompt. Called as
            build_prompt_fn(*prompt_args, items_subset).
        items: The list of names to process in this call.
        prompt_args: Extra leading args passed to build_prompt_fn before items.
        operation: Operation name for cost tracking.
        result_keys: Keys to extract from the parsed JSON and aggregate.
        model: Model identifier.
        dagster_log: Optional Dagster logger.

    Returns:
        Dict mapping each result_key to its aggregated list.
    """
    prompt = build_prompt_fn(*prompt_args, items)
    response = await openrouter.complete(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        operation=operation,
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=MAX_OUTPUT_TOKENS,
    )

    finish_reason = response["choices"][0].get("finish_reason", "stop")
    content = response["choices"][0]["message"]["content"]

    if finish_reason == "length":
        if len(items) <= 1:
            raise RuntimeError(
                f"{operation}: output truncated even with a single item; "
                f"cannot bisect further. Item: {items}"
            )
        mid = len(items) // 2
        log_fn = dagster_log.warning if dagster_log else logger.warning
        log_fn(
            f"{operation}: output truncated (finish_reason=length) for "
            f"{len(items)} items — bisecting into {mid} + {len(items) - mid}"
        )
        left = await _llm_call_with_bisect(
            openrouter,
            build_prompt_fn,
            items[:mid],
            prompt_args=prompt_args,
            operation=operation,
            result_keys=result_keys,
            model=model,
            dagster_log=dagster_log,
        )
        right = await _llm_call_with_bisect(
            openrouter,
            build_prompt_fn,
            items[mid:],
            prompt_args=prompt_args,
            operation=operation,
            result_keys=result_keys,
            model=model,
            dagster_log=dagster_log,
        )
        merged: dict[str, list] = {}
        for key in result_keys:
            merged[key] = left.get(key, []) + right.get(key, [])
        return merged

    data = json.loads(content)
    if not isinstance(data, dict):
        msg = f"{operation} LLM returned {type(data).__name__}, expected dict"
        if dagster_log is not None:
            dagster_log.error(msg)
        raise ValueError(msg)
    return {key: data.get(key) or [] for key in result_keys}


# ---------------------------------------------------------------------------
# 1. Assign unprocessed names to existing bags
# ---------------------------------------------------------------------------


def _build_assign_prompt(existing_bags: list[dict[str, Any]], unprocessed_names: list[str]) -> str:
    bags_text = json.dumps(existing_bags)
    names_text = json.dumps(unprocessed_names)
    return f"""We have existing **alias bags** (each bag has one canonical skill name and a list of equivalent aliases). Below are **new skill names** that are not yet in any bag. For each new name, assign it to the canonical of an existing bag if it means the same thing (e.g. "Typescript" → TypeScript, "ReactJS" → React). If no existing bag fits, put the name in new_groups. Use only canonicals from the existing bags; do not invent names.

**CRITICAL — "same skill" means the EXACT SAME technology, not merely related or similarly named:**
- Only aliases: alternate spellings, capitalizations, abbreviations, or widely accepted synonyms for the identical tool/language/framework.
- CORRECT merges: "Typescript" → TypeScript, "ReactJS" → React, "Golang" → Go, "Node" → Node.js, "Postgres" → PostgreSQL, "K8s" → Kubernetes, "JS" → JavaScript.
- WRONG merges (these are DISTINCT skills — NEVER group together):
  • Java ≠ JavaScript (different languages, different runtimes, different ecosystems)
  • C ≠ C++ ≠ C# (three separate languages)
  • React ≠ React Native (web framework vs mobile framework)
  • AWS ≠ GCP ≠ Azure (competing cloud platforms)
  • REST ≠ GraphQL ≠ gRPC (different API paradigms)
  • SQL ≠ PostgreSQL ≠ MySQL ≠ SQLite (SQL is a language; the others are specific databases)
  • Docker ≠ Kubernetes (containerization vs orchestration)
  • Terraform ≠ Ansible ≠ Pulumi (different IaC tools)
  • Redis ≠ Memcached (different caching systems)
  • Solidity ≠ Rust ≠ Move (different smart-contract / systems languages)
  • Next.js ≠ Nuxt.js (React-based vs Vue-based)
  • Express ≠ Fastify ≠ NestJS (different Node.js frameworks)
  • Sass ≠ CSS ≠ Tailwind CSS (different styling approaches)

**NEVER merge a specific tool/framework into a broad category.** A canonical like "Frontend", "Backend Development", "DevOps", "AI", "Blockchain", "Programming", "Design", "Testing", "Operations", "Data Analysis", "Cloud Computing", or "API Design" is NOT a valid alias target for concrete technologies. Examples of WRONG category merges:
  • React → "Frontend" (React is a specific framework, not a synonym for Frontend)
  • Django → "Backend Development" (Django is a specific framework)
  • Docker → "DevOps" (Docker is a specific tool)
  • TensorFlow → "AI" (TensorFlow is a specific library)
  • Solidity → "Blockchain" (Solidity is a specific language)
  • GraphQL → "API Design" (GraphQL is a specific technology)
  • Jest → "Testing" (Jest is a specific tool)
  • Figma → "Design" (Figma is a specific product)
  • Rust → "Programming" (Rust is a specific language)
  • Pandas → "Data Analysis" (Pandas is a specific library)

When in doubt, do NOT merge — put the name in new_groups instead. A false non-merge is harmless; a false merge corrupts matching data.

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

    If the LLM output is truncated (hits max_tokens), the chunk is automatically
    bisected and each half retried until the output fits.

    Args:
        openrouter: OpenRouter resource for API calls.
        existing_bags: List of { "canonical": str, "aliases": list[str] }.
        unprocessed_names: List of skill names not yet in any bag.
        model: Model to use; defaults to gpt-4o.
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
    for _chunk_idx, chunk in enumerate(chunks):
        result = await _llm_call_with_bisect(
            openrouter,
            _build_assign_prompt,
            chunk,
            prompt_args=(existing_bags,),
            operation="skill_normalization",
            result_keys=["assignments", "new_groups"],
            model=model or DEFAULT_MODEL,
            dagster_log=dagster_log,
        )
        all_assignments.extend(result["assignments"])
        all_new_groups.extend(result["new_groups"])

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
- "Equivalent" means the EXACT SAME technology under a different spelling, abbreviation, or common nickname. Two skills are equivalent ONLY if a developer listing one on their CV would always mean the other.
- CORRECT clusters (genuinely the same thing):
  • "Node", "Node.js", "NodeJS" → canonical "Node.js"
  • "Typescript", "TS" → canonical "TypeScript"
  • "Postgres", "PostgreSQL" → canonical "PostgreSQL"
  • "K8s", "Kubernetes" → canonical "Kubernetes"
  • "Golang", "Go lang" → canonical "Go"
- WRONG clusters (these are DISTINCT skills — keep them as separate singletons):
  • Java ≠ JavaScript (completely different languages)
  • C ≠ C++ ≠ C# (three separate languages)
  • React ≠ React Native (web vs mobile)
  • SQL ≠ PostgreSQL ≠ MySQL (language vs specific databases)
  • Docker ≠ Kubernetes (containerization vs orchestration)
  • REST ≠ GraphQL (different API paradigms)
  • Next.js ≠ Nuxt.js (React-based vs Vue-based)
  • Sass ≠ CSS ≠ Tailwind CSS (different styling approaches)
  • Terraform ≠ Pulumi ≠ Ansible (different IaC tools)
  • Solidity ≠ Rust ≠ Move (different languages)

**NEVER create category clusters.** Each cluster must represent ONE specific technology, not a category. A canonical name like "Frontend", "Backend", "DevOps", "AI", "Blockchain", "Programming", "Design", "Testing", "Operations", or "Data Analysis" is NOT a valid canonical for grouping specific tools. Examples of WRONG clusters:
  • {{"canonical": "Frontend", "aliases": ["React", "Angular", "Vue"]}} — these are three different frameworks
  • {{"canonical": "DevOps", "aliases": ["Docker", "Kubernetes", "Ansible"]}} — these are three different tools
  • {{"canonical": "AI", "aliases": ["PyTorch", "TensorFlow", "Machine Learning"]}} — these are distinct technologies
  • {{"canonical": "Programming", "aliases": ["Rust", "Dart", "Elixir"]}} — these are different languages

When in doubt, keep skills as separate singletons. A false separation is harmless; a false merge corrupts matching data permanently."""


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
        model: Model to use; defaults to gpt-4o.
        dagster_log: Optional Dagster logger for error diagnostics.

    Returns:
        List of { "canonical": str, "aliases": [str, ...] }.
        Clusters with empty aliases are singletons (no equivalents found).
    """
    if not skill_names:
        return []

    all_clusters: list[dict[str, Any]] = []

    chunks = _chunk_by_letter(skill_names)
    for _chunk_idx, chunk in enumerate(chunks):
        result = await _llm_call_with_bisect(
            openrouter,
            _build_cluster_prompt,
            chunk,
            operation="skill_clustering",
            result_keys=["clusters"],
            model=model or DEFAULT_MODEL,
            dagster_log=dagster_log,
        )
        all_clusters.extend(result["clusters"])

    return all_clusters
