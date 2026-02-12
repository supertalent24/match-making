"""Dagster jobs for the talent matching pipeline.

This module defines executable jobs that appear in the Dagster dashboard:
- sync_airtable_candidates: Fetch and register all Airtable records as partitions
- process_sample_candidates: Process a sample of 20 candidates
- process_all_candidates: Full pipeline for all candidates
- full_pipeline_job: Run complete pipeline for all candidates
- test_pipeline_20_job: Test run with 20 candidates
"""

from dagster import (
    OpExecutionContext,
    define_asset_job,
    job,
    op,
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
    context.log.info(
        f"With CV URL:      {stats['has_cv']} ({100*stats['has_cv']/stats['total']:.0f}%)"
    )
    context.log.info(
        f"With Skills:      {stats['has_skills']} ({100*stats['has_skills']/stats['total']:.0f}%)"
    )
    context.log.info(
        f"With Summary:     {stats['has_summary']} ({100*stats['has_summary']/stats['total']:.0f}%)"
    )
    context.log.info(
        f"With LinkedIn:    {stats['has_linkedin']} ({100*stats['has_linkedin']/stats['total']:.0f}%)"
    )
    context.log.info(
        f"With GitHub:      {stats['has_github']} ({100*stats['has_github']/stats['total']:.0f}%)"
    )
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


# =============================================================================
# BATCH PROCESSING JOBS
# =============================================================================


@op(required_resource_keys={"airtable"})
def sync_and_get_all_partitions(context: OpExecutionContext) -> list[str]:
    """Sync Airtable records and return all partition keys."""
    airtable = context.resources.airtable

    context.log.info("Fetching all record IDs from Airtable...")
    all_record_ids = airtable.get_all_record_ids()
    context.log.info(f"Found {len(all_record_ids)} records in Airtable")

    # Get existing partitions
    existing_partitions = set(
        context.instance.get_dynamic_partitions(partitions_def_name=candidate_partitions.name)
    )

    # Find new records
    new_record_ids = set(all_record_ids) - existing_partitions

    if new_record_ids:
        context.log.info(f"Adding {len(new_record_ids)} new partitions...")
        context.instance.add_dynamic_partitions(
            partitions_def_name=candidate_partitions.name,
            partition_keys=list(new_record_ids),
        )

    return all_record_ids


@op(required_resource_keys={"airtable"})
def sync_and_get_sample_partitions(context: OpExecutionContext) -> list[str]:
    """Sync Airtable records and return first 20 partition keys for testing."""
    airtable = context.resources.airtable

    context.log.info("Fetching record IDs from Airtable for test run...")
    all_record_ids = airtable.get_all_record_ids()
    sample_ids = all_record_ids[:20]
    context.log.info(f"Selected {len(sample_ids)} records for test run")

    # Get existing partitions
    existing_partitions = set(
        context.instance.get_dynamic_partitions(partitions_def_name=candidate_partitions.name)
    )

    # Find new records in sample
    new_record_ids = set(sample_ids) - existing_partitions

    if new_record_ids:
        context.log.info(f"Adding {len(new_record_ids)} new partitions...")
        context.instance.add_dynamic_partitions(
            partitions_def_name=candidate_partitions.name,
            partition_keys=list(new_record_ids),
        )

    return sample_ids


@op
def submit_pipeline_runs(context: OpExecutionContext, partition_keys: list[str]) -> dict:
    """Submit pipeline runs for each partition key.

    This op queues asset materializations for the candidate pipeline.
    """
    context.log.info(f"Submitting pipeline runs for {len(partition_keys)} partitions...")

    submitted = 0
    for partition_key in partition_keys:
        context.log.info(f"  Queuing: {partition_key}")

        # Submit a run request for the candidate_pipeline_job
        context.instance.submit_run(
            run_id=None,
            pipeline_name="candidate_pipeline",
            run_config={},
            mode=None,
            solids_to_execute=None,
            step_keys_to_execute=None,
            tags={
                "dagster/partition": partition_key,
                "source": "full_pipeline_job",
            },
        )
        submitted += 1

    context.log.info(f"Submitted {submitted} pipeline runs")
    return {
        "submitted": submitted,
        "partition_keys": partition_keys,
    }


@op
def log_pipeline_partitions(context: OpExecutionContext, partition_keys: list[str]) -> dict:
    """Log the partitions synced and ready for processing."""
    context.log.info("=" * 70)
    context.log.info("PIPELINE PARTITIONS READY FOR PROCESSING")
    context.log.info("=" * 70)
    context.log.info(f"Total partitions synced: {len(partition_keys)}")
    context.log.info("")
    context.log.info("Partition keys:")
    for i, key in enumerate(partition_keys[:10]):
        context.log.info(f"  {i+1}. {key}")
    if len(partition_keys) > 10:
        context.log.info(f"  ... and {len(partition_keys) - 10} more")
    context.log.info("=" * 70)
    context.log.info("")
    context.log.info("Next step: Run candidate_pipeline_job with these partitions")
    context.log.info("  In the Dagster UI: Jobs → candidate_pipeline → Launchpad")
    context.log.info("  Select partitions and click 'Launch Run'")
    context.log.info("")

    return {
        "total_partitions": len(partition_keys),
        "partition_keys": partition_keys,
    }


@op
def generate_run_commands(context: OpExecutionContext, partition_keys: list[str]) -> str:
    """Generate CLI commands to run the pipeline for each partition."""
    context.log.info("=" * 70)
    context.log.info("CLI COMMANDS FOR BATCH PROCESSING")
    context.log.info("=" * 70)
    context.log.info("")
    context.log.info("Run these commands to process all partitions:")
    context.log.info("")

    # Generate a single command that processes all partitions
    partitions_str = ",".join(partition_keys)
    cmd = f"dagster job backfill -j candidate_pipeline --partitions {partitions_str}"

    context.log.info("Option 1: Backfill all partitions at once")
    context.log.info(f"  {cmd}")
    context.log.info("")

    context.log.info("Option 2: Process one at a time")
    for i, key in enumerate(partition_keys[:5]):
        context.log.info(f"  dagster job execute -j candidate_pipeline --partition {key}")
    if len(partition_keys) > 5:
        context.log.info(f"  # ... {len(partition_keys) - 5} more partitions")

    context.log.info("")
    context.log.info("=" * 70)

    return partitions_str


@job(
    description="Full candidate pipeline: sync ALL partitions and generate backfill commands",
    tags={"pipeline": "candidates", "scope": "full"},
)
def full_pipeline_job():
    """Prepare the complete candidate pipeline for ALL candidates.

    This job:
    1. Syncs all Airtable records as dynamic partitions
    2. Logs partition info and generates CLI commands

    After running, use the generated backfill command or Dagster UI
    to materialize candidate_pipeline_job for all partitions.
    """
    partition_keys = sync_and_get_all_partitions()
    log_pipeline_partitions(partition_keys)
    generate_run_commands(partition_keys)


@job(
    description="Test pipeline: sync 20 candidates and generate run commands",
    tags={"pipeline": "candidates", "scope": "test", "sample_size": "20"},
)
def test_pipeline_20_job():
    """Test run preparation for 20 candidates.

    This job:
    1. Syncs the first 20 Airtable records as partitions
    2. Logs partition info and generates CLI commands

    Use this for testing LLM normalization costs and pipeline behavior
    before running on the full dataset.

    After running, execute the backfill command or use the Dagster UI
    to process these 20 partitions through candidate_pipeline_job.
    """
    partition_keys = sync_and_get_sample_partitions()
    log_pipeline_partitions(partition_keys)
    generate_run_commands(partition_keys)


# Export all jobs
__all__ = [
    "candidate_pipeline_job",
    "candidate_ingest_job",
    "sync_airtable_job",
    "sample_candidates_job",
    "full_pipeline_job",
    "test_pipeline_20_job",
]
