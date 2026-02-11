"""Candidate pipeline assets.

This module defines the asset graph for processing candidate data:
1. raw_candidates: Ingested candidate data from CVs, GitHub, forms
2. normalized_candidates: LLM-normalized structured profiles
3. candidate_vectors: Semantic embeddings for matching

These are currently stub implementations that establish the asset structure.
The actual processing logic will be implemented in subsequent phases.
"""

from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetIn,
    asset,
)


@asset(
    description="Raw candidate data ingested from various sources (CVs, GitHub, application forms)",
    group_name="candidates",
    metadata={
        "table": "raw_candidates",
        "source_types": ["cv", "github", "form"],
    },
)
def raw_candidates(context: AssetExecutionContext) -> list[dict[str, Any]]:
    """Ingest raw candidate data from multiple sources.
    
    In the full implementation, this asset would:
    1. Read CVs from a configured directory or S3 bucket
    2. Parse PDFs/DOCXs into text
    3. Fetch GitHub profile data via API
    4. Collect application form responses
    
    For now, returns mock data to establish the pipeline structure.
    """
    context.log.info("Ingesting raw candidate data (stub implementation)")
    
    # Mock data representing raw ingested candidates
    mock_candidates = [
        {
            "id": "candidate-001",
            "source": "cv",
            "raw_data": {
                "text": "John Doe - Senior Software Engineer with 5 years experience in Python and Rust...",
                "filename": "john_doe_resume.pdf",
            },
        },
        {
            "id": "candidate-002", 
            "source": "github",
            "raw_data": {
                "username": "jdoe",
                "bio": "Building things with code",
                "repos": 42,
            },
        },
    ]
    
    context.log.info(f"Ingested {len(mock_candidates)} raw candidates")
    return mock_candidates


@asset(
    ins={"raw_candidates": AssetIn()},
    description="LLM-normalized candidate profiles with structured fields",
    group_name="candidates",
    metadata={
        "table": "normalized_candidates",
        "llm_operation": "normalize_cv",
    },
)
def normalized_candidates(
    context: AssetExecutionContext,
    raw_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize raw candidate data into structured profiles using LLM.
    
    In the full implementation, this asset would:
    1. Send raw CV text to the LLM resource for normalization
    2. Extract structured fields (skills, experience, education, etc.)
    3. Store both the normalized JSON and versioning metadata
    
    For now, returns mock normalized data.
    """
    context.log.info(f"Normalizing {len(raw_candidates)} candidates (stub implementation)")
    
    # Mock normalized output
    normalized = []
    for raw in raw_candidates:
        normalized.append({
            "candidate_id": raw["id"],
            "normalized_json": {
                "name": "Mock Candidate",
                "years_of_experience": 5,
                "skills": {
                    "languages": ["Python", "Rust"],
                    "frameworks": ["React", "FastAPI"],
                    "domains": ["DeFi", "Infrastructure"],
                },
                "current_role": "Senior Software Engineer",
            },
            "prompt_version": "v1.0.0",
            "model_version": "mock-v1",
        })
    
    context.log.info(f"Normalized {len(normalized)} candidate profiles")
    return normalized


@asset(
    ins={"normalized_candidates": AssetIn()},
    description="Semantic embeddings for candidate profiles (experience, skills, domain context)",
    group_name="candidates",
    metadata={
        "table": "candidate_vectors",
        "vector_types": ["position", "experience", "domain_context", "personality"],
    },
)
def candidate_vectors(
    context: AssetExecutionContext,
    normalized_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate semantic embeddings for candidate profiles.
    
    In the full implementation, this asset would:
    1. Extract text sections for each vector type
    2. Generate embeddings using the embedding resource
    3. Store vectors with metadata for similarity search
    
    Vector types generated:
    - position_vectors: Each individual role/project description
    - experience_vector: Concatenated experience across all roles
    - domain_context_vector: Industries and problem spaces
    - personality_vector: Work style and personality signals
    
    For now, returns mock vector data.
    """
    context.log.info(f"Generating vectors for {len(normalized_candidates)} candidates (stub implementation)")
    
    # Mock vector output (actual vectors would be 1536-dimensional)
    vectors = []
    for candidate in normalized_candidates:
        # Generate multiple vector types per candidate
        for vector_type in ["experience", "domain_context", "personality"]:
            vectors.append({
                "candidate_id": candidate["candidate_id"],
                "vector_type": vector_type,
                "vector": [0.1] * 1536,  # Mock 1536-dim vector
                "model_version": "mock-embedding-v1",
            })
    
    context.log.info(f"Generated {len(vectors)} vectors")
    return vectors
