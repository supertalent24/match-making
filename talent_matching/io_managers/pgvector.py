"""pgvector IO Manager for storing and retrieving vector embeddings.

This IO manager handles the storage of semantic embeddings in PostgreSQL
using the pgvector extension for efficient similarity search.
"""

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


class PgVectorIOManager(ConfigurableIOManager):
    """IO Manager for storing vector embeddings using pgvector.
    
    Handles the following asset types:
    - candidate_vectors: Semantic embeddings for candidates
    - job_vectors: Semantic embeddings for job descriptions
    
    Vectors are stored with metadata including:
    - vector_type: Type of embedding (position, experience, domain_context, personality, etc.)
    - model_version: Which embedding model generated the vector
    
    The pgvector extension enables efficient cosine similarity search
    using HNSW indexes.
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

    def _vector_to_pg(self, vector: list[float]) -> str:
        """Convert Python list to pgvector format string."""
        return "[" + ",".join(str(v) for v in vector) + "]"

    def _pg_to_vector(self, pg_vector: str) -> list[float]:
        """Convert pgvector format string to Python list."""
        # pgvector returns vectors as '[1.0,2.0,3.0]' strings
        if isinstance(pg_vector, list):
            return pg_vector
        clean = pg_vector.strip("[]")
        return [float(x) for x in clean.split(",")]

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Store vector embeddings in PostgreSQL with pgvector.
        
        Args:
            context: Dagster output context with asset metadata
            obj: Vector data to store (list of dicts with 'vector' and metadata)
        """
        table_name = self._get_table_name(context)
        
        if table_name == "candidate_vectors":
            self._store_candidate_vectors(obj)
        elif table_name == "job_vectors":
            self._store_job_vectors(obj)
        else:
            context.log.warning(f"Unknown vector table: {table_name}")

        context.log.info(f"Stored vectors to table: {table_name}")

    def load_input(self, context: InputContext) -> Any:
        """Load vector embeddings from PostgreSQL.
        
        Args:
            context: Dagster input context with asset metadata
            
        Returns:
            List of vector records with metadata
        """
        table_name = self._get_table_name(context)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Load vectors with their metadata
        if table_name == "candidate_vectors":
            cursor.execute(
                """
                SELECT id, candidate_id, vector_type, vector::text, model_version, created_at
                FROM candidate_vectors
                ORDER BY created_at DESC
                LIMIT 1000
                """
            )
        elif table_name == "job_vectors":
            cursor.execute(
                """
                SELECT id, job_id, vector_type, vector::text, model_version, created_at
                FROM job_vectors
                ORDER BY created_at DESC
                LIMIT 1000
                """
            )
        else:
            cursor.close()
            conn.close()
            return []
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert to list of dicts with parsed vectors
        result = []
        for row in rows:
            if table_name == "candidate_vectors":
                record = {
                    "id": str(row[0]),
                    "candidate_id": str(row[1]),
                    "vector_type": row[2],
                    "vector": self._pg_to_vector(row[3]),
                    "model_version": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                }
            else:
                record = {
                    "id": str(row[0]),
                    "job_id": str(row[1]),
                    "vector_type": row[2],
                    "vector": self._pg_to_vector(row[3]),
                    "model_version": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                }
            result.append(record)
        
        context.log.info(f"Loaded {len(result)} vectors from table: {table_name}")
        return result

    def _store_candidate_vectors(self, data: list[dict[str, Any]]) -> None:
        """Store candidate embedding vectors."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            vector = record.get("vector", [])
            if not vector:
                continue
                
            cursor.execute(
                """
                INSERT INTO candidate_vectors 
                (id, candidate_id, vector_type, vector, model_version, created_at)
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    record.get("candidate_id"),
                    record.get("vector_type", "unknown"),
                    self._vector_to_pg(vector),
                    record.get("model_version", "mock-embedding-v1"),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def _store_job_vectors(self, data: list[dict[str, Any]]) -> None:
        """Store job embedding vectors."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for record in data if isinstance(data, list) else [data]:
            vector = record.get("vector", [])
            if not vector:
                continue
                
            cursor.execute(
                """
                INSERT INTO job_vectors 
                (id, job_id, vector_type, vector, model_version, created_at)
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    record.get("job_id"),
                    record.get("vector_type", "unknown"),
                    self._vector_to_pg(vector),
                    record.get("model_version", "mock-embedding-v1"),
                    datetime.now(),
                ),
            )
        
        conn.commit()
        cursor.close()
        conn.close()

    def find_similar_candidates(
        self,
        query_vector: list[float],
        vector_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find candidates with similar vectors using cosine similarity.
        
        Args:
            query_vector: Vector to compare against
            vector_type: Optional filter by vector type
            limit: Maximum number of results
            
        Returns:
            List of candidates sorted by similarity (highest first)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query_pg = self._vector_to_pg(query_vector)
        
        if vector_type:
            cursor.execute(
                """
                SELECT candidate_id, vector_type, 
                       1 - (vector <=> %s::vector) as similarity
                FROM candidate_vectors
                WHERE vector_type = %s
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (query_pg, vector_type, query_pg, limit),
            )
        else:
            cursor.execute(
                """
                SELECT candidate_id, vector_type,
                       1 - (vector <=> %s::vector) as similarity
                FROM candidate_vectors
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (query_pg, query_pg, limit),
            )
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [
            {
                "candidate_id": str(row[0]),
                "vector_type": row[1],
                "similarity": float(row[2]),
            }
            for row in rows
        ]

    def find_similar_jobs(
        self,
        query_vector: list[float],
        vector_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find jobs with similar vectors using cosine similarity.
        
        Args:
            query_vector: Vector to compare against
            vector_type: Optional filter by vector type
            limit: Maximum number of results
            
        Returns:
            List of jobs sorted by similarity (highest first)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query_pg = self._vector_to_pg(query_vector)
        
        if vector_type:
            cursor.execute(
                """
                SELECT job_id, vector_type,
                       1 - (vector <=> %s::vector) as similarity
                FROM job_vectors
                WHERE vector_type = %s
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (query_pg, vector_type, query_pg, limit),
            )
        else:
            cursor.execute(
                """
                SELECT job_id, vector_type,
                       1 - (vector <=> %s::vector) as similarity
                FROM job_vectors
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (query_pg, query_pg, limit),
            )
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [
            {
                "job_id": str(row[0]),
                "vector_type": row[1],
                "similarity": float(row[2]),
            }
            for row in rows
        ]
