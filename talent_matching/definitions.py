"""Dagster definitions for the Talent Matching system.

This module is the entry point for Dagster. It wires together:
- All assets (candidates, jobs, matches)
- Resources (OpenRouter for LLM + embeddings, GitHub API, Airtable)
- IO Managers (PostgreSQL, pgvector)
- Sensors (Airtable polling)
- Jobs (candidate pipeline, sync, sample)
- Configuration for different environments (dev, staging, prod)
"""

import os

from dagster import (
    Definitions,
    EnvVar,
    load_assets_from_modules,
)
from dotenv import load_dotenv

from talent_matching.assets import candidates, jobs, social
from talent_matching.io_managers import PgVectorIOManager, PostgresMetricsIOManager
from talent_matching.jobs import (
    candidate_ingest_job,
    candidate_pipeline_job,
    sample_candidates_job,
    sync_airtable_job,
)
from talent_matching.resources import (
    AirtableResource,
    GitHubAPIResource,
    LinkedInAPIResource,
    OpenRouterResource,
    TwitterAPIResource,
)
from talent_matching.sensors.airtable_sensor import airtable_candidate_sensor

# Load environment variables from .env file (must be before resource initialization)
load_dotenv()

# Load all assets from the modules
all_assets = load_assets_from_modules([candidates, jobs, social])


def get_environment() -> str:
    """Get current environment from env var."""
    return os.getenv("ENVIRONMENT", "development")


# Development resources (mock implementations)
# Using Dagster EnvVar for deferred resolution and better config visibility
dev_resources = {
    # Airtable resource for fetching candidates
    "airtable": AirtableResource(
        base_id=EnvVar("AIRTABLE_BASE_ID"),
        table_id=EnvVar("AIRTABLE_TABLE_ID"),
        api_key=EnvVar("AIRTABLE_API_KEY"),
    ),
    # OpenRouter LLM resource with cost tracking (also handles embeddings)
    "openrouter": OpenRouterResource(
        api_key=EnvVar("OPENROUTER_API_KEY"),
        default_model="openai/gpt-4o-mini",
    ),
    # GitHub API resource
    "github": GitHubAPIResource(
        mock_mode=True,
    ),
    # Twitter/X API resource
    "twitter_api": TwitterAPIResource(
        mock_mode=True,
    ),
    # LinkedIn API resource
    "linkedin_api": LinkedInAPIResource(
        data_source="mock",
    ),
    # IO Managers for dual storage
    "postgres_io": PostgresMetricsIOManager(
        host=EnvVar("POSTGRES_HOST"),
        port=EnvVar.int("POSTGRES_PORT"),
        user=EnvVar("POSTGRES_USER"),
        password=EnvVar("POSTGRES_PASSWORD"),
        database=EnvVar("POSTGRES_DB"),
    ),
    "pgvector_io": PgVectorIOManager(
        host=EnvVar("POSTGRES_HOST"),
        port=EnvVar.int("POSTGRES_PORT"),
        user=EnvVar("POSTGRES_USER"),
        password=EnvVar("POSTGRES_PASSWORD"),
        database=EnvVar("POSTGRES_DB"),
    ),
}


def get_resources():
    """Get resources based on current environment."""
    env = get_environment()

    if env == "production":
        # In production, we would return prod_resources
        # For now, use dev resources
        return dev_resources
    elif env == "staging":
        # Staging could use real LLMs with cheaper models
        return dev_resources
    else:
        # Development uses mock resources
        return dev_resources


# All jobs available in the dashboard
all_jobs = [
    # Asset jobs (partitioned) - use Backfill in UI to select partitions
    candidate_pipeline_job,
    candidate_ingest_job,
    # Ops jobs (non-partitioned)
    sync_airtable_job,
    sample_candidates_job,
]

# All sensors
all_sensors = [
    airtable_candidate_sensor,
]

# Create the Dagster Definitions object
defs = Definitions(
    assets=all_assets,
    resources=get_resources(),
    jobs=all_jobs,
    sensors=all_sensors,
)


def main():
    """Entry point for CLI usage."""
    print("Talent Matching Dagster project loaded successfully!")
    print(f"Environment: {get_environment()}")
    print(f"Assets: {len(all_assets)}")
    print(f"Jobs: {len(all_jobs)}")
    print(f"Sensors: {len(all_sensors)}")
    print("\nAvailable jobs:")
    for job in all_jobs:
        print(f"  - {job.name}")
    print("\nRun 'dagster dev' to start the development server.")


if __name__ == "__main__":
    main()
