"""Dagster definitions for the Talent Matching system.

This module is the entry point for Dagster. It wires together:
- All assets (candidates, jobs, matches)
- Resources (LLM, embeddings, GitHub API)
- IO Managers (PostgreSQL, pgvector)
- Configuration for different environments (dev, staging, prod)
"""

import os

from dagster import (
    Definitions,
    EnvVar,
    load_assets_from_modules,
)

from talent_matching.assets import candidates, jobs, social
from talent_matching.io_managers import PgVectorIOManager, PostgresMetricsIOManager
from talent_matching.resources import (
    GitHubAPIResource,
    LinkedInAPIResource,
    MockEmbeddingResource,
    MockLLMResource,
    TwitterAPIResource,
)

# Load all assets from the modules
all_assets = load_assets_from_modules([candidates, jobs, social])


def get_environment() -> str:
    """Get current environment from env var."""
    return os.getenv("ENVIRONMENT", "development")


# Development resources (mock implementations)
dev_resources = {
    # LLM resource for CV/job normalization and scoring
    "llm": MockLLMResource(
        model_version="mock-v1",
        prompt_version="v1.0.0",
    ),
    # Embedding resource for vector generation
    "embeddings": MockEmbeddingResource(
        model_version="mock-embedding-v1",
        dimensions=1536,
        deterministic=True,
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
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "talent"),
        password=os.getenv("POSTGRES_PASSWORD", "talent_dev"),
        database=os.getenv("POSTGRES_DB", "talent_matching"),
    ),
    "pgvector_io": PgVectorIOManager(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "talent"),
        password=os.getenv("POSTGRES_PASSWORD", "talent_dev"),
        database=os.getenv("POSTGRES_DB", "talent_matching"),
    ),
}

# Production resources would use real LLM APIs
# These are commented out until the llm extras are installed
# from openai import OpenAI
#
# prod_resources = {
#     "llm": OpenAILLMResource(
#         api_key=EnvVar("OPENAI_API_KEY"),
#         model="gpt-4o",
#     ),
#     "embeddings": OpenAIEmbeddingResource(
#         api_key=EnvVar("OPENAI_API_KEY"),
#         model="text-embedding-3-large",
#     ),
#     "github": GitHubAPIResource(
#         api_token=EnvVar("GITHUB_TOKEN"),
#         mock_mode=False,
#     ),
#     "postgres_io": PostgresMetricsIOManager(...),
#     "pgvector_io": PgVectorIOManager(...),
# }


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


# Create the Dagster Definitions object
defs = Definitions(
    assets=all_assets,
    resources=get_resources(),
)


def main():
    """Entry point for CLI usage."""
    print("Talent Matching Dagster project loaded successfully!")
    print(f"Environment: {get_environment()}")
    print(f"Assets: {len(all_assets)}")
    print("Run 'dagster dev' to start the development server.")


if __name__ == "__main__":
    main()
