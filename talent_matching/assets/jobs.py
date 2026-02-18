"""Job pipeline and matching assets.

This module defines the asset graph for processing jobs and generating matches:
1. airtable_jobs: Job records fetched from Airtable (partitioned per record)
2. raw_jobs: Resolved job description text (Notion fetch + Airtable mapping), stored in PostgreSQL
3. normalized_jobs: LLM-normalized job requirements + narratives
4. job_vectors: Semantic embeddings (experience, domain, personality, impact, technical, role_description)
5. matches: Computed candidate-job matches (stub; loads from DB when implemented)
"""

import asyncio
from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetIn,
    Config,
    DataVersion,
    DynamicPartitionsDefinition,
    Output,
    asset,
)

from talent_matching.llm.operations.embed_text import embed_text
from talent_matching.llm.operations.normalize_job import (
    PROMPT_VERSION as NORMALIZE_JOB_PROMPT_VERSION,
)
from talent_matching.llm.operations.normalize_job import (
    normalize_job,
)

# Dynamic partition definition for jobs (one partition per Airtable job record ID)
job_partitions = DynamicPartitionsDefinition(name="jobs")


@asset(
    partitions_def=job_partitions,
    description="Single job record fetched from Airtable (jobs table)",
    group_name="jobs",
    required_resource_keys={"airtable_jobs"},
    metadata={"source": "airtable"},
)
def airtable_jobs(context: AssetExecutionContext) -> Output[dict[str, Any]]:
    """Fetch a single job row from Airtable by partition key (Airtable record ID)."""
    record_id = context.partition_key
    context.log.info(f"Fetching job record: {record_id}")

    airtable = context.resources.airtable_jobs
    job_record = airtable.fetch_record_by_id(record_id)

    data_version = job_record.pop("_data_version", None)
    context.log.info(
        f"Fetched job: {job_record.get('company_name', 'Unknown')} / {job_record.get('job_title_raw', 'N/A')}"
    )

    return Output(
        value=job_record,
        data_version=DataVersion(data_version) if data_version else None,
    )


@asset(
    partitions_def=job_partitions,
    ins={"airtable_jobs": AssetIn()},
    description="Raw job data with resolved job description (Notion fetch or text)",
    group_name="jobs",
    io_manager_key="postgres_io",
    required_resource_keys={"notion"},
    metadata={"table": "raw_jobs"},
)
def raw_jobs(
    context: AssetExecutionContext,
    airtable_jobs: dict[str, Any],
) -> dict[str, Any]:
    """Resolve job description from Airtable row (Notion URL or text) and store as RawJob."""
    record_id = context.partition_key
    notion = context.resources.notion
    link = airtable_jobs.get("job_description_link")
    job_description = airtable_jobs.get("job_description_text") or ""

    if link and _is_notion_url(link):
        context.log.info(f"Fetching Notion page for job: {link[:60]}...")
        job_description = (
            notion.fetch_page_content(link) or job_description or "(No content from Notion)"
        )

    payload = {
        "airtable_record_id": record_id,
        "source": "airtable",
        "source_id": record_id,
        "source_url": link or None,
        "job_title": airtable_jobs.get("job_title_raw"),
        "company_name": airtable_jobs.get("company_name"),
        "job_description": job_description or "(No description provided)",
        "company_website_url": airtable_jobs.get("company_website_url"),
        "experience_level_raw": None,
        "location_raw": None,
        "work_setup_raw": None,
        "status_raw": None,
        "job_category_raw": airtable_jobs.get("job_title_raw"),
        "x_url": airtable_jobs.get("x_url"),
    }
    context.log.info(f"Prepared raw job {record_id} (description length: {len(job_description)})")
    return payload


def _is_notion_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return "notion.site" in url or "notion.so" in url


@asset(
    partitions_def=job_partitions,
    ins={"raw_jobs": AssetIn()},
    description="LLM-normalized job requirements with structured fields and narratives",
    group_name="jobs",
    io_manager_key="postgres_io",
    required_resource_keys={"openrouter"},
    code_version="2.0.0",  # v2: real normalize_job LLM + narratives
    metadata={
        "table": "normalized_jobs",
        "llm_operation": "normalize_job",
    },
    op_tags={"dagster/concurrency_key": "openrouter_api"},
)
def normalized_jobs(
    context: AssetExecutionContext,
    raw_jobs: dict[str, Any],
) -> dict[str, Any]:
    """Normalize raw job description for this partition via LLM; persist to normalized_jobs."""
    record_id = context.partition_key
    job_description = (raw_jobs.get("job_description") or "").strip()
    if not job_description or len(job_description) < 50:
        context.log.warning(f"No meaningful job description for {record_id}; skipping LLM")
        return {
            "airtable_record_id": record_id,
            "title": raw_jobs.get("job_title") or "Unknown",
            "company_name": raw_jobs.get("company_name") or "Unknown",
            "job_description": job_description or "(No description)",
            "normalized_json": None,
            "prompt_version": None,
            "model_version": None,
            "narratives": {},
        }
    openrouter = context.resources.openrouter
    result = asyncio.run(normalize_job(openrouter, job_description))
    data = result.data
    context.add_output_metadata(
        {
            "llm_cost_usd": result.cost_usd,
            "llm_tokens_input": result.input_tokens,
            "llm_tokens_output": result.output_tokens,
            "llm_model": result.model,
        }
    )
    payload = {
        "airtable_record_id": record_id,
        **data,
        "normalized_json": data,
        "prompt_version": NORMALIZE_JOB_PROMPT_VERSION,
        "model_version": result.model,
    }
    return payload


