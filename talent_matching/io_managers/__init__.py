"""Dagster IO managers for the talent matching pipeline."""

from talent_matching.io_managers.pgvector import PgVectorIOManager
from talent_matching.io_managers.postgres import PostgresMetricsIOManager

__all__ = [
    "PostgresMetricsIOManager",
    "PgVectorIOManager",
]
