"""Candidate pipeline assets.

This module defines the asset graph for processing candidate data:
1. airtable_candidates: Candidates fetched from Airtable (partitioned per record)
2. raw_candidates: Raw candidate data stored in PostgreSQL
3. normalized_candidates: LLM-normalized structured profiles
4. candidate_vectors: Semantic embeddings for matching

The pipeline uses dynamic partitions to process each candidate independently,
enabling incremental processing and per-record change tracking.
"""

import asyncio
import os
from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetIn,
    DataVersion,
    DynamicPartitionsDefinition,
    Output,
    asset,
)

from talent_matching.llm import normalize_cv

# Dynamic partition definition for candidates
# Each candidate record gets its own partition key (Airtable record ID)
candidate_partitions = DynamicPartitionsDefinition(name="candidates")


@asset(
    partitions_def=candidate_partitions,
    description="Single candidate record fetched from Airtable",
    group_name="candidates",
    required_resource_keys={"airtable"},
    metadata={
        "source": "airtable",
    },
)
def airtable_candidates(context: AssetExecutionContext) -> Output[dict[str, Any]]:
    """Fetch a single candidate from Airtable by partition key.

    Each partition key corresponds to an Airtable record ID.
    The asset tracks data versions per record to enable change detection.

    Returns:
        Output with the candidate data and a DataVersion for staleness tracking.
    """
    record_id = context.partition_key
    context.log.info(f"Fetching candidate record: {record_id}")

    airtable = context.resources.airtable
    candidate = airtable.fetch_record_by_id(record_id)

    # Extract data version for Dagster's change detection
    data_version = candidate.pop("_data_version", None)

    context.log.info(
        f"Fetched candidate: {candidate.get('full_name', 'Unknown')} " f"(version: {data_version})"
    )

    return Output(
        value=candidate,
        data_version=DataVersion(data_version) if data_version else None,
    )


@asset(
    partitions_def=candidate_partitions,
    ins={"airtable_candidates": AssetIn()},
    description="Raw candidate data stored in PostgreSQL",
    group_name="candidates",
    io_manager_key="postgres_io",
    metadata={
        "table": "raw_candidates",
    },
)
def raw_candidates(
    context: AssetExecutionContext,
    airtable_candidates: dict[str, Any],
) -> dict[str, Any]:
    """Store raw candidate data in PostgreSQL.

    This asset receives candidate data from Airtable and prepares it
    for storage in the raw_candidates table. The postgres_io manager
    handles the actual database insertion/update.

    The partition key (Airtable record ID) ensures each candidate
    is processed independently.
    """
    record_id = context.partition_key
    context.log.info(f"Storing raw candidate: {record_id}")

    # The airtable_candidates data is already mapped to our model fields
    # Just pass it through to the IO manager
    raw_data = {
        **airtable_candidates,
        # Ensure required fields have defaults
        "source": airtable_candidates.get("source", "airtable"),
    }

    context.log.info(
        f"Raw candidate data ready for storage: {raw_data.get('full_name', 'Unknown')}"
    )

    return raw_data