# Vector types for job narratives (aligned with candidate vector types for matching)
JOB_NARRATIVE_VECTOR_TYPES = [
    "experience",
    "domain",
    "personality",
    "impact",
    "technical",
    "role_description",
]


@asset(
    partitions_def=job_partitions,
    ins={"normalized_jobs": AssetIn()},
    description="Semantic embeddings for job narratives (experience, domain, personality, impact, technical, role_description)",
    group_name="jobs",
    required_resource_keys={"openrouter"},
    io_manager_key="pgvector_io",
    code_version="2.0.0",  # v2: narrative-based, same vector_type as candidates
    op_tags={"dagster/concurrency_key": "openrouter_api"},
    metadata={
        "table": "job_vectors",
        "vector_types": JOB_NARRATIVE_VECTOR_TYPES,
    },
)
def job_vectors(
    context: AssetExecutionContext,
    normalized_jobs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate semantic embeddings from normalized job narratives for matching.

    Builds six vectors from narrative columns (fallback to normalized_json.narratives):
    experience, domain, personality, impact, technical, role_description.
    Uses same embedding model as candidate_vectors for like-for-like similarity.
    """
    record_id = context.partition_key
    openrouter = context.resources.openrouter

    narratives = normalized_jobs.get("narratives") or {}

    # Fallback to top-level narrative_* if present (e.g. from DB load)
    def _text(key: str, narrative_key: str) -> str:
        if key == "role_description":
            return (
                normalized_jobs.get("narrative_role")
                or narratives.get("role")
                or "No role description."
            )
        return (
            normalized_jobs.get(f"narrative_{key}") or narratives.get(key) or f"No {key} narrative."
        )

    texts_to_embed = [
        _text("experience", "experience"),
        _text("domain", "domain"),
        _text("personality", "personality"),
        _text("impact", "impact"),
        _text("technical", "technical"),
        _text("role_description", "role"),
    ]
    vector_types = list(JOB_NARRATIVE_VECTOR_TYPES)

    result = asyncio.run(embed_text(openrouter, texts_to_embed))
    context.add_output_metadata(
        {
            "embedding_cost_usd": result.cost_usd,
            "embedding_tokens": result.input_tokens,
            "embedding_dimensions": result.dimensions,
            "embedding_model": result.model,
            "vectors_generated": len(result.embeddings),
        }
    )

    vectors = []
    for i, vt in enumerate(vector_types):
        vectors.append(
            {
                "airtable_record_id": record_id,
                "vector_type": vt,
                "vector": result.embeddings[i],
                "model_version": result.model,
            }
        )
    return vectors


# Airtable column names for write-back (subset of normalized fields)
AIRTABLE_JOBS_WRITEBACK_FIELDS = {
    "title": "Hiring Job Title",
    "company_name": "Company",
}


class AirtableJobSyncConfig(Config):
    """Run config for airtable_job_sync. Set sync_to_airtable=True to write back to Airtable."""

    sync_to_airtable: bool = False


@asset(
    partitions_def=job_partitions,
    ins={"normalized_jobs": AssetIn()},
    description="Optional: write back parsed job fields to the Airtable row (controlled by run config)",
    group_name="jobs",
    required_resource_keys={"airtable_jobs"},
    metadata={"optional_sync": True},
)
def airtable_job_sync(
    context: AssetExecutionContext,
    config: AirtableJobSyncConfig,
    normalized_jobs: dict[str, Any],
) -> dict[str, Any]:
    """Write a subset of normalized job fields back to the Airtable record.

    Only performs the write when run config sync_to_airtable is True (default False).
    Fills Airtable columns (e.g. Hiring Job Title, Company) from LLM output.
    """
    record_id = context.partition_key
    if not config.sync_to_airtable:
        context.log.info(f"Sync to Airtable disabled for {record_id} (sync_to_airtable=False)")
        return {"airtable_record_id": record_id, "synced": False, "skipped": True, "fields": {}}
    airtable = context.resources.airtable_jobs
    fields_to_patch: dict[str, Any] = {}
    for our_key, airtable_col in AIRTABLE_JOBS_WRITEBACK_FIELDS.items():
        value = normalized_jobs.get(our_key)
        if value is not None and str(value).strip():
            fields_to_patch[airtable_col] = value.strip() if isinstance(value, str) else value
    if not fields_to_patch:
        context.log.info(f"No fields to sync for job {record_id}")
        return {"airtable_record_id": record_id, "synced": False, "fields": {}}
    airtable.update_record(record_id, fields_to_patch)
    context.log.info(f"Synced {record_id}: {list(fields_to_patch.keys())}")
    return {"airtable_record_id": record_id, "synced": True, "fields": fields_to_patch}


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
            match_results.append(
                {
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
                }
            )

    context.log.info(f"Computed {len(match_results)} matches")
    return match_results
