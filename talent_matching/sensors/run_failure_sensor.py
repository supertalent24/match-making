"""Run failure sensor that tags failed runs with classified failure reasons.

Known failures are tagged with a specific category (e.g. PDF_EXTRACTION_FAILED).
Unknown failures are tagged with UNKNOWN_FAILURE so they surface for investigation.
"""

import dagster as dg

FAILURE_TAG = "failure_type"

KNOWN_FAILURES: list[tuple[str, list[str]]] = [
    (
        "PDF_INVALID",
        ["Invalid PDF", "FileDataError", "Failed to open stream", "FzErrorFormat"],
    ),
    (
        "PDF_DOWNLOAD_FAILED",
        ["PDF download failed", "ConnectError", "TimeoutException"],
    ),
    (
        "OPENROUTER_API_ERROR",
        ["openrouter.ai", "HTTPStatusError", "422 Unprocessable Entity"],
    ),
    (
        "INVALID_ENUM_VALUE",
        ["InvalidTextRepresentation", "invalid input value for enum"],
    ),
    (
        "STRING_TRUNCATION",
        ["StringDataRightTruncation", "value too long for type"],
    ),
    (
        "LLM_JSON_PARSE_ERROR",
        ["JSONDecodeError", "Expecting value"],
    ),
    (
        "AIRTABLE_API_ERROR",
        ["airtable.com", "AUTHENTICATION_REQUIRED", "TABLE_NOT_FOUND"],
    ),
    (
        "RATE_LIMIT",
        ["429", "Too Many Requests", "rate limit"],
    ),
]


def _classify_failure(error_str: str) -> list[str]:
    """Return all matching failure tags for the given error string."""
    tags = []
    for tag, patterns in KNOWN_FAILURES:
        if any(p.lower() in error_str.lower() for p in patterns):
            tags.append(tag)
    return tags


@dg.run_failure_sensor(
    name="run_failure_tagger",
    description=(
        "Tags failed runs with classified failure reasons. "
        "Known failures get a specific tag; unknown failures get UNKNOWN_FAILURE."
    ),
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def run_failure_tagger(context: dg.RunFailureSensorContext):
    run_id = context.dagster_run.run_id
    job_name = context.dagster_run.job_name

    step_failure_events = context.get_step_failure_events()

    all_tags: set[str] = set()

    for event in step_failure_events:
        failure_data = event.step_failure_data
        if failure_data is None:
            continue
        error = failure_data.error
        if error is None:
            continue

        error_str = error.to_string()
        matched = _classify_failure(error_str)
        all_tags.update(matched)

    if not all_tags:
        all_tags.add("UNKNOWN_FAILURE")

    tag_value = ", ".join(sorted(all_tags))
    context.instance.add_run_tags(run_id, {FAILURE_TAG: tag_value})

    context.log.info(f"Tagged failed run {run_id} ({job_name}) with {FAILURE_TAG}={tag_value}")
