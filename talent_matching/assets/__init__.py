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

__all__ = [
    # Candidate assets
    "raw_candidates",
    "normalized_candidates",
    "candidate_vectors",
    # Job assets
    "raw_jobs",
    "normalized_jobs",
    "job_vectors",
    # Matching
    "matches",
]
