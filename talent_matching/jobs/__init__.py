"""Dagster jobs for the talent matching pipeline.

Jobs available in the Dagster dashboard:

ASSET JOBS (for materializing assets):
- candidate_pipeline: Process candidates through full pipeline (partitioned)
- candidate_ingest: Fetch and store raw candidates only (no LLM)
- upload_normalized_to_airtable_job: Upload normalized candidate data to Airtable (N) columns only (partitioned)

OPS JOBS (for operational tasks):
- sync_airtable_candidates_job: Register Airtable candidate records as dynamic partitions
- sync_airtable_jobs_job: Register Airtable job records as dynamic partitions
- sample_candidates_job: Fetch 20 candidates and log data quality stats

USAGE:
1. Run sync_airtable_candidates_job to register candidate partitions from Airtable
2. Go to Jobs → candidate_pipeline → Backfill
3. Select partitions (all, or first N for testing) and launch
"""

from dagster import (
    Backoff,
    Jitter,
    OpExecutionContext,
    RetryPolicy,
    define_asset_job,
    job,
    op,
)

from talent_matching.assets.candidates import (
    airtable_candidate_sync,
    airtable_candidates,
    candidate_partitions,
    candidate_role_fitness,
    candidate_vectors,
    normalized_candidates,
    raw_candidates,
)
from talent_matching.assets.jobs import (
    airtable_job_sync,
    airtable_jobs,
    job_partitions,
    job_vectors,
    matches,
    normalized_jobs,
    raw_jobs,
)

# =============================================================================
# ASSET JOBS (for partitioned processing)
# =============================================================================

# Retry policy for API calls (rate limits, transient errors)
# Uses exponential backoff: 1s, 2s, 4s between retries
openrouter_retry_policy = RetryPolicy(
    max_retries=3,
    delay=1,  # 1 second base delay
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.PLUS_MINUS,  # Add randomness to avoid thundering herd
)

candidate_pipeline_job = define_asset_job(
    name="candidate_pipeline",
    description=(
        "Process candidates through the full pipeline: "
        "fetch → store → normalize (LLM) → vectorize → role fitness → Airtable write-back. "
        "Use Backfill to select partitions."
    ),
    selection=[
        airtable_candidates,
        raw_candidates,
        normalized_candidates,
        candidate_vectors,
        candidate_role_fitness,
        airtable_candidate_sync,
    ],
    partitions_def=candidate_partitions,
    # Retry on failures (rate limits, transient API errors)
    op_retry_policy=openrouter_retry_policy,
)

candidate_ingest_job = define_asset_job(
    name="candidate_ingest",
    description=(
        "Fetch and store raw candidate data from Airtable (no LLM normalization). "
        "Use this for initial data loading before running normalization."
    ),
    selection=[
        airtable_candidates,
        raw_candidates,
    ],
    partitions_def=candidate_partitions,
)

upload_normalized_to_airtable_job = define_asset_job(
    name="upload_normalized_to_airtable",
    description=(
        "Upload normalized candidate data to Airtable (N)-prefixed columns only. "
        "Uses already-materialized normalized_candidates; does not re-run normalization. "
        "Use Backfill to select which candidate partitions to sync."
    ),
    selection=[airtable_candidate_sync],
    partitions_def=candidate_partitions,
)

job_pipeline_job = define_asset_job(
    name="job_pipeline",
    description=("Process jobs: fetch → raw → normalize (LLM) → vectorize → Airtable write-back."),
    selection=[
        airtable_jobs,
        raw_jobs,
        normalized_jobs,
        job_vectors,
        airtable_job_sync,
    ],
    partitions_def=job_partitions,
    op_retry_policy=openrouter_retry_policy,
)

job_ingest_job = define_asset_job(
    name="job_ingest",
    description=(
        "Fetch and store raw job data from Airtable (Notion fetch, no LLM). "
        "Use for initial load before running normalization."
    ),
    selection=[
        airtable_jobs,
        raw_jobs,
    ],
    partitions_def=job_partitions,
)

