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
PROMPT_VERSION = (
    "2.0.0"  # v2.0.0: Aligned with database schema, added contact info, education, hackathons
)

# Default model for CV normalization (cost-effective for extraction)
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are a CV parser. Extract and normalize the following CV into this exact JSON structure:

{
  "name": "Full name of the candidate",
  "email": "Email address or null",
  "phone": "Phone number or null",
  "years_of_experience": <total years as number or null>,
  "current_role": "Most recent job title",
  "summary": "2-3 sentence professional summary",
  "seniority_level": "JUNIOR|MID|SENIOR|STAFF|PRINCIPAL|null",

  "location": {
    "city": "City name or null",
    "country": "Country name or null",
    "timezone": "Timezone like 'America/New_York' or null"
  },

  "skills": ["All skills mentioned: programming languages, frameworks, tools, databases, platforms, etc."],

  "experience": [
    {
      "company": "Company name",
      "role": "Job title",
      "duration_months": <number or null>,
      "is_current": <true if current job, false otherwise>,
      "description": "Full description of responsibilities and achievements",
      "technologies": ["Tech used in this role..."]
    }
  ],

  "education": {
    "highest_degree": "Highest degree (e.g., 'Bachelor's', 'Master's', 'PhD') or null",
    "field": "Field of study (e.g., 'Computer Science') or null",
    "institution": "Name of university/college or null"
  },

  "projects": [
    {
      "name": "Project name",
      "description": "What the project does",
      "technologies": ["Tech stack used..."],
      "url": "Project URL or null"
    }
  ],

  "hackathons": [
    {
      "name": "Hackathon name",
      "prize": "Prize won (e.g., '1st Place', 'Best DeFi') or null",
      "prize_amount_usd": <prize in USD as number or null>,
      "is_solana": <true if Solana/Solana Foundation hackathon>
    }
  ],

  "achievements": ["Other awards, certifications, notable accomplishments..."],

  "social_handles": {
    "github": "GitHub username only (not full URL) or null",
    "linkedin": "LinkedIn handle only (not full URL) or null",
    "twitter": "Twitter/X handle only (not full URL) or null"
  },

  "verified_communities": ["Any crypto/tech communities they are verified members of..."]
}

IMPORTANT:
- Extract email and phone if present in the CV
- skills is a FLAT LIST of all skills (languages, frameworks, tools, etc.)
- For social handles, extract just the username (e.g., "darshan9solanki" not "https://x.com/darshan9solanki")
- Separate hackathons from general projects - hackathons have prizes/competitions
- seniority_level must be uppercase: JUNIOR, MID, SENIOR, STAFF, or PRINCIPAL
- Be factual. If information is missing, use null. Do not make up information."""


class NormalizeCVResult:
    """Result of CV normalization with usage stats for Dagster metadata."""

    def __init__(
        self, data: dict[str, Any], usage: dict[str, Any], model: str, prompt_version: str
    ):
        self.data = data
        self.usage = usage
        self.model = model
        self.prompt_version = prompt_version

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

    return NormalizeCVResult(
        data=json.loads(content), usage=usage, model=model, prompt_version=PROMPT_VERSION
    )
