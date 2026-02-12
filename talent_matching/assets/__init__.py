"""Dagster assets for the talent matching pipeline."""

from talent_matching.assets.candidates import (
    candidate_vectors,
    normalized_candidates,
    raw_candidates,
)
from talent_matching.assets.jobs import (
    job_vectors,
    matches,
    normalized_jobs,
    raw_jobs,
)
from talent_matching.assets.social import (
    candidate_linkedin_metrics,
    candidate_twitter_metrics,
    social_followers_aggregation,
)

__all__ = [
    # Candidate assets
    "raw_candidates",
    "normalized_candidates",
    "candidate_vectors",
    # Job assets
    "raw_jobs",
    "normalized_jobs",
    "job_vectors",
    # Social metrics
    "candidate_twitter_metrics",
    "candidate_linkedin_metrics",
    "social_followers_aggregation",
    # Matching
    "matches",
]
