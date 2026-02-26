"""Timezone resolution LLM operation.

Resolves (city, country) pairs to IANA timezone identifiers via LLM.
Used by both the inline candidate ingest resolver and the batch backfill job.
"""

import json
import logging
from typing import TYPE_CHECKING, Any
from zoneinfo import available_timezones

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_BATCH_SIZE = 200

SYSTEM_PROMPT = """\
You are a geographic timezone resolver. For each location below, determine the \
IANA timezone identifier (e.g., "America/New_York", "Europe/Berlin", "Asia/Tokyo").

Rules:
- Use the IANA Time Zone Database names (also known as Olson names).
- If a city is provided, use the city-specific timezone.
- If only a country is provided, use the country's most common/capital timezone.
- If a location is ambiguous (e.g., "Springfield" without a state), use the most \
populated match in the given country. Set confidence to "medium".
- If you cannot determine the timezone, set timezone to null and confidence to "low".
- For UTC offset, use the standard offset (not DST-adjusted), e.g. "UTC+01:00".

Return a JSON object with this structure:
{
  "results": [
    {"city": "Berlin", "country": "Germany", "timezone": "Europe/Berlin", "utc_offset": "UTC+01:00", "confidence": "high"},
    ...
  ]
}"""

VALID_TIMEZONES = available_timezones()


def _validate_iana(tz: str | None) -> str | None:
    """Return the timezone if it's a valid IANA name, else None."""
    if tz and tz in VALID_TIMEZONES:
        return tz
    return None


async def resolve_timezones(
    openrouter: "OpenRouterResource",
    locations: list[dict[str, str | None]],
) -> list[dict[str, Any]]:
    """Resolve a batch of (city, country) pairs to IANA timezones.

    Args:
        openrouter: OpenRouterResource for API calls
        locations: list of {"city": str|None, "country": str} dicts

    Returns:
        list of {"city", "country", "timezone", "utc_offset", "confidence"} dicts.
        Invalid IANA timezones are set to None with confidence "low".
    """
    if not locations:
        return []

    results: list[dict[str, Any]] = []

    for batch_start in range(0, len(locations), MAX_BATCH_SIZE):
        batch = locations[batch_start : batch_start + MAX_BATCH_SIZE]
        user_prompt = f"Resolve timezones for these locations:\n{json.dumps(batch)}"

        response = await openrouter.complete(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=DEFAULT_MODEL,
            operation="resolve_timezones",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        batch_results = parsed.get("results", [])

        for entry in batch_results:
            tz = _validate_iana(entry.get("timezone"))
            if tz is None and entry.get("timezone"):
                logger.warning(
                    "Invalid IANA timezone %r for %s, %s",
                    entry.get("timezone"),
                    entry.get("city"),
                    entry.get("country"),
                )
            results.append(
                {
                    "city": entry.get("city"),
                    "country": entry.get("country"),
                    "timezone": tz,
                    "utc_offset": entry.get("utc_offset"),
                    "confidence": "low" if tz is None else entry.get("confidence", "high"),
                }
            )

        usage = response.get("usage", {})
        logger.info(
            "Resolved %d/%d locations (batch %d-%d), tokens: %d",
            len(batch_results),
            len(batch),
            batch_start,
            batch_start + len(batch),
            usage.get("total_tokens", 0),
        )

    return results
