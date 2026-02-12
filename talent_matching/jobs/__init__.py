"""Dagster jobs for the talent matching pipeline.

This module defines executable jobs that appear in the Dagster dashboard:
- sync_airtable_candidates: Fetch and register all Airtable records as partitions
- process_sample_candidates: Process a sample of 20 candidates
- process_all_candidates: Full pipeline for all candidates
"""

from dagster import (
    AssetSelection,
    define_asset_job,
    job,
    op,
    OpExecutionContext,
)

from talent_matching.assets.candidates import (
    airtable_candidates,
    candidate_partitions,
    candidate_vectors,
    normalized_candidates,
    raw_candidates,
)


# =============================================================================
# ASSET JOBS (for partitioned processing)
# =============================================================================

# Job to process a single candidate partition through the full pipeline
candidate_pipeline_job = define_asset_job(
    name="candidate_pipeline",
    description="Process a single candidate through the full pipeline (fetch → store → normalize → vectorize)",
    selection=[
        airtable_candidates,
        raw_candidates,
        normalized_candidates,
        candidate_vectors,
    ],
    partitions_def=candidate_partitions,
)

# Job to only fetch and store raw candidates (no LLM processing)
candidate_ingest_job = define_asset_job(
    name="candidate_ingest",
    description="Fetch and store raw candidate data from Airtable (no normalization)",
    selection=[
        airtable_candidates,
        raw_candidates,
    ],
    partitions_def=candidate_partitions,
)


# =============================================================================
# OPS-BASED JOBS (for non-partitioned operations)
# =============================================================================

@op(required_resource_keys={"airtable"})
def sync_airtable_partitions(context: OpExecutionContext) -> dict:
    """Sync all Airtable record IDs as dynamic partitions.
    
    This op fetches all record IDs from Airtable and registers them
    as dynamic partitions, making them available for processing.
    """
    airtable = context.resources.airtable
    
    context.log.info("Fetching all record IDs from Airtable...")
    all_record_ids = airtable.get_all_record_ids()
    context.log.info(f"Found {len(all_record_ids)} records in Airtable")
    
    # Get existing partitions
    existing_partitions = set(
        context.instance.get_dynamic_partitions(
            partitions_def_name=candidate_partitions.name
        )
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
    
    return {
        "total_records": len(all_record_ids),
        "existing_partitions": len(existing_partitions),
        "new_partitions": len(new_record_ids),
    }


@op(required_resource_keys={"airtable"})
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
    stats = {
        "total": len(candidates),
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
    context.log.info(f"With CV URL:      {stats['has_cv']} ({100*stats['has_cv']/stats['total']:.0f}%)")
    context.log.info(f"With Skills:      {stats['has_skills']} ({100*stats['has_skills']/stats['total']:.0f}%)")
    context.log.info(f"With Summary:     {stats['has_summary']} ({100*stats['has_summary']/stats['total']:.0f}%)")
    context.log.info(f"With LinkedIn:    {stats['has_linkedin']} ({100*stats['has_linkedin']/stats['total']:.0f}%)")
    context.log.info(f"With GitHub:      {stats['has_github']} ({100*stats['has_github']/stats['total']:.0f}%)")
    context.log.info("=" * 60)
    
    return stats


@job(description="Sync all Airtable records as dynamic partitions (no processing)")
def sync_airtable_job():
    """Register all Airtable record IDs as dynamic partitions.
    
    Run this job first to populate the partition list before
    processing candidates through the pipeline.
    """
    sync_airtable_partitions()


@job(description="Fetch and analyze a sample of 20 candidates from Airtable")
def sample_candidates_job():
    """Fetch a sample of candidates for testing and validation.
    
    This job fetches 20 candidates from Airtable and logs
    statistics about data completeness.
    """
    candidates = fetch_sample_candidates()
    log_sample_stats(candidates)


# Export all jobs
__all__ = [
    "candidate_pipeline_job",
    "candidate_ingest_job",
    "sync_airtable_job",
    "sample_candidates_job",
]
