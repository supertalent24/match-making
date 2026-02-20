"""Create (N)-prefixed normalized candidate columns in the Airtable candidates table.

Uses the Airtable API to add the columns required for airtable_candidate_sync.
Requires an Airtable Personal Access Token with schema read + write access to the base
(create at https://airtable.com/create/tokens and add the schema scope for your base).
If you get 403/401 on GET or POST, the token may need "schema.bases:read" and write
for the base, or your plan may require a separate Metadata API token.

Safety / rollback:
  - This script writes a local backup (records + schema) to scripts/airtable_backups/
    before creating any columns, unless you pass --skip-backup.
  - Airtable also has built-in base snapshots: in the base, click the history icon
    (upper-right) → Snapshots → Take a snapshot. Restoring creates a new base
    (see https://support.airtable.com/docs/taking-and-restoring-base-snapshots).

Usage:
  From project root (with .env loaded):
    uv run python scripts/create_airtable_normalized_columns.py
  Skip local backup (e.g. you already took an Airtable snapshot):
    uv run python scripts/create_airtable_normalized_columns.py --skip-backup
  Or with explicit env:
    AIRTABLE_BASE_ID=appXXX AIRTABLE_TABLE_ID=tblXXX AIRTABLE_API_KEY=patXXX \\
    python scripts/create_airtable_normalized_columns.py

Skips columns that already exist. Uses the same (N) names as AIRTABLE_CANDIDATES_WRITEBACK_FIELDS.
"""

import json
import os
import sys
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv

# Project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from talent_matching.utils.airtable_mapper import (
    AIRTABLE_CANDIDATES_WRITEBACK_FIELDS,
)

load_dotenv()

# Airtable field type and options per normalized field (model attribute name)
# Types: singleLineText, multilineText, email, number, singleSelect, multipleSelects, dateTime, currency
FIELD_SPECS: dict[str, dict] = {
    "full_name": {"type": "singleLineText"},
    "email": {"type": "email"},
    "phone": {"type": "phoneNumber"},
    "location_city": {"type": "singleLineText"},
    "location_country": {"type": "singleLineText"},
    "location_region": {"type": "singleLineText"},
    "timezone": {"type": "singleLineText"},
    "professional_summary": {"type": "multilineText"},
    "current_role": {"type": "singleLineText"},
    "seniority_level": {
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "junior"},
                {"name": "mid"},
                {"name": "senior"},
                {"name": "lead"},
                {"name": "principal"},
                {"name": "executive"},
            ]
        },
    },
    "years_of_experience": {"type": "number", "options": {"precision": 0}},
    # Long text so we can store arbitrary values; multipleSelects would require existing options
    "desired_job_categories": {"type": "multilineText"},
    "skills_summary": {"type": "multilineText"},
    "companies_summary": {"type": "multilineText"},
    "notable_achievements": {"type": "multilineText"},
    "verified_communities": {"type": "multilineText"},
    "compensation_min": {"type": "number", "options": {"precision": 0}},
    "compensation_max": {"type": "number", "options": {"precision": 0}},
    "compensation_currency": {"type": "singleLineText"},
    "job_count": {"type": "number", "options": {"precision": 0}},
    "job_switches_count": {"type": "number", "options": {"precision": 0}},
    "average_tenure_months": {"type": "number", "options": {"precision": 0}},
    "longest_tenure_months": {"type": "number", "options": {"precision": 0}},
    "education_highest_degree": {"type": "singleLineText"},
    "education_field": {"type": "singleLineText"},
    "education_institution": {"type": "singleLineText"},
    "hackathon_wins_count": {"type": "number", "options": {"precision": 0}},
    "hackathon_total_prize_usd": {"type": "number", "options": {"precision": 0}},
    "solana_hackathon_wins": {"type": "number", "options": {"precision": 0}},
    "x_handle": {"type": "singleLineText"},
    "linkedin_handle": {"type": "singleLineText"},
    "github_handle": {"type": "singleLineText"},
    "social_followers_total": {"type": "number", "options": {"precision": 0}},
    "verification_status": {
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "unverified"},
                {"name": "verified"},
            ]
        },
    },
    "verification_notes": {"type": "multilineText"},
    "verified_at": {
        "type": "dateTime",
        "options": {
            "dateFormat": {"name": "iso", "format": "YYYY-MM-DD"},
            "timeFormat": {"name": "24hour", "format": "HH:mm"},
            "timeZone": "utc",
        },
    },
    "prompt_version": {"type": "singleLineText"},
    "model_version": {"type": "singleLineText"},
    "confidence_score": {"type": "number", "options": {"precision": 4}},
    "normalized_at": {
        "type": "dateTime",
        "options": {
            "dateFormat": {"name": "iso", "format": "YYYY-MM-DD"},
            "timeFormat": {"name": "24hour", "format": "HH:mm"},
            "timeZone": "utc",
        },
    },
}


