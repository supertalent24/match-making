"""Airtable field mapping utilities.

This module provides functions for mapping Airtable field formats to our
internal data model. These are used by the AirtableResource but can also
be used independently for testing and data transformation.
"""

import re
from typing import Any


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
        match = re.search(r'\((https?://[^)]+)\)', cv_field)
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
