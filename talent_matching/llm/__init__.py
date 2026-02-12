"""LLM operations for the talent matching pipeline.

This module organizes all LLM prompts and operations, enabling:
- Versioned prompts for staleness tracking
- Easy addition of new LLM operations
- Centralized prompt management

Each operation module exports:
- PROMPT_VERSION: String version to track prompt changes
- The operation function that uses OpenRouterResource
"""

from talent_matching.llm.operations.normalize_cv import (
    PROMPT_VERSION as CV_PROMPT_VERSION,
)
from talent_matching.llm.operations.normalize_cv import (
    NormalizeCVResult,
    normalize_cv,
)
from talent_matching.llm.operations.normalize_job import (
    PROMPT_VERSION as JOB_PROMPT_VERSION,
)
from talent_matching.llm.operations.normalize_job import (
    NormalizeJobResult,
    normalize_job,
)
from talent_matching.llm.operations.score_candidate import (
    PROMPT_VERSION as SCORE_PROMPT_VERSION,
)
from talent_matching.llm.operations.score_candidate import (
    ScoreCandidateResult,
    score_candidate,
)

__all__ = [
    # CV normalization
    "CV_PROMPT_VERSION",
    "NormalizeCVResult",
    "normalize_cv",
    # Job normalization
    "JOB_PROMPT_VERSION",
    "NormalizeJobResult",
    "normalize_job",
    # Candidate scoring
    "SCORE_PROMPT_VERSION",
    "ScoreCandidateResult",
    "score_candidate",
]
