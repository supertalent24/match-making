"""Job description normalization LLM operation.

Extracts structured job requirements from raw job descriptions using an LLM.

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

# Default model for job normalization (cost-effective for extraction)
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are a job description parser. Extract and normalize this job posting into structured JSON:

{
  "title": "Job title",
  "seniority_level": "junior|mid|senior|lead|principal",
  "employment_type": "full-time|part-time|contract",
  "requirements": {
    "must_have_skills": ["Hard requirements..."],
    "nice_to_have_skills": ["Preferred but not required..."],
    "years_of_experience_min": <number or null>,
    "years_of_experience_max": <number or null>,
    "education_required": "Degree requirement or null",
    "domain_experience": ["DeFi", "NFT", "Trading", etc.]
  },
  "role_description": "2-3 sentence summary of what the role does",
  "team_context": "Team size, reporting structure if mentioned",
  "tech_stack": ["Specific technologies mentioned..."],
  "compensation": {
    "salary_min": <number or null>,
    "salary_max": <number or null>,
    "currency": "USD",
    "equity": true|false|null
  },
  "location": {
    "type": "remote|hybrid|onsite",
    "locations": ["Locations if onsite/hybrid..."]
  }
}

Be factual. If information is not mentioned, use null."""


class NormalizeJobResult:
    """Result of job normalization with usage stats for Dagster metadata."""

    def __init__(self, data: dict[str, Any], usage: dict[str, Any], model: str):
        self.data = data
        self.usage = usage
        self.model = model

    @property
    def input_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def output_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("cost", 0))


async def normalize_job(
    openrouter: "OpenRouterResource",
    raw_job_text: str,
) -> NormalizeJobResult:
    """Normalize a job description into structured format using LLM.

    Args:
        openrouter: OpenRouterResource instance for API calls
        raw_job_text: Raw job description text

    Returns:
        NormalizeJobResult with data, usage stats, and model for metadata
    """
    model = DEFAULT_MODEL
    response = await openrouter.complete(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this job description:\n\n{raw_job_text}"},
        ],
        model=model,
        operation="normalize_job",
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})

    return NormalizeJobResult(data=json.loads(content), usage=usage, model=model)
