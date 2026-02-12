"""Dagster sensors for the talent matching pipeline."""

from talent_matching.sensors.airtable_sensor import airtable_candidate_sensor

__all__ = [
    "airtable_candidate_sensor",
]
