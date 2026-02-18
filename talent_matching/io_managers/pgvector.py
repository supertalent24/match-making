"""pgvector IO Manager using SQLAlchemy ORM.

This IO manager handles the storage and retrieval of vector embeddings
using SQLAlchemy with pgvector extension for efficient similarity search.
"""

from typing import Any
from uuid import uuid4

from dagster import ConfigurableIOManager, InputContext, OutputContext
from pydantic import Field
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from talent_matching.models import CandidateVector, JobVector, RawCandidate, RawJob


class PgVectorIOManager(ConfigurableIOManager):
    """IO Manager for storing vector embeddings using SQLAlchemy with pgvector.

    Handles the following asset types:
    - candidate_vectors: Semantic embeddings for candidates
    - job_vectors: Semantic embeddings for job descriptions

    Vectors are stored with metadata including:
    - vector_type: Type of embedding (position, experience, domain_context, etc.)
    - model_version: Which embedding model generated the vector

    Uses pgvector's SQLAlchemy integration for native vector operations
    including cosine similarity search with HNSW indexes.
    """

    host: str = Field(description="PostgreSQL host")
    port: int = Field(description="PostgreSQL port")
    user: str = Field(description="PostgreSQL user")
    password: str = Field(description="PostgreSQL password")
    database: str = Field(description="PostgreSQL database name")

    _engine: Any = None
    _session_factory: Any = None

    def _get_engine(self):
        """Create or return cached SQLAlchemy engine."""
        if self._engine is None:
            url = (
                f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
            )
            self._engine = create_engine(url, pool_pre_ping=True)
            self._session_factory = sessionmaker(bind=self._engine)
        return self._engine

    def _get_session(self) -> Session:
        """Create a new database session."""
        self._get_engine()
        return self._session_factory()

    def _get_table_name(self, context: OutputContext | InputContext) -> str:
        """Derive table name from asset key."""
        asset_key = context.asset_key
        if asset_key:
            return "_".join(asset_key.path)
        return "unknown"

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Store vector embeddings using SQLAlchemy ORM.

        Args:
            context: Dagster output context with asset metadata
            obj: Vector data to store (dict or list of dicts with 'vector' and metadata)
        """
        table_name = self._get_table_name(context)

        if table_name == "candidate_vectors":
            self._store_candidate_vectors(context, obj)
        elif table_name == "job_vectors":
            self._store_job_vectors(context, obj)
        else:
            context.log.warning(f"Unknown vector table: {table_name}")

        context.log.info(f"Stored vectors to table: {table_name}")

    def load_input(self, context: InputContext) -> Any:
        """Load vector embeddings using SQLAlchemy ORM.

        Args:
            context: Dagster input context with asset metadata

        Returns:
            List of vector records with metadata
        """
        table_name = self._get_table_name(context)
        session = self._get_session()

        partition_key = context.partition_key if hasattr(context, "partition_key") else None

        if table_name == "candidate_vectors":
            if partition_key:
                # Get candidate ID from partition key
                raw_candidate = session.execute(
                    select(RawCandidate).where(RawCandidate.airtable_record_id == partition_key)
                ).scalar_one_or_none()

                if raw_candidate:
                    stmt = select(CandidateVector).where(
                        CandidateVector.candidate_id == raw_candidate.id
                    )
                    results = session.execute(stmt).scalars().all()
                else:
                    results = []
            else:
                stmt = select(CandidateVector).limit(1000)
                results = session.execute(stmt).scalars().all()

            session.close()
            return [self._vector_to_dict(r, "candidate_id") for r in results]

        elif table_name == "job_vectors":
            if partition_key:
                raw_job = session.execute(
                    select(RawJob).where(RawJob.airtable_record_id == partition_key)
                ).scalar_one_or_none()

                if raw_job:
                    stmt = select(JobVector).where(JobVector.job_id == raw_job.id)
                    results = session.execute(stmt).scalars().all()
                else:
                    results = []
            else:
                stmt = select(JobVector).limit(1000)
                results = session.execute(stmt).scalars().all()

            session.close()
            return [self._vector_to_dict(r, "job_id") for r in results]

        session.close()
        return []

    def _vector_to_dict(self, model_instance: Any, id_field: str) -> dict[str, Any]:
        """Convert vector model instance to dictionary."""
        return {
            "id": str(model_instance.id),
            id_field: str(getattr(model_instance, id_field)),
            "vector_type": model_instance.vector_type,
            "vector": list(model_instance.vector),  # pgvector returns numpy array
            "model_version": model_instance.model_version,
            "created_at": model_instance.created_at.isoformat()
            if model_instance.created_at
            else None,
        }

    def _store_candidate_vectors(self, context: OutputContext, data: Any) -> None:
        """Store candidate embedding vectors using SQLAlchemy ORM.

        Deletes all existing vectors for the candidate before inserting new ones.
        This ensures old vector types are removed when re-materializing.
        """
        session = self._get_session()
        partition_key = context.partition_key

        # Get the raw candidate ID
        raw_candidate = session.execute(
            select(RawCandidate).where(RawCandidate.airtable_record_id == partition_key)
        ).scalar_one_or_none()

        if not raw_candidate:
            context.log.error(f"Raw candidate not found for: {partition_key}")
            session.close()
            return

        # Delete all existing vectors for this candidate before inserting new ones
        # This removes legacy vector types when re-materializing
        deleted = session.execute(
            CandidateVector.__table__.delete().where(
                CandidateVector.candidate_id == raw_candidate.id
            )
        )
        deleted_count = deleted.rowcount
        if deleted_count > 0:
            context.log.info(f"Deleted {deleted_count} existing vectors for: {partition_key}")

        # Handle single dict or list of dicts
        records = data if isinstance(data, list) else [data]

        for record in records:
            vector = record.get("vector", [])
            if not vector:
                continue

            values = {
                "id": uuid4(),
                "candidate_id": raw_candidate.id,
                "vector_type": record.get("vector_type", "unknown"),
                "vector": vector,
                "model_version": record.get("model_version", "unknown"),
            }

            stmt = insert(CandidateVector).values(**values)
            session.execute(stmt)

        session.commit()
        session.close()
        context.log.info(f"Stored {len(records)} candidate vectors for: {partition_key}")

    def _store_job_vectors(self, context: OutputContext, data: Any) -> None:
        """Store job embedding vectors using SQLAlchemy ORM.

        Deletes all existing vectors for the job before inserting new ones.
        This ensures old vector types are removed when re-materializing.
        """
        session = self._get_session()
        partition_key = context.partition_key if hasattr(context, "partition_key") else None
        if partition_key:
            record_id = partition_key
        elif isinstance(data, list) and data:
            record_id = data[0].get("airtable_record_id")
        elif isinstance(data, dict):
            record_id = data.get("airtable_record_id")
        else:
            record_id = None

        # Get the raw job ID
        raw_job = None
        if record_id:
            raw_job = session.execute(
                select(RawJob).where(RawJob.airtable_record_id == record_id)
            ).scalar_one_or_none()

        if not raw_job:
            context.log.error(f"Raw job not found for: {record_id}")
            session.close()
            return

        # Delete all existing vectors for this job before inserting new ones
        # This removes legacy vector types when re-materializing
        deleted = session.execute(
            JobVector.__table__.delete().where(JobVector.job_id == raw_job.id)
        )
        deleted_count = deleted.rowcount
        if deleted_count > 0:
            context.log.info(f"Deleted {deleted_count} existing vectors for job: {record_id}")

        records = data if isinstance(data, list) else [data]

        for record in records:
            vector = record.get("vector", [])
            if not vector:
                continue

            values = {
                "id": uuid4(),
                "job_id": raw_job.id,
                "vector_type": record.get("vector_type", "unknown"),
                "vector": vector,
                "model_version": record.get("model_version", "unknown"),
            }

            stmt = insert(JobVector).values(**values)
            session.execute(stmt)

        session.commit()
        session.close()
        context.log.info(f"Stored {len(records)} job vectors for: {record_id}")

    def find_similar_candidates(
        self,
        query_vector: list[float],
        vector_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find candidates with similar vectors using cosine similarity.

        Uses pgvector's native cosine distance operator via SQLAlchemy.

        Args:
            query_vector: Vector to compare against
            vector_type: Optional filter by vector type
            limit: Maximum number of results

        Returns:
            List of candidates sorted by similarity (highest first)
        """
        session = self._get_session()

        # Build query with cosine distance
        stmt = select(
            CandidateVector.candidate_id,
            CandidateVector.vector_type,
            # Cosine similarity = 1 - cosine_distance
            (1 - CandidateVector.vector.cosine_distance(query_vector)).label("similarity"),
        )

        if vector_type:
            stmt = stmt.where(CandidateVector.vector_type == vector_type)

        stmt = stmt.order_by(CandidateVector.vector.cosine_distance(query_vector)).limit(limit)

        results = session.execute(stmt).all()
        session.close()

        return [
            {
                "candidate_id": str(row.candidate_id),
                "vector_type": row.vector_type,
                "similarity": float(row.similarity),
            }
            for row in results
        ]

    def find_similar_jobs(
        self,
        query_vector: list[float],
        vector_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find jobs with similar vectors using cosine similarity.

        Uses pgvector's native cosine distance operator via SQLAlchemy.

        Args:
            query_vector: Vector to compare against
            vector_type: Optional filter by vector type
            limit: Maximum number of results

        Returns:
            List of jobs sorted by similarity (highest first)
        """
        session = self._get_session()

        stmt = select(
            JobVector.job_id,
            JobVector.vector_type,
            (1 - JobVector.vector.cosine_distance(query_vector)).label("similarity"),
        )

        if vector_type:
            stmt = stmt.where(JobVector.vector_type == vector_type)

        stmt = stmt.order_by(JobVector.vector.cosine_distance(query_vector)).limit(limit)

        results = session.execute(stmt).all()
        session.close()

        return [
            {
                "job_id": str(row.job_id),
                "vector_type": row.vector_type,
                "similarity": float(row.similarity),
            }
            for row in results
        ]
