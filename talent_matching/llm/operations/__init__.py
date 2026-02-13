"""LLM operation modules.

Each module contains:
- PROMPT_VERSION: Bump when prompt changes (triggers asset staleness)
- SYSTEM_PROMPT: The prompt template
- An async function that performs the operation
"""

from talent_matching.llm.operations.extract_pdf import (
    PROMPT_VERSION as PDF_PROMPT_VERSION,
)
from talent_matching.llm.operations.extract_pdf import (
    PDFEngine,
    extract_pdf_from_url,
    extract_pdf_text,
)
from talent_matching.llm.operations.normalize_cv import (
    PROMPT_VERSION as CV_PROMPT_VERSION,
)
from talent_matching.llm.operations.normalize_cv import (
    normalize_cv,
)
from talent_matching.llm.operations.normalize_job import (
    PROMPT_VERSION as JOB_PROMPT_VERSION,
)
from talent_matching.llm.operations.normalize_job import (
    normalize_job,
)
from talent_matching.llm.operations.score_candidate import (
    PROMPT_VERSION as SCORE_PROMPT_VERSION,
)
from talent_matching.llm.operations.score_candidate import (
    score_candidate,
)

__all__ = [
    "CV_PROMPT_VERSION",
    "normalize_cv",
    "JOB_PROMPT_VERSION",
    "normalize_job",
    "SCORE_PROMPT_VERSION",
    "score_candidate",
    "PDF_PROMPT_VERSION",
    "PDFEngine",
    "extract_pdf_text",
    "extract_pdf_from_url",
]
