"""CV normalization LLM operation.

Extracts structured candidate data from raw CV text using an LLM.

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
PROMPT_VERSION = "1.1.0"  # v1.1.0: Extracted to modular LLM operations structure

# Default model for CV normalization (cost-effective for extraction)
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are a CV parser. Extract and normalize the following CV into this exact JSON structure:

{
  "name": "Full name of the candidate",
  "years_of_experience": <number or null if unclear>,
  "current_role": "Most recent job title",
  "summary": "2-3 sentence professional summary",
  "skills": {
    "languages": ["Programming languages..."],
    "frameworks": ["Frameworks and libraries..."],
    "tools": ["Tools, databases, platforms..."],
    "domains": ["Industry domains and expertise areas..."]
  },
  "experience": [
    {
      "company": "Company name",
      "role": "Job title",
      "duration_months": <number or null>,
      "description": "1-2 sentence summary of responsibilities",
      "technologies": ["Tech used in this role..."]
    }
  ],
  "education": [
    {
      "institution": "University/School name",
      "degree": "Degree type and field",
      "year": <graduation year or null>
    }
  ],
  "notable_achievements": ["Hackathon wins, awards, significant projects..."],
  "location": {
    "city": "City name or null",
    "country": "Country name or null",
    "timezone": "Timezone like 'America/New_York' or null"
  },
  "social_handles": {
    "github": "GitHub username or null",
    "linkedin": "LinkedIn handle or null",
    "twitter": "Twitter/X handle or null"
  },
  "seniority_level": "junior|mid|senior|staff|principal|null"
}

Be factual. If information is missing, use null. Do not make up information.
Infer seniority_level from job titles and years of experience when possible."""


class NormalizeCVResult:
    """Result of CV normalization with usage stats for Dagster metadata."""

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


async def normalize_cv(
    openrouter: "OpenRouterResource",
    raw_cv_text: str,
) -> NormalizeCVResult:
    """Normalize a CV into structured format using LLM.

    Args:
        openrouter: OpenRouterResource instance for API calls
        raw_cv_text: Raw text extracted from a CV/resume

    Returns:
        NormalizeCVResult with data and usage stats for metadata
    """
    model = DEFAULT_MODEL
    response = await openrouter.complete(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this CV:\n\n{raw_cv_text}"},
        ],
        model=model,
        operation="normalize_cv",
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})

    return NormalizeCVResult(data=json.loads(content), usage=usage, model=model)
