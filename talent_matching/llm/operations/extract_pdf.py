"""PDF text extraction using OpenRouter's native PDF support.

OpenRouter offers native PDF processing via their API:
- pdf-text: Free, works well for structured digital PDFs
- mistral-ocr: $2/1000 pages, best for scanned documents
- native: Uses model's native file processing (charged as tokens)

See: https://openrouter.ai/docs/guides/overview/multimodal/pdfs

Bump PROMPT_VERSION when changing the prompt to trigger asset staleness.
"""

import base64
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from talent_matching.resources.openrouter import OpenRouterResource

# Bump this version when the prompt changes
PROMPT_VERSION = "1.0.0"

# Default model for PDF extraction - GPT-4o-mini is cost-effective for extraction
DEFAULT_MODEL = "openai/gpt-4o-mini"


class PDFEngine(str, Enum):
    """PDF processing engines available on OpenRouter."""

    PDF_TEXT = "pdf-text"  # Free, best for digital PDFs
    MISTRAL_OCR = "mistral-ocr"  # $2/1000 pages, best for scanned docs
    NATIVE = "native"  # Model's native processing


DEFAULT_PDF_ENGINE = PDFEngine.PDF_TEXT

SYSTEM_PROMPT = """You are a CV/resume text extractor. Extract ALL text from this document.

IMPORTANT:
- Extract the complete text, preserving the structure and formatting
- Include all sections: contact info, summary, experience, education, skills, projects
- Keep bullet points and list structures
- Preserve dates, company names, job titles exactly as written
- If text is unclear or partially visible, make your best effort to transcribe it
- Do NOT summarize or interpret - just extract the raw text

Output the extracted text as plain text, preserving paragraph breaks."""


@dataclass
class ExtractPDFResult:
    """Result of PDF text extraction with usage stats."""

    text: str
    pages_processed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    prompt_version: str
    pdf_engine: str = "unknown"
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def failed(self) -> bool:
        return self.error is not None


async def download_pdf(url: str, timeout: float = 60.0) -> bytes:
    """Download PDF from URL (supports Airtable attachment URLs).

    Args:
        url: URL to download PDF from
        timeout: Request timeout in seconds

    Returns:
        PDF file bytes
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return response.content


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Get page count from PDF bytes.

    Raises ValueError if the bytes are not a valid PDF.
    """
    import fitz  # pymupdf

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Invalid PDF: {exc}") from exc
    count = len(doc)
    doc.close()
    return count


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to base64 data URL for OpenRouter API."""
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return f"data:application/pdf;base64,{b64}"


def _failed_result(
    model: str,
    engine_value: str,
    error: str,
) -> ExtractPDFResult:
    return ExtractPDFResult(
        text="",
        pages_processed=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        model=model,
        prompt_version=PROMPT_VERSION,
        pdf_engine=engine_value,
        error=error,
    )


async def extract_pdf_text(
    openrouter: "OpenRouterResource",
    pdf_bytes: bytes,
    model: str | None = None,
    pdf_engine: PDFEngine | str | None = None,
) -> ExtractPDFResult:
    """Extract text from PDF using OpenRouter's native PDF support.

    Uses OpenRouter's PDF processing engines directly, which is more efficient
    than converting to images.

    Returns a result with ``error`` set (instead of raising) when the PDF is
    invalid or the API rejects the request, so callers can fall back gracefully.

    Args:
        openrouter: OpenRouterResource instance for API calls
        pdf_bytes: Raw PDF file bytes
        model: Model to use (defaults to gpt-4o-mini)
        pdf_engine: PDF processing engine:
            - PDFEngine.PDF_TEXT (free): Best for digital PDFs
            - PDFEngine.MISTRAL_OCR ($2/1000 pages): Best for scanned docs
            - PDFEngine.NATIVE: Use model's native processing

    Returns:
        ExtractPDFResult with extracted text and usage stats
    """
    model = model or DEFAULT_MODEL
    engine = pdf_engine or DEFAULT_PDF_ENGINE
    engine_value = engine.value if isinstance(engine, PDFEngine) else engine

    try:
        page_count = get_pdf_page_count(pdf_bytes)
    except ValueError as exc:
        return _failed_result(model, engine_value, str(exc))

    if page_count == 0:
        return _failed_result(model, engine_value, "PDF has 0 pages")

    # Build message with PDF file content
    # OpenRouter supports PDF via the "file" content type with base64 data
    pdf_data_url = pdf_to_base64(pdf_bytes)

    content_parts: list[dict] = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "file",
            "file": {
                "filename": "cv.pdf",
                "file_data": pdf_data_url,
            },
        },
    ]

    # Configure PDF processing engine via plugins
    # See: https://openrouter.ai/docs/guides/overview/multimodal/pdfs
    plugins = [
        {
            "id": "file-parser",
            "pdf": {
                "engine": engine_value,
            },
        },
    ]

    try:
        response = await openrouter.complete(
            messages=[
                {"role": "user", "content": content_parts},
            ],
            model=model,
            operation="extract_pdf",
            temperature=0.0,
            max_tokens=8000,  # CVs can be lengthy
            plugins=plugins,
        )
    except httpx.HTTPStatusError as exc:
        return _failed_result(
            model,
            engine_value,
            f"OpenRouter API {exc.response.status_code}: {exc.response.text[:200]}",
        )

    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})

    return ExtractPDFResult(
        text=content,
        pages_processed=page_count,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        cost_usd=float(usage.get("cost", 0)),
        model=model,
        prompt_version=PROMPT_VERSION,
        pdf_engine=engine_value,
    )


async def extract_pdf_from_url(
    openrouter: "OpenRouterResource",
    pdf_url: str,
    model: str | None = None,
    pdf_engine: PDFEngine | str | None = None,
) -> ExtractPDFResult:
    """Download PDF from URL and extract text using OpenRouter.

    Convenience function that combines download and extraction.
    Returns a result with ``error`` set when download or extraction fails,
    so the caller can fall back to other CV sources.

    Args:
        openrouter: OpenRouterResource instance for API calls
        pdf_url: URL to download PDF from
        model: Model to use (defaults to gpt-4o-mini)
        pdf_engine: PDF processing engine:
            - PDFEngine.PDF_TEXT (free): Best for digital PDFs
            - PDFEngine.MISTRAL_OCR ($2/1000 pages): Best for scanned docs
            - PDFEngine.NATIVE: Use model's native processing

    Returns:
        ExtractPDFResult with extracted text and usage stats
    """
    _model = model or DEFAULT_MODEL
    _engine = pdf_engine or DEFAULT_PDF_ENGINE
    _engine_value = _engine.value if isinstance(_engine, PDFEngine) else _engine

    try:
        pdf_bytes = await download_pdf(pdf_url)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
        return _failed_result(_model, _engine_value, f"PDF download failed: {exc}")

    return await extract_pdf_text(openrouter, pdf_bytes, model=model, pdf_engine=pdf_engine)
