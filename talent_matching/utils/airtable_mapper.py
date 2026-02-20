"""Airtable field mapping utilities.

This module provides functions for mapping Airtable field formats to our
internal data model. These are used by the AirtableResource but can also
be used independently for testing and data transformation.
"""

import re
from datetime import datetime
from typing import Any

# Prefix for normalized candidate columns when writing back to Airtable
NORMALIZED_COLUMN_PREFIX = "(N) "

# Syncable NormalizedCandidate fields (exclude id, airtable_record_id, raw_candidate_id, verified_by, normalized_json)
NORMALIZED_CANDIDATE_SYNCABLE_FIELDS = [
    "full_name",
    "email",
    "phone",
    "location_city",
    "location_country",
    "location_region",
    "timezone",
    "professional_summary",
    "current_role",
    "seniority_level",
    "years_of_experience",
    "desired_job_categories",
    "skills_summary",
    "companies_summary",
    "notable_achievements",
    "verified_communities",
    "compensation_min",
    "compensation_max",
    "compensation_currency",
    "job_count",
    "job_switches_count",
    "average_tenure_months",
    "longest_tenure_months",
    "education_highest_degree",
    "education_field",
    "education_institution",
    "hackathon_wins_count",
    "hackathon_total_prize_usd",
    "solana_hackathon_wins",
    "x_handle",
    "linkedin_handle",
    "github_handle",
    "social_followers_total",
    "verification_status",
    "verification_notes",
    "verified_at",
    "prompt_version",
    "model_version",
    "confidence_score",
    "normalized_at",
]


def _snake_to_title(name: str) -> str:
    """Convert snake_case to Title Case (e.g. full_name -> Full Name)."""
    return name.replace("_", " ").title()


def _normalized_column_name(snake_name: str) -> str:
    """Return Airtable column name for a normalized field: (N) Title Case."""
    return NORMALIZED_COLUMN_PREFIX + _snake_to_title(snake_name)


# Mapping: NormalizedCandidate attribute name -> Airtable column name (N) prefix
AIRTABLE_CANDIDATES_WRITEBACK_FIELDS: dict[str, str] = {
    name: _normalized_column_name(name) for name in NORMALIZED_CANDIDATE_SYNCABLE_FIELDS
}


def _value_for_airtable(value: Any) -> Any:
    """Coerce a NormalizedCandidate field value for Airtable API (strings, numbers, list, enum, datetime).

    Lists are sent as newline-separated strings so they can be stored in Long text columns.
    Airtable multiple-select columns require existing options and token permission to create
    new ones; using Long text avoids that and supports arbitrary values.
    """
    if value is None:
        return None
    if hasattr(value, "value"):  # Enum
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        if not value:
            return None
        # Store as single string for Long text columns (avoids multiple-select option limits)
        return "\n".join(str(v) for v in value)
    return value


def normalized_candidate_to_airtable_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    """Build Airtable PATCH fields dict from a NormalizedCandidate row (dict).

    Uses AIRTABLE_CANDIDATES_WRITEBACK_FIELDS. Skips None values. Coerces enums to .value,
    datetimes to ISO 8601 strings, arrays to list of strings.
    """
    fields: dict[str, Any] = {}
    for our_key, airtable_col in AIRTABLE_CANDIDATES_WRITEBACK_FIELDS.items():
        raw = candidate.get(our_key)
        if raw is None:
            continue
        coerced = _value_for_airtable(raw)
        if coerced is None:
            continue
        fields[airtable_col] = coerced
    return fields


# Column name mapping from Airtable to RawCandidate model fields
AIRTABLE_COLUMN_MAPPING: dict[str, str] = {
    "Full Name": "full_name",
    "Location": "location_raw",
    "Desired Job Category": "desired_job_categories_raw",
    "Skills": "skills_raw",
    "CV": "cv_url",
    "Professional summary": "professional_summary",
    "Proof of Work": "proof_of_work",
    "Salary Range": "salary_range_raw",
    "X Profile Link": "x_profile_url",
    "LinkedIn Profile": "linkedin_url",
    "Earn Profile": "earn_profile_url",
    "Git Hub Profile": "github_url",
    "Work Experience": "work_experience_raw",
}


def extract_cv_url(cv_field: Any) -> str | None:
    """Extract URL from CV field in various formats.

    Supports:
    1. Airtable API format: List of attachment objects with 'url' key
    2. CSV export format: "filename.pdf (https://...)"
    3. Plain URL string

    Args:
        cv_field: The CV field value from Airtable

    Returns:
        The extracted URL string, or None if no URL found.

    Examples:
        >>> extract_cv_url([{"url": "https://example.com/cv.pdf"}])
        'https://example.com/cv.pdf'

        >>> extract_cv_url("resume.pdf (https://example.com/cv.pdf)")
        'https://example.com/cv.pdf'

        >>> extract_cv_url("https://example.com/cv.pdf")
        'https://example.com/cv.pdf'
    """
    if cv_field is None:
        return None

    # Airtable API format: list of attachment objects
    if isinstance(cv_field, list) and cv_field:
        first_attachment = cv_field[0]
        if isinstance(first_attachment, dict):
            return first_attachment.get("url")

    # String formats
    if isinstance(cv_field, str):
        cv_field = cv_field.strip()

        # CSV export format: "filename.pdf (https://...)"
        match = re.search(r"\((https?://[^)]+)\)", cv_field)
        if match:
            return match.group(1)

        # Plain URL
        if cv_field.startswith(("http://", "https://")):
            return cv_field

    return None


