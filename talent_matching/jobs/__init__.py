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

import asyncio
from uuid import UUID

from dagster import (
    Backoff,
    Jitter,
    OpExecutionContext,
    RetryPolicy,
    ScheduleDefinition,
    define_asset_job,
    job,
    op,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

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
from talent_matching.db import get_session
from talent_matching.llm.operations.normalize_skills import (
    assign_skills_to_bags,
    cluster_new_skills,
)
from talent_matching.models.skills import Skill, SkillAlias

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
    tags={"dagster/concurrency_limit": "matchmaking"},
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
    tags={"dagster/concurrency_limit": "matchmaking"},
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


# =============================================================================
# SKILL NORMALIZATION (periodic: assign unprocessed skills to existing bags)
# =============================================================================


@op(description="Load existing alias bags and unprocessed skill names from DB")
def get_existing_bags_and_unprocessed_skills(context: OpExecutionContext) -> dict:
    """Return existing bags (canonical + skill_id + aliases) and unprocessed skill names.

    Processed = skill is canonical (has aliases) or its name is an alias.
    Unprocessed = skill name in skills table that is neither.
    """
    session = get_session()
    # Skills that have at least one alias (canonicals)
    canonicals = (
        session.execute(select(Skill).where(Skill.id.in_(select(SkillAlias.skill_id).distinct())))
        .scalars()
        .all()
    )
    existing_bags = []
    for skill in canonicals:
        aliases = [
            row[0]
            for row in session.execute(
                select(SkillAlias.alias).where(SkillAlias.skill_id == skill.id)
            ).all()
        ]
        existing_bags.append(
            {
                "canonical": skill.name,
                "skill_id": str(skill.id),
                "aliases": aliases,
            }
        )

    # Unprocessed: skills that are not a canonical and whose name is not an alias
    alias_names = {row[0] for row in session.execute(select(SkillAlias.alias)).all()}
    canonical_ids = {s.id for s in canonicals}
    unprocessed = (
        session.execute(select(Skill.name).where(Skill.id.not_in(canonical_ids))).scalars().all()
    )
    unprocessed_names = sorted({name for name in unprocessed if name not in alias_names})
    session.close()

    context.log.info(
        f"Found {len(existing_bags)} existing bags and {len(unprocessed_names)} unprocessed skill names"
    )
    return {
        "existing_bags": existing_bags,
        "unprocessed_names": unprocessed_names,
    }


@op(
    required_resource_keys={"openrouter"},
    tags={"dagster/concurrency_key": "openrouter_api"},
    description="Assign unprocessed skill names to existing bags via LLM",
)
def assign_unprocessed_skills_to_bags(context: OpExecutionContext, data: dict) -> dict:
    """Call LLM to assign each unprocessed name to an existing canonical or new_groups."""
    existing_bags = data["existing_bags"]
    unprocessed_names = data["unprocessed_names"]
    if not unprocessed_names:
        context.log.info("No unprocessed names; skipping LLM")
        return {"assignments": [], "new_groups": [], "existing_bags": existing_bags}

    # Pass bags without skill_id to LLM (not needed for prompt)
    bags_for_prompt = [
        {"canonical": b["canonical"], "aliases": b["aliases"]} for b in existing_bags
    ]
    result = asyncio.run(
        assign_skills_to_bags(
            context.resources.openrouter,
            bags_for_prompt,
            unprocessed_names,
            dagster_log=context.log,
        )
    )
    result["existing_bags"] = existing_bags
    context.log.info(
        f"LLM returned {len(result['assignments'])} assignments and "
        f"{len(result['new_groups'])} new_groups"
    )
    return result


@op(
    required_resource_keys={"openrouter"},
    tags={"dagster/concurrency_key": "openrouter_api"},
    description="Cluster unmatched skill names (new_groups) into new bags via LLM",
)
def cluster_unmatched_skills(context: OpExecutionContext, llm_result: dict) -> dict:
    """Group new_groups into clusters so new alias bags can be created."""
    new_groups = llm_result.get("new_groups") or []
    if not new_groups:
        context.log.info("No new_groups to cluster; skipping")
        llm_result["clusters"] = []
        return llm_result

    clusters = asyncio.run(
        cluster_new_skills(
            context.resources.openrouter,
            new_groups,
            dagster_log=context.log,
        )
    )
    llm_result["clusters"] = clusters
    multi_alias = [c for c in clusters if c.get("aliases")]
    context.log.info(
        f"Clustered {len(new_groups)} unmatched names into {len(clusters)} groups "
        f"({len(multi_alias)} with aliases, {len(clusters) - len(multi_alias)} singletons)"
    )
    return llm_result


@op(description="Apply assignments and clusters: insert skill_aliases rows, create new bags")
def apply_skill_assignments(context: OpExecutionContext, llm_result: dict) -> dict:
    """Write alias rows for both existing-bag assignments and new clusters."""
    assignments = llm_result.get("assignments") or []
    existing_bags = llm_result.get("existing_bags") or []
    clusters = llm_result.get("clusters") or []
    canonical_to_id = {b["canonical"]: UUID(b["skill_id"]) for b in existing_bags}

    session = get_session()

    # 1. Apply assignments to existing bags
    applied = 0
    for item in assignments:
        skill_name = (item.get("skill_name") or "").strip()
        canonical = (item.get("assign_to_canonical") or "").strip()
        if not skill_name or not canonical:
            continue
        skill_id = canonical_to_id.get(canonical)
        if skill_id is None:
            context.log.warning(
                f"Assignment canonical '{canonical}' not in existing bags; skipping '{skill_name}'"
            )
            continue
        stmt = insert(SkillAlias).values(
            alias=skill_name,
            skill_id=skill_id,
            added_by="llm",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["alias"],
            set_={"skill_id": skill_id, "added_by": "llm"},
        )
        session.execute(stmt)
        applied += 1

    # 2. Create new bags from clusters
    bags_created = 0
    aliases_from_clusters = 0
    for cluster in clusters:
        canonical_name = (cluster.get("canonical") or "").strip()
        aliases = cluster.get("aliases") or []
        if not canonical_name or not aliases:
            continue

        canonical_skill = (
            session.execute(select(Skill).where(func.lower(Skill.name) == canonical_name.lower()))
            .scalars()
            .first()
        )
        if canonical_skill is None:
            context.log.warning(
                f"Cluster canonical '{canonical_name}' not found in skills table; skipping"
            )
            continue

        bags_created += 1
        for alias_name in aliases:
            alias_name = alias_name.strip()
            if not alias_name or alias_name == canonical_name:
                continue
            stmt = insert(SkillAlias).values(
                alias=alias_name,
                skill_id=canonical_skill.id,
                added_by="llm",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["alias"],
                set_={"skill_id": canonical_skill.id, "added_by": "llm"},
            )
            session.execute(stmt)
            aliases_from_clusters += 1

    session.commit()
    session.close()

    context.log.info(
        f"Applied {applied} assignments to existing bags, "
        f"created {bags_created} new bags with {aliases_from_clusters} aliases"
    )
    return {
        "applied": applied,
        "assignments_count": len(assignments),
        "bags_created": bags_created,
        "aliases_from_clusters": aliases_from_clusters,
    }


@job(
    description="Normalize unprocessed skill names into existing alias bags via LLM (run periodically)",
    op_retry_policy=openrouter_retry_policy,
)
def skill_normalization_job():
    """Normalize unprocessed skill names into alias bags.

    Op 1: load existing bags + unprocessed names from DB.
    Op 2: call LLM to assign each unprocessed name to an existing bag or new_groups.
    Op 3: cluster new_groups into new bags via LLM (solves cold-start).
    Op 4: insert skill_aliases for both assignments and new clusters.
    """
    data = get_existing_bags_and_unprocessed_skills()
    llm_result = assign_unprocessed_skills_to_bags(data)
    llm_result_with_clusters = cluster_unmatched_skills(llm_result)
    apply_skill_assignments(llm_result_with_clusters)


skill_normalization_schedule = ScheduleDefinition(
    name="skill_normalization_daily",
    cron_schedule="0 2 * * *",
    job=skill_normalization_job,
    description="Run skill normalization daily at 02:00 UTC",
)


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
    "skill_normalization_job",
    "skill_normalization_schedule",
]