@asset(
    partitions_def=candidate_partitions,
    ins={"raw_candidates": AssetIn()},
    description="LLM-normalized candidate profiles with structured fields",
    group_name="candidates",
    required_resource_keys={"openrouter"},
    io_manager_key="postgres_io",
    code_version="1.3.0",  # Bump when prompt or normalization logic changes
    metadata={
        "table": "normalized_candidates",
        "llm_operation": "normalize_cv",
    },
)
def normalized_candidates(
    context: AssetExecutionContext,
    raw_candidates: dict[str, Any],
) -> dict[str, Any]:
    """Normalize raw candidate data into structured profiles using LLM.

    Uses OpenRouter API via talent_matching.llm operations to:
    1. Send raw CV text to the LLM for normalization
    2. Extract structured fields (skills, experience, education, etc.)
    3. Track token usage and costs per request
    4. Store both the normalized data and versioning metadata

    The code_version in the decorator tracks when this asset's logic changes.
    Bump it when modifying prompt handling or normalization logic.
    """
    record_id = context.partition_key
    openrouter = context.resources.openrouter

    # Set context for cost tracking
    openrouter.set_context(
        run_id=context.run_id,
        asset_key="normalized_candidates",
        partition_key=record_id,
    )

    # Build CV text from available raw data
    cv_parts = []
    if raw_candidates.get("full_name"):
        cv_parts.append(f"Name: {raw_candidates['full_name']}")
    if raw_candidates.get("professional_summary"):
        cv_parts.append(f"Summary: {raw_candidates['professional_summary']}")
    if raw_candidates.get("skills_raw"):
        cv_parts.append(f"Skills: {raw_candidates['skills_raw']}")
    if raw_candidates.get("work_experience_raw"):
        cv_parts.append(f"Experience: {raw_candidates['work_experience_raw']}")
    if raw_candidates.get("cv_text"):
        cv_parts.append(f"CV Content:\n{raw_candidates['cv_text']}")
    if raw_candidates.get("location_raw"):
        cv_parts.append(f"Location: {raw_candidates['location_raw']}")
    if raw_candidates.get("proof_of_work"):
        cv_parts.append(f"Proof of Work: {raw_candidates['proof_of_work']}")

    cv_text = "\n\n".join(cv_parts)

    if not cv_text.strip():
        context.log.warning(f"No CV data available for candidate: {record_id}")
        # Add metadata for skipped LLM call
        context.add_output_metadata(
            {
                "llm_cost_usd": 0.0,
                "llm_tokens_input": 0,
                "llm_tokens_output": 0,
                "llm_model": "skipped",
                "skip_reason": "no_cv_data",
            }
        )
        # Return minimal normalized data for candidates without CV text
        return {
            "candidate_id": record_id,
            "airtable_record_id": raw_candidates.get("airtable_record_id"),
            "normalized_json": {
                "name": raw_candidates.get("full_name", "Unknown"),
                "years_of_experience": None,
                "skills": {"languages": [], "frameworks": [], "tools": [], "domains": []},
                "current_role": None,
                "location": None,
                "professional_summary": None,
            },
            "model_version": None,
        }

    context.log.info(f"Normalizing candidate: {record_id} via OpenRouter API")

    # Fail fast if API key is not configured
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Set it in .env or export it before running the pipeline."
        )

    # Call the normalize_cv operation (prompt lives in talent_matching.llm.operations)
    result = asyncio.run(normalize_cv(openrouter, cv_text))

    # Add LLM cost metadata to the materialization (visible in Dagster UI)
    context.add_output_metadata(
        {
            "llm_cost_usd": result.cost_usd,
            "llm_tokens_input": result.input_tokens,
            "llm_tokens_output": result.output_tokens,
            "llm_tokens_total": result.total_tokens,
            "llm_model": result.model,
        }
    )

    context.log.info(
        f"Normalized candidate: {result.data.get('name', 'Unknown')} "
        f"(cost: ${result.cost_usd:.6f}, tokens: {result.total_tokens}, model: {result.model})"
    )

    return {
        "candidate_id": record_id,
        "airtable_record_id": raw_candidates.get("airtable_record_id"),
        "normalized_json": result.data,
        "model_version": result.model,
    }


@asset(
    partitions_def=candidate_partitions,
    ins={"normalized_candidates": AssetIn()},
    description="Semantic embeddings for candidate profiles",
    group_name="candidates",
    io_manager_key="pgvector_io",
    metadata={
        "table": "candidate_vectors",
        "vector_types": ["experience", "domain_context", "personality"],
    },
)
def candidate_vectors(
    context: AssetExecutionContext,
    normalized_candidates: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate semantic embeddings for a candidate profile.

    Generates multiple vector types:
    - experience: Concatenated experience across all roles
    - domain_context: Industries and problem spaces
    - personality: Work style and personality signals

    For now, returns mock vector data.
    """
    record_id = context.partition_key
    context.log.info(f"Generating vectors for candidate: {record_id} (stub implementation)")

    # Mock vector output (actual vectors would be 1536-dimensional)
    # TODO: Use embeddings resource for actual vector generation
    vectors = []
    for vector_type in ["experience", "domain_context", "personality"]:
        vectors.append(
            {
                "candidate_id": record_id,
                "airtable_record_id": normalized_candidates.get("airtable_record_id"),
                "vector_type": vector_type,
                "vector": [0.1] * 1536,  # Mock 1536-dim vector
                "model_version": "mock-embedding-v1",
            }
        )

    context.log.info(f"Generated {len(vectors)} vectors for candidate: {record_id}")
    return vectors
