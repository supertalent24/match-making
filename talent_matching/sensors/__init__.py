"""Dagster sensors for the talent matching pipeline."""

from talent_matching.sensors.airtable_sensor import (
    airtable_candidate_sensor,
    airtable_job_matchmaking_sensor,
)
from talent_matching.sensors.run_failure_sensor import run_failure_tagger

__all__ = [
    "airtable_candidate_sensor",
    "airtable_job_matchmaking_sensor",
    "run_failure_tagger",
]
