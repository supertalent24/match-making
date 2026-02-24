"""Skill normalization: assign unprocessed skill names to existing alias bags via LLM.

Used by the periodic skill_normalization job. Given existing bags (canonical + aliases)
and a list of unprocessed skill names, the LLM assigns each name to an existing
canonical or to new_groups.
"""

import json
from itertools import groupby
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

DEFAULT_MODEL = "openai/gpt-4o-mini"


def _build_prompt(existing_bags: list[dict[str, Any]], unprocessed_names: list[str]) -> str:
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
        existing_bags: List of { "canonical": str, "aliases": list[str] } (and optionally "skill_id").
        unprocessed_names: List of skill names not yet in any bag.
        model: Model to use; defaults to gpt-4o-mini.
        dagster_log: Optional Dagster log (e.g. context.log). If set, on JSON parse failure
            we call dagster_log.error(...) with the raw LLM input and output for the run logs.

    Returns:
        { "assignments": [ { "skill_name": str, "assign_to_canonical": str } ], "new_groups": [ str ] }
    """
    if not unprocessed_names:
        return {"assignments": [], "new_groups": []}

    all_assignments: list[dict[str, Any]] = []
    all_new_groups: list[str] = []

    sorted_names = sorted(unprocessed_names, key=lambda n: n[0].upper() if n else "")
    chunks = [
        list(group) for _, group in groupby(sorted_names, key=lambda n: n[0].upper() if n else "")
    ]
    for chunk_idx, chunk in enumerate(chunks):
        prompt = _build_prompt(existing_bags, chunk)
        response = await openrouter.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model or DEFAULT_MODEL,
            operation="skill_normalization",
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=8192,
        )
        content = response["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            if dagster_log is not None:
                dagster_log.error(
                    f"skill_normalization LLM returned invalid JSON (chunk {chunk_idx + 1} of {len(chunks)}): {e}"
                )
                dagster_log.error(f"LLM input (prompt) length={len(prompt)} chars:\n{prompt}")
                dagster_log.error(
                    f"LLM output (raw content) length={len(content)} chars:\n{content}"
                )
            raise
        all_assignments.extend(data.get("assignments") or [])
        all_new_groups.extend(data.get("new_groups") or [])

    return {"assignments": all_assignments, "new_groups": all_new_groups}