matchmaking_job = define_asset_job(
    name="matchmaking",
    description=(
        "Compute job–candidate matches (scoring) per job. One partition per job; run "
        "after job_pipeline and candidate_pipeline backfills. Backfill to select job partitions."
    ),
    selection=[matches],
    partitions_def=job_partitions,
)

upload_normalized_jobs_to_airtable_job = define_asset_job(
    name="upload_normalized_jobs_to_airtable",
    description=(
        "Upload normalized job data to Airtable (N)-prefixed columns + set Start Matchmaking=false. "
        "Uses already-materialized normalized_jobs; does not re-run normalization. "
        "Use Backfill to select which job partitions to sync."
    ),
    selection=[airtable_job_sync],
    partitions_def=job_partitions,
)

matchmaking_with_feedback_job = define_asset_job(
    name="matchmaking_with_feedback",
    description=(
        "Re-generate job vectors and compute matches after human-edited (N) fields "
        "have been synced from Airtable to DB. Triggered by the airtable_job_matchmaking_sensor."
    ),
    selection=[job_vectors, matches],
    partitions_def=job_partitions,
    op_retry_policy=openrouter_retry_policy,
)


# =============================================================================
# OPS JOBS (for operational tasks)
# =============================================================================


@op(required_resource_keys={"airtable"}, tags={"dagster/concurrency_key": "airtable_api"})
def sync_airtable_candidates_partitions(context: OpExecutionContext) -> dict:
    """Sync all Airtable candidate record IDs as dynamic partitions.

    This op fetches all record IDs from the candidates table and registers them
    as dynamic partitions, making them available for candidate_pipeline.
    """
    airtable = context.resources.airtable

    context.log.info("Fetching all record IDs from Airtable...")
    all_record_ids = airtable.get_all_record_ids()
    context.log.info(f"Found {len(all_record_ids)} records in Airtable")

    # Get existing partitions
    existing_partitions = set(
        context.instance.get_dynamic_partitions(partitions_def_name=candidate_partitions.name)
    )
    context.log.info(f"Existing partitions: {len(existing_partitions)}")

    # Find new records
    new_record_ids = set(all_record_ids) - existing_partitions

    if new_record_ids:
        context.log.info(f"Adding {len(new_record_ids)} new partitions...")
        context.instance.add_dynamic_partitions(
            partitions_def_name=candidate_partitions.name,
            partition_keys=list(new_record_ids),
        )
    else:
        context.log.info("No new partitions to add")

    context.log.info("")
    context.log.info("Next: Go to Jobs → candidate_pipeline → Backfill to process partitions")

    return {
        "total_records": len(all_record_ids),
        "existing_partitions": len(existing_partitions),
        "new_partitions": len(new_record_ids),
    }


@op(required_resource_keys={"airtable"}, tags={"dagster/concurrency_key": "airtable_api"})
def fetch_sample_candidates(context: OpExecutionContext, sample_size: int = 20) -> list:
    """Fetch a sample of candidates from Airtable for testing."""
    airtable = context.resources.airtable

    context.log.info(f"Fetching {sample_size} sample candidates from Airtable...")
    all_records = airtable.fetch_all_records()
    sample = all_records[:sample_size]

    context.log.info(f"Fetched {len(sample)} candidates")
    for i, record in enumerate(sample[:5]):
        context.log.info(f"  {i+1}. {record.get('full_name', 'Unknown')}")
    if len(sample) > 5:
        context.log.info(f"  ... and {len(sample) - 5} more")

    return sample


