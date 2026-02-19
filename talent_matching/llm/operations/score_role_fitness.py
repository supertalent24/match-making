"""Candidate–role fitness: LLM scores how well a candidate fits a desired job category."""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

PROMPT_VERSION = "1.0.0"
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are an expert technical recruiter. Score how well a candidate fits a specific role category (e.g. "Frontend Developer", "Smart Contract Engineer").

Consider:
- Skill overlap with typical role requirements
- Skill depth (e.g. 1-5 or 1-10 scale)
- Experience relevance (past roles, projects)
- Years of experience vs typical seniority for the role

Return JSON only:
{
  "fitness_score": <integer 1 to 100>,
  "reasoning": "<2-4 sentences explaining the score>"
}

Guidelines:
- 80-100: Strong fit; skills and experience align well with the role.
- 60-79: Good fit; minor gaps.
- 40-59: Moderate fit; some relevant experience/skills but notable gaps.
- 20-39: Weak fit; limited alignment.
- 1-19: Poor fit; role does not match profile."""


async def score_role_fitness(
    openrouter: "OpenRouterResource",
    candidate_profile: dict[str, Any],
    role_name: str,
) -> dict[str, Any]:
    """Score fitness (1-100) and reasoning for a candidate in a role category.

    Args:
        openrouter: OpenRouter resource.
        candidate_profile: Normalized candidate profile (skills, experience, seniority, etc.).
        role_name: Desired job category / role name (e.g. "Frontend Developer").

    Returns:
        {"fitness_score": int 1-100, "reasoning": str}
    """
    user_content = f"""Candidate profile (excerpt):
{json.dumps(candidate_profile, indent=2)}

Role category to score fit for: "{role_name}"

Return JSON with fitness_score (1-100) and reasoning."""

    response = await openrouter.complete(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        model=DEFAULT_MODEL,
        operation="score_role_fitness",
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)
    score = data.get("fitness_score", 50)
    if not isinstance(score, int):
        score = int(round(float(score)))
    score = max(1, min(100, score))
    return {"fitness_score": score, "reasoning": data.get("reasoning", "") or ""}
