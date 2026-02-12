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

from talent_matching.llm import embed_text, normalize_cv

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
    op_tags={
        # Limit concurrent OpenRouter API calls to avoid rate limits
        # All assets sharing this key compete for the same concurrency slots
        "dagster/concurrency_key": "openrouter_api",
    },
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
    required_resource_keys={"openrouter"},
    io_manager_key="pgvector_io",
    code_version="1.0.0",  # Bump when embedding logic changes
    op_tags={
        # Limit concurrent OpenRouter API calls to avoid rate limits
        # Shares concurrency pool with normalized_candidates
        "dagster/concurrency_key": "openrouter_api",
    },
    metadata={
        "table": "candidate_vectors",
        "vector_types": ["experience", "skills", "summary"],
    },
)
def candidate_vectors(
    context: AssetExecutionContext,
    normalized_candidates: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate semantic embeddings for a candidate profile using OpenRouter.

    Generates multiple vector types for different matching dimensions:
    - experience: Concatenated work experience descriptions
    - skills: Technical skills and domain expertise
    - summary: Overall professional summary

    Uses OpenRouter's embeddings API with text-embedding-3-small (1536 dims).
    """
    record_id = context.partition_key
    openrouter = context.resources.openrouter

    # Fail fast if API key is not configured
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Set it in .env or export it before running the pipeline."
        )

    # Set context for cost tracking
    openrouter.set_context(
        run_id=context.run_id,
        asset_key="candidate_vectors",
        partition_key=record_id,
    )

    normalized_json = normalized_candidates.get("normalized_json", {})

    # Build text for each vector type
    texts_to_embed = {}

    # Experience text: concatenate all work experience
    experience_parts = []
    for exp in normalized_json.get("experience", []):
        exp_text = f"{exp.get('role', '')} at {exp.get('company', '')}"
        if exp.get("description"):
            exp_text += f": {exp['description']}"
        if exp.get("technologies"):
            exp_text += f" Technologies: {', '.join(exp['technologies'])}"
        experience_parts.append(exp_text)
    texts_to_embed["experience"] = (
        " | ".join(experience_parts) if experience_parts else "No experience data"
    )

    # Skills text: combine all skill categories
    skills = normalized_json.get("skills", {})
    skills_parts = []
    for category, skill_list in skills.items():
        if skill_list:
            skills_parts.append(f"{category}: {', '.join(skill_list)}")
    texts_to_embed["skills"] = " | ".join(skills_parts) if skills_parts else "No skills data"

    # Summary text: professional summary + current role + domains
    summary_parts = []
    if normalized_json.get("summary"):
        summary_parts.append(normalized_json["summary"])
    if normalized_json.get("current_role"):
        summary_parts.append(f"Current role: {normalized_json['current_role']}")
    if normalized_json.get("seniority_level"):
        summary_parts.append(f"Seniority: {normalized_json['seniority_level']}")
    if skills.get("domains"):
        summary_parts.append(f"Domains: {', '.join(skills['domains'])}")
    texts_to_embed["summary"] = " ".join(summary_parts) if summary_parts else "No summary data"

    context.log.info(f"Generating embeddings for candidate: {record_id}")

    # Batch embed all texts in a single API call
    text_list = list(texts_to_embed.values())
    vector_types = list(texts_to_embed.keys())

    result = asyncio.run(embed_text(openrouter, text_list))

    # Add metadata for cost tracking
    context.add_output_metadata(
        {
            "embedding_cost_usd": result.cost_usd,
            "embedding_tokens": result.input_tokens,
            "embedding_dimensions": result.dimensions,
            "embedding_model": result.model,
            "vectors_generated": len(result.embeddings),
        }
    )

    context.log.info(
        f"Generated {len(result.embeddings)} vectors for candidate: {record_id} "
        f"(cost: ${result.cost_usd:.6f}, dims: {result.dimensions}, model: {result.model})"
    )

    # Build output records
    vectors = []
    for i, vector_type in enumerate(vector_types):
        vectors.append(
            {
                "candidate_id": record_id,
                "airtable_record_id": normalized_candidates.get("airtable_record_id"),
                "vector_type": vector_type,
                "vector": result.embeddings[i],
                "model_version": result.model,
            }
        )

    return vectors