def parse_comma_separated(field_value: str | None) -> list[str]:
    """Parse a comma-separated string into a list of trimmed values.

    Args:
        field_value: Comma-separated string (e.g., "Python,JavaScript,Rust")

    Returns:
        List of trimmed non-empty strings.

    Examples:
        >>> parse_comma_separated("Python, JavaScript, Rust")
        ['Python', 'JavaScript', 'Rust']

        >>> parse_comma_separated(None)
        []

        >>> parse_comma_separated("  One  ,  Two  ,  ")
        ['One', 'Two']
    """
    if not field_value:
        return []

    items = field_value.split(",")
    return [item.strip() for item in items if item.strip()]


# Column name mapping from Airtable (jobs table, e.g. Customers STT) to RawJob model fields
AIRTABLE_JOBS_COLUMN_MAPPING: dict[str, str] = {
    "🔗  Job Description Link": "job_description_link",
    "Hiring Job Title": "job_title_raw",
    "Company": "company_name",
    "Twitter Handle": "x_url",
    "Website Link": "company_website_url",
    "Full Name": "hiring_contact_name",
    "Mail": "hiring_contact_email",
    # Optional: if table has a text field for pasted job description
    "Job Description Text": "job_description_text",
    "Links & details": "job_description_text",
}


def _serialize_airtable_value(value: Any) -> str | None:
    """Serialize Airtable field value to string for raw job storage (e.g. multi-select -> JSON array string)."""
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(str(v) for v in value) if value else None
    return str(value) if value else None


def map_airtable_row_to_raw_job(
    record: dict[str, Any],
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map an Airtable record (jobs table) to RawJob-like field names.

    Args:
        record: Airtable record with 'id', 'fields', 'createdTime'
        column_mapping: Optional; defaults to AIRTABLE_JOBS_COLUMN_MAPPING.

    Returns:
        Dictionary with mapped field names and airtable_record_id, source, source_id.
    """
    if column_mapping is None:
        column_mapping = AIRTABLE_JOBS_COLUMN_MAPPING

    fields = record.get("fields", {})
    mapped: dict[str, Any] = {
        "airtable_record_id": record.get("id"),
        "source": "airtable",
        "source_id": record.get("id"),
    }
    for airtable_col, model_field in column_mapping.items():
        value = fields.get(airtable_col)
        if value is None:
            continue
        if model_field == "job_description_link":
            mapped[model_field] = (
                value
                if isinstance(value, str)
                else (
                    value[0].get("url")
                    if isinstance(value, list) and value and isinstance(value[0], dict)
                    else None
                )
            )
        elif isinstance(value, list):
            mapped[model_field] = ",".join(str(v) for v in value) if value else None
        else:
            mapped[model_field] = str(value) if value else None
    return mapped


def map_airtable_row_to_raw_candidate(
    record: dict[str, Any],
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map an Airtable record to RawCandidate model fields.

    This function handles the transformation from Airtable's field names
    (e.g., "Full Name", "Professional summary") to our database column names
    (e.g., "full_name", "professional_summary").

    Args:
        record: Airtable record with 'id', 'fields', and 'createdTime' keys
        column_mapping: Optional custom column mapping. Defaults to AIRTABLE_COLUMN_MAPPING.

    Returns:
        Dictionary with mapped field names suitable for creating a RawCandidate.

    Example:
        >>> record = {
        ...     "id": "recXYZ123",
        ...     "createdTime": "2024-01-15T10:30:00.000Z",
        ...     "fields": {
        ...         "Full Name": "John Doe",
        ...         "Skills": "Python,Rust",
        ...         "CV": [{"url": "https://example.com/cv.pdf"}],
        ...     }
        ... }
        >>> mapped = map_airtable_row_to_raw_candidate(record)
        >>> mapped["full_name"]
        'John Doe'
        >>> mapped["airtable_record_id"]
        'recXYZ123'
    """
    if column_mapping is None:
        column_mapping = AIRTABLE_COLUMN_MAPPING

    fields = record.get("fields", {})

    # Start with metadata fields
    mapped: dict[str, Any] = {
        "airtable_record_id": record.get("id"),
        "source": "airtable",
        "source_id": record.get("id"),
    }

    # Map each Airtable column to our model field
    for airtable_col, model_field in column_mapping.items():
        value = fields.get(airtable_col)

        # Apply field-specific transformations
        if model_field == "cv_url":
            value = extract_cv_url(value)

        mapped[model_field] = value

    return mapped
