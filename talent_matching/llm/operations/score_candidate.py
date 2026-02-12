"""Candidate scoring LLM operation.

Evaluates candidate profiles and scores their fit for roles using an LLM.

Bump PROMPT_VERSION when changing the prompt to trigger asset staleness.
"""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

# Bump this version when the prompt changes
# Format: MAJOR.MINOR.PATCH
# - MAJOR: Breaking changes to output schema
# - MINOR: New fields or significant prompt improvements
# - PATCH: Minor wording tweaks or bug fixes
PROMPT_VERSION = "1.0.0"

# Use a more capable model for reasoning/scoring tasks
DEFAULT_MODEL = "openai/gpt-4o"

SYSTEM_PROMPT_JOB_FIT = """You are an expert technical recruiter evaluating candidate fit for a specific role.

Analyze the candidate profile against the job requirements and provide a detailed scoring.

Return JSON with:
{
  "overall_score": <0.0 to 1.0>,
  "skills_match_score": <0.0 to 1.0>,
  "experience_score": <0.0 to 1.0>,
  "domain_score": <0.0 to 1.0>,
  "seniority_match": true|false,
  "strengths": ["Key strengths for this role..."],
  "gaps": ["Missing skills or experience..."],
  "reasoning": "2-3 sentences explaining the overall score"
}

Scoring guidelines:
- 0.9-1.0: Exceptional fit, exceeds all requirements
- 0.7-0.9: Strong fit, meets most requirements
- 0.5-0.7: Moderate fit, meets core requirements
- 0.3-0.5: Weak fit, significant gaps
- 0.0-0.3: Poor fit, missing critical requirements"""

SYSTEM_PROMPT_GENERAL = """You are an expert technical recruiter evaluating a candidate profile.

Analyze the candidate's overall quality and potential.

Return JSON with:
{
  "overall_score": <0.0 to 1.0>,
  "experience_score": <0.0 to 1.0>,
  "skills_score": <0.0 to 1.0>,
  "domain_score": <0.0 to 1.0>,
  "strengths": ["Key strengths..."],
  "areas_for_growth": ["Areas that could be stronger..."],
  "reasoning": "2-3 sentences explaining the evaluation"
}

Scoring guidelines:
- 0.9-1.0: Exceptional candidate, strong across all dimensions
- 0.7-0.9: Strong candidate, solid experience and skills
- 0.5-0.7: Average candidate, meets basic expectations
- 0.3-0.5: Below average, limited experience or skills
- 0.0-0.3: Weak candidate, significant concerns"""


async def score_candidate(
    openrouter: "OpenRouterResource",
    normalized_profile: dict[str, Any],
    job_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate scores for a candidate profile.

    Args:
        openrouter: OpenRouterResource instance for API calls
        normalized_profile: Normalized candidate profile
        job_requirements: Optional job to score against

    Returns:
        Scoring breakdown with individual metric scores and reasoning
    """
    if job_requirements:
        system_prompt = SYSTEM_PROMPT_JOB_FIT
        user_content = f"""Candidate Profile:
{json.dumps(normalized_profile, indent=2)}

Job Requirements:
{json.dumps(job_requirements, indent=2)}"""
    else:
        system_prompt = SYSTEM_PROMPT_GENERAL
        user_content = f"""Candidate Profile:
{json.dumps(normalized_profile, indent=2)}"""

    response = await openrouter.complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        model=DEFAULT_MODEL,
        operation="score_candidate",
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    content = response["choices"][0]["message"]["content"]
    return json.loads(content)
