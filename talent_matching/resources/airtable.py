"""Airtable API resource for fetching candidate data.

This resource connects to Airtable to fetch candidate records from the
Tech Assignment table. It supports:
- Fetching all records
- Fetching specific records by ID
- Tracking record modification times for incremental syncs
"""

import hashlib
from typing import Any

import httpx
from dagster import ConfigurableResource
from pydantic import Field

from talent_matching.utils.airtable_mapper import (
    map_airtable_row_to_raw_candidate,
    map_airtable_row_to_raw_job,
)


class AirtableResource(ConfigurableResource):
    """Airtable API resource for fetching candidate and job data.

    This resource connects to the Airtable REST API to fetch records.
    It supports incremental syncs by tracking record modification times.

    Configuration:
        base_id: The Airtable base ID (starts with 'app')
        table_id: The Airtable table ID (starts with 'tbl')
        api_key: Personal access token for Airtable API

    Example:
        ```python
        airtable = AirtableResource(
            base_id="appXXXXXXXXXXXXXX",
            table_id="tblXXXXXXXXXXXXXX",
            api_key=EnvVar("AIRTABLE_API_KEY"),
        )
        ```
    """

    base_id: str = Field(
        description="Airtable base ID (starts with 'app')",
    )
    table_id: str = Field(
        description="Airtable table ID (starts with 'tbl')",
    )
    api_key: str = Field(
        description="Airtable Personal Access Token (read; used for write too unless write_api_key is set)",
    )
    write_api_key: str | None = Field(
        default=None,
        description="Optional token with data.records:write scope for PATCH. If unset, api_key is used.",
    )

    # Column name mapping from Airtable to our model fields
    COLUMN_MAPPING: dict[str, str] = {
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

    @property
    def _base_url(self) -> str:
        """Base URL for Airtable API."""
        return f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}"

    def _auth_headers(self, token: str | None = None) -> dict[str, str]:
        """Build request headers; token defaults to api_key for read, or use _write_headers for PATCH."""
        raw = token if token is not None else self.api_key
        resolved = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
        return {
            "Authorization": f"Bearer {resolved}",
            "Content-Type": "application/json",
        }

    @property
    def _headers(self) -> dict[str, str]:
        """Request headers with authentication (read)."""
        return self._auth_headers()

    def _write_headers(self) -> dict[str, str]:
        """Request headers for write (PATCH); use write_api_key if set."""
        raw = self.write_api_key or self.api_key
        return self._auth_headers(raw)

    def fetch_all_records(self) -> list[dict[str, Any]]:
        """Fetch all records from the Airtable table.

        Handles pagination automatically by following the 'offset' cursor.

        Returns:
            List of records with Airtable record IDs and mapped field names.
        """
        all_records: list[dict[str, Any]] = []
        offset: str | None = None

        with httpx.Client(timeout=30.0) as client:
            while True:
                params: dict[str, str] = {}
                if offset:
                    params["offset"] = offset

                response = client.get(
                    self._base_url,
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                for record in data.get("records", []):
                    mapped_record = self._map_record(record)
                    all_records.append(mapped_record)

                # Check for more pages
                offset = data.get("offset")
                if not offset:
                    break

        return all_records

    def fetch_record_by_id(self, record_id: str) -> dict[str, Any]:
        """Fetch a single record by its Airtable record ID.

        Args:
            record_id: The Airtable record ID (starts with 'rec')

        Returns:
            Mapped record dictionary.
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{self._base_url}/{record_id}",
                headers=self._headers,
            )
            response.raise_for_status()
            record = response.json()

        return self._map_record(record)

    def fetch_records_modified_since(self, since_iso: str) -> list[dict[str, Any]]:
        """Fetch records modified since a given timestamp.

        Uses Airtable's filterByFormula to get only recently modified records.

        Args:
            since_iso: ISO 8601 timestamp (e.g., "2024-01-15T10:30:00.000Z")

        Returns:
            List of records modified after the given timestamp.
        """
        formula = f"LAST_MODIFIED_TIME() > '{since_iso}'"

        all_records: list[dict[str, Any]] = []
        offset: str | None = None

        with httpx.Client(timeout=30.0) as client:
            while True:
                params: dict[str, str] = {"filterByFormula": formula}
                if offset:
                    params["offset"] = offset

                response = client.get(
                    self._base_url,
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                for record in data.get("records", []):
                    mapped_record = self._map_record(record)
                    all_records.append(mapped_record)

                offset = data.get("offset")
                if not offset:
                    break

        return all_records

    def _map_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Map an Airtable record to our internal field names.

        Args:
            record: Raw Airtable record with 'id', 'fields', 'createdTime'

        Returns:
            Mapped record with standardized field names.
        """
        # Use shared mapper utility
        mapped = map_airtable_row_to_raw_candidate(record, self.COLUMN_MAPPING)

        # Add created_time from Airtable metadata
        mapped["created_time"] = record.get("createdTime")

        # Compute a data version hash for this record
        mapped["_data_version"] = self._compute_record_hash(mapped)

        return mapped

    def _compute_record_hash(self, mapped_record: dict[str, Any]) -> str:
        """Compute a hash of the record content for change detection.

        This enables Dagster to skip re-processing unchanged records.
        The hash excludes metadata fields that don't affect processing.

        Args:
            mapped_record: The mapped record dictionary

        Returns:
            SHA-256 hash of the content fields.
        """
        # Fields that affect processing (exclude metadata)
        content_fields = [
            "full_name",
            "location_raw",
            "desired_job_categories_raw",
            "skills_raw",
            "cv_url",
            "professional_summary",
            "proof_of_work",
            "salary_range_raw",
            "x_profile_url",
            "linkedin_url",
            "earn_profile_url",
            "github_url",
            "work_experience_raw",
        ]

        content = {k: mapped_record.get(k) for k in content_fields}
        content_str = str(sorted(content.items()))

        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def get_all_record_ids(self) -> list[str]:
        """Get all record IDs from the table.

        This is useful for initializing dynamic partitions.
        Only fetches the record ID field to minimize data transfer.

        Returns:
            List of Airtable record IDs.
        """
        record_ids: list[str] = []
        offset: str | None = None

        with httpx.Client(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {"fields[]": []}  # Empty fields = only IDs
                if offset:
                    params["offset"] = offset

                response = client.get(
                    self._base_url,
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                for record in data.get("records", []):
                    record_ids.append(record["id"])

                offset = data.get("offset")
                if not offset:
                    break

        return record_ids

    def update_record(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update an Airtable candidate record with the given fields (PATCH).

        Args:
            record_id: Airtable record ID (e.g. recXXX).
            fields: Dict of Airtable column names to values.

        Returns:
            The updated Airtable record as returned by the API.

        Raises:
            httpx.HTTPStatusError: On API errors. 403 with a hint to use a token
                with data.records:write scope (or set AIRTABLE_WRITE_TOKEN).
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.patch(
                f"{self._base_url}/{record_id}",
                headers=self._write_headers(),
                json={"fields": fields},
            )
            if response.status_code == 403:
                raise httpx.HTTPStatusError(
                    "403 Forbidden: Airtable token does not have write access. "
                    "Create a token at https://airtable.com/create/tokens with scope "
                    "'data.records:write' (and access to this base), then set AIRTABLE_API_KEY "
                    "or AIRTABLE_WRITE_TOKEN in .env and restart Dagster.",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()


class AirtableJobsResource(ConfigurableResource):
    """Airtable API resource for fetching job records (e.g. Customers STT table).

    Same interface as AirtableResource but uses jobs table and job field mapping.
    Configure with AIRTABLE_BASE_ID, AIRTABLE_JOBS_TABLE_ID, AIRTABLE_API_KEY.
    """

    base_id: str = Field(description="Airtable base ID (starts with 'app')")
    table_id: str = Field(description="Airtable jobs table ID (starts with 'tbl')")
    api_key: str = Field(description="Airtable Personal Access Token")
    write_api_key: str | None = Field(
        default=None,
        description="Optional token with data.records:write scope for PATCH.",
    )

    @property
    def _base_url(self) -> str:
        return f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _write_headers(self) -> dict[str, str]:
        raw = self.write_api_key or self.api_key
        token = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def fetch_record_by_id(self, record_id: str) -> dict[str, Any]:
        """Fetch a single job record by Airtable record ID. Returns mapped job fields."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{self._base_url}/{record_id}",
                headers=self._headers,
            )
            response.raise_for_status()
            record = response.json()
        return self._map_record(record)

    def _map_record(self, record: dict[str, Any]) -> dict[str, Any]:
        mapped = map_airtable_row_to_raw_job(record)
        mapped["created_time"] = record.get("createdTime")
        mapped["_data_version"] = self._compute_record_hash(mapped)
        return mapped

    def _compute_record_hash(self, mapped_record: dict[str, Any]) -> str:
        content_fields = [
            "job_description_link",
            "job_title_raw",
            "company_name",
            "x_url",
            "company_website_url",
        ]
        content = {k: mapped_record.get(k) for k in content_fields}
        content_str = str(sorted(content.items()))
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def get_all_record_ids(self) -> list[str]:
        """Get all record IDs from the jobs table for dynamic partitions."""
        record_ids: list[str] = []
        offset: str | None = None
        with httpx.Client(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {"fields[]": []}
                if offset:
                    params["offset"] = offset
                response = client.get(
                    self._base_url,
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                for record in data.get("records", []):
                    record_ids.append(record["id"])
                offset = data.get("offset")
                if not offset:
                    break
        return record_ids

    def update_record(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update an Airtable job record with the given fields (PATCH).

        Args:
            record_id: Airtable record ID (e.g. recXXX).
            fields: Dict of Airtable column names to values (e.g. {"Hiring Job Title": "Senior Engineer"}).

        Returns:
            The updated Airtable record as returned by the API.
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.patch(
                f"{self._base_url}/{record_id}",
                headers=self._write_headers(),
                json={"fields": fields},
            )
            if response.status_code == 403:
                raise httpx.HTTPStatusError(
                    "403 Forbidden: Airtable token does not have write access. "
                    "Create a token at https://airtable.com/create/tokens with scope "
                    "'data.records:write', then set AIRTABLE_API_KEY or AIRTABLE_WRITE_TOKEN.",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()