@op
def log_sample_stats(context: OpExecutionContext, candidates: list) -> dict:
    """Log statistics about the sample candidates."""
    total = len(candidates)
    if total == 0:
        context.log.warning("No candidates to analyze")
        return {"total": 0}

    stats = {
        "total": total,
        "has_cv": sum(1 for c in candidates if c.get("cv_url")),
        "has_skills": sum(1 for c in candidates if c.get("skills_raw")),
        "has_summary": sum(1 for c in candidates if c.get("professional_summary")),
        "has_linkedin": sum(1 for c in candidates if c.get("linkedin_url")),
        "has_github": sum(1 for c in candidates if c.get("github_url")),
    }

    context.log.info("=" * 60)
    context.log.info("SAMPLE STATISTICS")
    context.log.info("=" * 60)
    context.log.info(f"Total candidates: {stats['total']}")
    context.log.info(f"With CV URL:      {stats['has_cv']} ({100*stats['has_cv']//total}%)")
    context.log.info(f"With Skills:      {stats['has_skills']} ({100*stats['has_skills']//total}%)")
    context.log.info(
        f"With Summary:     {stats['has_summary']} ({100*stats['has_summary']//total}%)"
    )
    context.log.info(
        f"With LinkedIn:    {stats['has_linkedin']} ({100*stats['has_linkedin']//total}%)"
    )
    context.log.info(f"With GitHub:      {stats['has_github']} ({100*stats['has_github']//total}%)")
    context.log.info("=" * 60)

    return stats


@job(description="Sync Airtable candidate records as dynamic partitions")
def sync_airtable_candidates_job():
    """Register all Airtable candidate record IDs as dynamic partitions.

    Run this job first to populate the partition list, then use
    candidate_pipeline with Backfill to process them.
    """
    sync_airtable_candidates_partitions()


@op(required_resource_keys={"airtable_jobs"}, tags={"dagster/concurrency_key": "airtable_api"})
def sync_airtable_jobs_partitions(context: OpExecutionContext) -> dict:
    """Sync all Airtable job record IDs as dynamic partitions (jobs table)."""
    airtable_jobs_resource = context.resources.airtable_jobs
    context.log.info("Fetching all record IDs from Airtable jobs table...")
    all_record_ids = airtable_jobs_resource.get_all_record_ids()
    context.log.info(f"Found {len(all_record_ids)} job records")

    existing = set(context.instance.get_dynamic_partitions(partitions_def_name=job_partitions.name))
    new_record_ids = set(all_record_ids) - existing
    if new_record_ids:
        context.instance.add_dynamic_partitions(
            partitions_def_name=job_partitions.name,
            partition_keys=list(new_record_ids),
        )
        context.log.info(f"Added {len(new_record_ids)} new job partitions")
    context.log.info("Next: Go to Jobs → job_pipeline → Backfill to process job partitions")
    return {
        "total_records": len(all_record_ids),
        "existing_partitions": len(existing),
        "new_partitions": len(new_record_ids),
    }


@job(description="Sync Airtable job records as dynamic partitions")
def sync_airtable_jobs_job():
    """Register all Airtable job record IDs (jobs table) as dynamic partitions.

    Run before job_pipeline Backfill to process jobs.
    """
    sync_airtable_jobs_partitions()


@job(description="Fetch 20 candidates and log data quality statistics")
def sample_candidates_job():
    """Fetch a sample of candidates and analyze data completeness.

    This job fetches 20 candidates from Airtable and logs
    statistics about data availability (CV, skills, etc.).
    Does NOT run the pipeline - just for data exploration.
    """
    candidates = fetch_sample_candidates()
    log_sample_stats(candidates)


# Export all jobs
__all__ = [
    "candidate_pipeline_job",
    "candidate_ingest_job",
    "upload_normalized_to_airtable_job",
    "job_pipeline_job",
    "job_ingest_job",
    "matchmaking_job",
    "upload_normalized_jobs_to_airtable_job",
    "matchmaking_with_feedback_job",
    "sync_airtable_candidates_job",
    "sync_airtable_jobs_job",
    "sample_candidates_job",
]
