"""Candidate pipeline assets.

This module defines the asset graph for processing candidate data:
1. airtable_candidates: Candidates fetched from Airtable (partitioned per record)
2. raw_candidates: Raw candidate data stored in PostgreSQL
3. normalized_candidates: LLM-normalized structured profiles
4. candidate_vectors: Semantic embeddings for matching

The pipeline uses dynamic partitions to process each candidate independently,
enabling incremental processing and per-record change tracking.
"""

from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetIn,
    DataVersion,
    DynamicPartitionsDefinition,
    Output,
    asset,
)


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
        f"Fetched candidate: {candidate.get('full_name', 'Unknown')} "
        f"(version: {data_version})"
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
    io_manager_key="postgres_io",
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
    
    In the full implementation, this asset would:
    1. Send raw CV text to the LLM resource for normalization
    2. Extract structured fields (skills, experience, education, etc.)
    3. Store both the normalized JSON and versioning metadata
    
    For now, returns mock normalized data.
    """
    record_id = context.partition_key
    context.log.info(f"Normalizing candidate: {record_id} (stub implementation)")
    
    # Mock normalized output
    # TODO: Use LLM resource for actual normalization
    normalized = {
        "candidate_id": record_id,
        "airtable_record_id": raw_candidates.get("airtable_record_id"),
        "normalized_json": {
            "name": raw_candidates.get("full_name", "Unknown"),
            "years_of_experience": 5,  # Mock
            "skills": {
                "languages": ["Python", "Rust"],
                "frameworks": ["React", "FastAPI"],
                "domains": ["DeFi", "Infrastructure"],
            },
            "current_role": "Senior Software Engineer",
            "location": raw_candidates.get("location_raw"),
            "professional_summary": raw_candidates.get("professional_summary"),
        },
        "prompt_version": "v1.0.0",
        "model_version": "mock-v1",
    }
    
    context.log.info(f"Normalized candidate: {raw_candidates.get('full_name', 'Unknown')}")
    return normalized


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
        vectors.append({
            "candidate_id": record_id,
            "airtable_record_id": normalized_candidates.get("airtable_record_id"),
            "vector_type": vector_type,
            "vector": [0.1] * 1536,  # Mock 1536-dim vector
            "model_version": "mock-embedding-v1",
        })
    
    context.log.info(f"Generated {len(vectors)} vectors for candidate: {record_id}")
    return vectors
