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
PROMPT_VERSION = "2.4.0"  # v2.4.0: Per-skill expected_capability for matchmaking

# Default model for job normalization (cost-effective for extraction)
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are a job description parser. Extract and normalize this job posting into structured JSON. The output is used for semantic matching with candidate profiles: write job narratives and structured fields so they align with how candidates describe themselves (same vocabulary, same concepts).

Output a single JSON object with this structure (use null when not mentioned):

{
  "title": "Job title in English (translate if the posting is in another language)",
  "company_name": "Company name if mentioned",
  "seniority_level": "JUNIOR|MID|SENIOR|STAFF|LEAD|PRINCIPAL|EXECUTIVE",
  "employment_type": ["full-time", "part-time"] (array: list every type offered; infer from 'Vollzeit/Teilzeit', 'full or part time'; use ["full-time", "part-time"] when both offered)",
  "requirements": {
    "must_have_skills": [{"name": "Canonical skill name", "expected_capability": "1-2 sentences: what the ideal candidate must be able to do with this skill in this role"}],
    "nice_to_have_skills": [{"name": "Canonical skill name", "expected_capability": "1-2 sentences: what the ideal candidate should be able to do with this skill"}],
    "years_of_experience_min": <number or null>,
    "years_of_experience_max": <number or null>,
    "education_required": "Degree requirement or null",
    "domain_experience": ["DeFi", "NFT", "Trading", etc.]
  },
  "soft_attribute_requirements": {
    "leadership": <min 1-5 or null>,
    "autonomy": <min 1-5 or null>,
    "technical_depth": <min 1-5 or null>,
    "communication": <min 1-5 or null>,
    "growth_trajectory": <min 1-5 or null>
  },
  "role_description": "2-3 sentence summary of what the role does",
  "team_context": "Team size, reporting structure if mentioned",
  "tech_stack": ["Canonical names: React, TypeScript, etc."],
  "compensation": {
    "salary_min": <number or null, always yearly>,
    "salary_max": <number or null, always yearly>,
    "currency": "USD",
    "equity": true|false|null
  },
  "contact": {
    "hiring_manager_name": "Name if given, else null",
    "hiring_manager_email": "Application or contact email if given (e.g. 'Apply to info@...')",
    "application_url": "URL for applications if given, else null"
  },
  "location": {
    "type": "remote|hybrid|onsite",
    "locations": ["Locations if onsite/hybrid..."]
  },
  "responsibilities": ["Bullet or sentence per responsibility"],
  "nice_to_haves": ["Optional bullets"],
  "benefits": ["Benefits if mentioned"],
  "narratives": {
    "experience": "Pure prose: career path and progression the ideal candidate would have (e.g. 'Progressed from X to Y', 'typical background', 'years and trajectory'). Same style as candidate CV narratives. 3-5 sentences, no bullet points.",
    "domain": "Pure prose: industries, protocols, ecosystems, problem spaces (e.g. DeFi, trading, infra). Use same vocabulary as candidate domain narratives. 3-5 sentences.",
    "personality": "Pure prose: work style, values, collaboration, culture. What kind of person thrives (e.g. async-first, ownership, builder mentality). Align with candidate personality narratives. 3-5 sentences.",
    "impact": "Pure prose: scope of ownership, scale, outcomes expected (team size, systems scale, measurable results). Same concepts as candidate impact narratives. 3-5 sentences.",
    "technical": "Pure prose: technical depth, stack, systems context (architecture, infra, deep expertise). Align with candidate technical narratives. 3-5 sentences.",
    "role": "Pure prose: day-to-day role and responsibilities in flowing prose. Single position-like description. No bullet points."
  }
}

Be factual. If information is not mentioned, use null.

**Matchmaking:** Narratives and structured fields are embedded for semantic matching with candidate profiles. Describe the ideal candidate in the same terms candidates use: career journey, domain expertise, work style, impact level, technical depth. Same vocabulary improves match quality.

**Seniority:** Use the same levels as candidate profiles (uppercase): JUNIOR, MID, SENIOR, STAFF (IC track), LEAD (management track), PRINCIPAL, EXECUTIVE.

**Skills:** Use canonical skill names so they match candidate skill lists: e.g. "React" not "ReactJS", "TypeScript" not "TS", "PostgreSQL" not "Postgres". For each required skill, output an object with "name" and "expected_capability". The expected_capability is 1-2 sentences inferring from the job description what the ideal candidate must be capable of with that skill (e.g. "Design and implement REST APIs; integrate with internal services"). Use the same vocabulary as candidate skill evidence for better semantic matching. Apply to must_have_skills and nice_to_have_skills. tech_stack remains a simple array of canonical names.

**Soft attribute requirements:** Infer minimum 1-5 scores from job description signals (e.g. "lead small team" -> leadership 3; "self-directed" -> autonomy 4). Use the same five dimensions as candidate profiles: leadership, autonomy, technical_depth, communication, growth_trajectory. Use null when not implied.

**Compensation:** Always normalize to yearly amounts for salary_min and salary_max. If the posting states hourly, daily, or monthly rates, convert to yearly (e.g. hourly × 2080 for full-time, × 1040 for half-time; monthly × 12). Keep the stated currency. Use null only when no numeric compensation is given.

**Job title:** Use English. If the posting is in another language (e.g. German "Frontend-Entwickler"), output the English equivalent (e.g. "Frontend Developer")."""


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
