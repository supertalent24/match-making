"""Job pipeline and matching assets.

This module defines the asset graph for processing jobs and generating matches:
1. raw_jobs: Ingested job descriptions
2. normalized_jobs: LLM-normalized job requirements
3. job_vectors: Semantic embeddings for jobs
4. matches: Computed candidate-job matches

These are currently stub implementations that establish the asset structure.
The actual processing logic will be implemented in subsequent phases.
"""

from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetIn,
    asset,
)

# Import prompt version for metadata tracking (auditing which prompts were used)
from talent_matching.llm import JOB_PROMPT_VERSION as _JOB_PROMPT_VERSION


@asset(
    description="Raw job descriptions ingested from various sources",
    group_name="jobs",
    metadata={
        "table": "raw_jobs",
    },
)
def raw_jobs(context: AssetExecutionContext) -> list[dict[str, Any]]:
    """Ingest raw job descriptions.
    
    In the full implementation, this asset would:
    1. Read job postings from configured sources
    2. Associate with company information
    3. Store raw text for processing
    
    For now, returns mock data to establish the pipeline structure.
    """
    context.log.info("Ingesting raw job descriptions (stub implementation)")
    
    # Mock job descriptions
    mock_jobs = [
        {
            "id": "job-001",
            "company_id": "company-001",
            "raw_description": """
                Senior Backend Engineer - DeFi Protocol
                
                We're looking for an experienced backend engineer to join our DeFi team.
                
                Requirements:
                - 5+ years of software engineering experience
                - Strong Rust or Go experience
                - Understanding of blockchain technology
                - Experience with distributed systems
                
                Nice to have:
                - Solana development experience
                - Previous DeFi/crypto experience
            """,
        },
        {
            "id": "job-002",
            "company_id": "company-002",
            "raw_description": """
                Full Stack Developer - NFT Marketplace
                
                Join our team building the next generation NFT platform.
                
                Requirements:
                - 3+ years of full stack development
                - React/TypeScript expertise
                - Node.js backend experience
                
                Nice to have:
                - Web3 experience
                - Smart contract knowledge
            """,
        },
    ]
    
    context.log.info(f"Ingested {len(mock_jobs)} raw jobs")
    return mock_jobs


@asset(
    ins={"raw_jobs": AssetIn()},
    description="LLM-normalized job requirements with structured fields",
    group_name="jobs",
    code_version="1.0.0",  # Bump when prompt or normalization logic changes
    metadata={
        "table": "normalized_jobs",
        "llm_operation": "normalize_job",
    },
)
def normalized_jobs(
    context: AssetExecutionContext,
    raw_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize raw job descriptions into structured requirements using LLM.

    In the full implementation, this asset would:
    1. Send job descriptions to the LLM resource for normalization
    2. Extract must-have skills, nice-to-have skills, experience requirements
    3. Identify domain context and team culture signals

    The code_version in the decorator tracks when this asset's logic changes.
    Bump it when modifying prompt handling or normalization logic.

    TODO: Add openrouter resource and use normalize_job() from talent_matching.llm

    For now, returns mock normalized data.
    """
    context.log.info(f"Normalizing {len(raw_jobs)} jobs (stub implementation)")

    # Mock normalized output
    normalized = []
    for raw in raw_jobs:
        normalized.append({
            "job_id": raw["id"],
            "normalized_json": {
                "title": "Senior Backend Engineer",
                "seniority_level": "senior",
                "employment_type": "full-time",
                "requirements": {
                    "must_have_skills": ["Rust", "Go", "Distributed Systems"],
                    "nice_to_have_skills": ["Solana", "DeFi"],
                    "years_of_experience_min": 5,
                    "domain_experience": ["DeFi", "Blockchain"],
                },
                "tech_stack": ["Rust", "Go", "PostgreSQL"],
            },
            "prompt_version": _JOB_PROMPT_VERSION,
            "model_version": "mock-v1",
        })

    context.log.info(f"Normalized {len(normalized)} job descriptions")
    return normalized


@asset(
    ins={"normalized_jobs": AssetIn()},
    description="Semantic embeddings for job descriptions (role, domain, culture)",
    group_name="jobs",
    metadata={
        "table": "job_vectors",
        "vector_types": ["role_description", "domain_context", "culture"],
    },
)
def job_vectors(
    context: AssetExecutionContext,
    normalized_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate semantic embeddings for job descriptions.
    
    In the full implementation, this asset would:
    1. Extract text sections for each vector type
    2. Generate embeddings using the embedding resource
    3. Store vectors for similarity matching against candidates
    
    Vector types generated:
    - role_description_vector: Full job description and responsibilities
    - domain_context_vector: Product domain and industry
    - culture_vector: Company culture and team working style
    
    For now, returns mock vector data.
    """
    context.log.info(f"Generating vectors for {len(normalized_jobs)} jobs (stub implementation)")
    
    # Mock vector output
    vectors = []
    for job in normalized_jobs:
        for vector_type in ["role_description", "domain_context", "culture"]:
            vectors.append({
                "job_id": job["job_id"],
                "vector_type": vector_type,
                "vector": [0.1] * 1536,  # Mock 1536-dim vector
                "model_version": "mock-embedding-v1",
            })
    
    context.log.info(f"Generated {len(vectors)} job vectors")
    return vectors


@asset(
    ins={
        "normalized_candidates": AssetIn(key=["normalized_candidates"]),
        "candidate_vectors": AssetIn(key=["candidate_vectors"]),
        "normalized_jobs": AssetIn(),
        "job_vectors": AssetIn(),
    },
    description="Computed matches between jobs and candidates with scores",
    group_name="matching",
    code_version="1.0.0",  # Bump when scoring logic or weights change
    metadata={
        "table": "matches",
        "scoring_weights": {"keyword": 0.4, "vector": 0.6},
    },
)
def matches(
    context: AssetExecutionContext,
    normalized_candidates: list[dict[str, Any]],
    candidate_vectors: list[dict[str, Any]],
    normalized_jobs: list[dict[str, Any]],
    job_vectors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute matches between jobs and candidates.
    
    In the full implementation, this asset would:
    1. Apply hard filters (years of experience, must-have skills)
    2. Calculate keyword match score (40% weight)
    3. Calculate vector similarity score (60% weight)
    4. Rank candidates and return top 50 per job
    
    Scoring formula:
    - keyword_score = (must_have_coverage * 0.6) + (nice_to_have_coverage * 0.4)
    - vector_score = weighted cosine similarity across vector types
    - final_score = (keyword_score * 0.4) + (vector_score * 0.6)
    
    For now, returns mock match data.
    """
    context.log.info("Computing matches (stub implementation)")
    context.log.info(f"  Candidates: {len(normalized_candidates)}")
    context.log.info(f"  Candidate vectors: {len(candidate_vectors)}")
    context.log.info(f"  Jobs: {len(normalized_jobs)}")
    context.log.info(f"  Job vectors: {len(job_vectors)}")
    
    # Mock match output
    match_results = []
    for job in normalized_jobs:
        for candidate in normalized_candidates:
            match_results.append({
                "job_id": job["job_id"],
                "candidate_id": candidate["candidate_id"],
                "match_score": 0.75,  # Mock score
                "keyword_score": 0.70,
                "vector_score": 0.78,
                "breakdown": {
                    "must_have_coverage": 0.80,
                    "nice_to_have_coverage": 0.50,
                    "experience_similarity": 0.85,
                    "domain_similarity": 0.70,
                },
            })
    
    context.log.info(f"Computed {len(match_results)} matches")
    return match_results
