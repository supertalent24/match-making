"""PostgreSQL IO Manager for storing structured candidate and job metrics.

This IO manager handles the storage and retrieval of normalized profiles,
raw data, and other queryable metrics in PostgreSQL using JSONB columns.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any

import psycopg2
from dagster import (
    ConfigurableIOManager,
    InputContext,
    OutputContext,
)
from pydantic import Field


class PostgresMetricsIOManager(ConfigurableIOManager):
    """IO Manager for storing structured data in PostgreSQL.
    
    Handles the following asset types:
    - raw_candidates: Raw ingested candidate data
    - normalized_candidates: LLM-normalized candidate profiles
    - raw_jobs: Raw job descriptions
    - normalized_jobs: LLM-normalized job requirements
    - matches: Computed match results
    
    Data is stored in JSONB columns for flexible schema evolution,
    with versioning metadata for prompt and model tracking.
    """

    host: str = Field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    port: int = Field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    user: str = Field(default_factory=lambda: os.getenv("POSTGRES_USER", "talent"))
    password: str = Field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "talent_dev"))
    database: str = Field(default_factory=lambda: os.getenv("POSTGRES_DB", "talent_matching"))

    def _get_connection(self):
        """Create a database connection."""
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.database,
        )

    def _get_table_name(self, context: OutputContext | InputContext) -> str:
        """Derive table name from asset key."""
        asset_key = context.asset_key
        if asset_key:
            return "_".join(asset_key.path)
        return "unknown"

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Store output data in PostgreSQL.
        
        Args:
            context: Dagster output context with asset metadata
            obj: Data to store (dict, list of dicts, or other serializable data)
        """
        table_name = self._get_table_name(context)
        
        # Handle different asset types
        if table_name == "raw_candidates":
            self._store_raw_candidates(obj)
        elif table_name == "normalized_candidates":
            self._store_normalized_candidates(obj)
        elif table_name == "raw_jobs":
            self._store_raw_jobs(obj)
        elif table_name == "normalized_jobs":
            self._store_normalized_jobs(obj)
        elif table_name == "matches":
            self._store_matches(obj)
        else:
            # Generic storage for unknown asset types
            self._store_generic(table_name, obj)

        context.log.info(f"Stored data to table: {table_name}")

    def load_input(self, context: InputContext) -> Any:
        """Load data from PostgreSQL.
        
        Args:
            context: Dagster input context with asset metadata
            
        Returns:
            Retrieved data from the database
        """
        table_name = self._get_table_name(context)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Load all records from the table
        # In production, you'd want pagination or filtering
        query = f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 1000"
        cursor.execute(query)
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Convert to list of dicts
        result = []
        for row in rows:
            record = dict(zip(columns, row))
            # Parse JSONB columns
            for key, value in record.items():
                if isinstance(value, str) and value.startswith("{"):
                    record[key] = json.loads(value)
            result.append(record)
        
        context.log.info(f"Loaded {len(result)} records from table: {table_name}")
        return result

    def _store_raw_candidates(self, data: list[dict[str, Any]]) -> None:
        """Store raw candidate data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            cursor.execute(
                """
                INSERT INTO raw_candidates (id, source, raw_data, ingested_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET raw_data = EXCLUDED.raw_data
                """,
                (
                    record.get("id", str(uuid.uuid4())),
                    record.get("source", "unknown"),
                    json.dumps(record.get("raw_data", record)),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_normalized_candidates(self, data: list[dict[str, Any]]) -> None:
        """Store normalized candidate profiles."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            cursor.execute(
                """
                INSERT INTO normalized_candidates 
                (id, candidate_id, normalized_json, prompt_version, model_version, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    record.get("candidate_id"),
                    json.dumps(record.get("normalized_json", record)),
                    record.get("prompt_version", "v1.0.0"),
                    record.get("model_version", "mock-v1"),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_raw_jobs(self, data: list[dict[str, Any]]) -> None:
        """Store raw job descriptions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            cursor.execute(
                """
                INSERT INTO raw_jobs (id, company_id, raw_description, ingested_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET raw_description = EXCLUDED.raw_description
                """,
                (
                    record.get("id", str(uuid.uuid4())),
                    record.get("company_id"),
                    record.get("raw_description", ""),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_normalized_jobs(self, data: list[dict[str, Any]]) -> None:
        """Store normalized job requirements."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            cursor.execute(
                """
                INSERT INTO normalized_jobs 
                (id, job_id, normalized_json, prompt_version, model_version, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    record.get("job_id"),
                    json.dumps(record.get("normalized_json", record)),
                    record.get("prompt_version", "v1.0.0"),
                    record.get("model_version", "mock-v1"),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_matches(self, data: list[dict[str, Any]]) -> None:
        """Store match results."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            cursor.execute(
                """
                INSERT INTO matches 
                (id, job_id, candidate_id, match_score, keyword_score, vector_score, breakdown_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id, candidate_id) DO UPDATE SET 
                    match_score = EXCLUDED.match_score,
                    breakdown_json = EXCLUDED.breakdown_json
                """,
                (
                    str(uuid.uuid4()),
                    record.get("job_id"),
                    record.get("candidate_id"),
                    record.get("match_score", 0.0),
                    record.get("keyword_score"),
                    record.get("vector_score"),
                    json.dumps(record.get("breakdown", {})),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_generic(self, table_name: str, data: Any) -> None:
        """Generic storage for unknown asset types."""
        # For now, just log that we don't handle this type
        # In production, you might create a generic key-value table
        pass