BACKUP_DIR = os.path.join(os.path.dirname(__file__), "airtable_backups")


def get_tables_response(base_id: str, token: str) -> dict:
    """GET full tables schema for the base."""
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def get_existing_field_names(base_id: str, table_id: str, token: str) -> set[str]:
    """GET table schema and return the set of existing field names."""
    data = get_tables_response(base_id, token)
    tables = data.get("tables", [])
    for table in tables:
        if table.get("id") == table_id:
            return {f.get("name") for f in table.get("fields", []) if f.get("name")}
    return set()


def fetch_all_records(base_id: str, table_id: str, token: str) -> list[dict]:
    """Fetch all records from the table (follows offset pagination)."""
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    headers = {"Authorization": f"Bearer {token}"}
    all_records: list[dict] = []
    offset: str | None = None
    with httpx.Client(timeout=60.0) as client:
        while True:
            params = {} if offset is None else {"offset": offset}
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
    return all_records


def backup_table_to_file(base_id: str, table_id: str, token: str) -> str:
    """Save a copy of the table schema and all records to a timestamped JSON file.

    Returns the path to the written file.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"candidates_{base_id}_{table_id}_{ts}.json"
    filepath = os.path.join(BACKUP_DIR, filename)

    data = get_tables_response(base_id, token)
    tables = data.get("tables", [])
    table_schema = None
    for t in tables:
        if t.get("id") == table_id:
            table_schema = {"name": t.get("name"), "id": t.get("id"), "fields": t.get("fields", [])}
            break
    if table_schema is None:
        table_schema = {"id": table_id, "fields": []}

    print("Fetching all records for backup...")
    records = fetch_all_records(base_id, table_id, token)
    print(f"  {len(records)} records")

    payload = {
        "backed_up_at": datetime.now(UTC).isoformat(),
        "base_id": base_id,
        "table_id": table_id,
        "schema": table_schema,
        "record_count": len(records),
        "records": records,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return filepath


def create_field(base_id: str, table_id: str, token: str, name: str, spec: dict) -> None:
    """POST to create one field on the table."""
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"name": name, "type": spec["type"]}
    if "options" in spec:
        body["options"] = spec["options"]
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=body)
        if response.status_code == 403:
            print(
                "\n403 Forbidden: token does not have schema write access. "
                "Create a new token at https://airtable.com/create/tokens with schema write for this base, "
                "set AIRTABLE_SCHEMA_TOKEN in .env, and run again."
            )
            response.raise_for_status()
        if response.status_code == 422:
            err = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            err_type = err.get("error", {}).get("type", "") if isinstance(err, dict) else ""
            if err_type == "DUPLICATE_OR_EMPTY_FIELD_NAME":
                print(f"  Skipping {name!r} (already exists or invalid name).")
                return
            print(f"\n422 Unprocessable Entity for field {name!r}. Response: {response.text}")
            response.raise_for_status()
        response.raise_for_status()


def main() -> None:
    skip_backup = "--skip-backup" in sys.argv
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_id = os.getenv("AIRTABLE_TABLE_ID")
    token = os.getenv("AIRTABLE_SCHEMA_TOKEN") or os.getenv("AIRTABLE_API_KEY")
    if not base_id or not table_id or not token:
        print(
            "Set AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID, and AIRTABLE_API_KEY (or AIRTABLE_SCHEMA_TOKEN) in .env"
        )
        sys.exit(1)

    print(f"Base: {base_id}, Table: {table_id}")

    if not skip_backup:
        print("Writing local backup (records + schema)...")
        filepath = backup_table_to_file(base_id, table_id, token)
        print(f"  Backup saved to: {filepath}")
    else:
        print("Skipping backup (--skip-backup).")

    print("Fetching existing field names...")
    existing = get_existing_field_names(base_id, table_id, token)
    print(f"Found {len(existing)} existing fields")

    to_create = []
    for our_key, airtable_name in AIRTABLE_CANDIDATES_WRITEBACK_FIELDS.items():
        if airtable_name not in existing:
            to_create.append((airtable_name, FIELD_SPECS.get(our_key, {"type": "singleLineText"})))

    if not to_create:
        print("All (N) columns already exist. Nothing to do.")
        return

    print(f"Creating {len(to_create)} (N) columns...")
    for name, spec in to_create:
        print(f"  Creating: {name}")
        create_field(base_id, table_id, token, name, spec)
    print("Done.")


if __name__ == "__main__":
    main()
