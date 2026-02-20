"""Matchmaking resource: job required skills, candidate skills, and DB helpers for scoring."""

from typing import Any
from uuid import UUID

from dagster import ConfigurableResource
from pydantic import Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from talent_matching.models.candidates import CandidateSkill, NormalizedCandidate
from talent_matching.models.enums import RequirementTypeEnum
from talent_matching.models.jobs import JobRequiredSkill
from talent_matching.models.skills import Skill
from talent_matching.utils.airtable_mapper import NORMALIZED_CANDIDATE_SYNCABLE_FIELDS


class MatchmakingResource(ConfigurableResource):
    """Provides job required skills (and optional helpers) for the matches asset."""

    host: str = Field(description="PostgreSQL host")
    port: int = Field(description="PostgreSQL port")
    user: str = Field(description="PostgreSQL user")
    password: str = Field(description="PostgreSQL password")
    database: str = Field(description="PostgreSQL database name")

    _engine: Any = None
    _session_factory: Any = None

    def _get_engine(self):
        if self._engine is None:
            url = (
                f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
            )
            self._engine = create_engine(url, pool_pre_ping=True)
            self._session_factory = sessionmaker(bind=self._engine)
        return self._engine

    def _get_session(self) -> Session:
        self._get_engine()
        return self._session_factory()

    def get_job_required_skills(
        self,
        job_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Return for each job_id the list of required skills with name and type.

        Args:
            job_ids: List of normalized job UUIDs (strings).

        Returns:
            Dict mapping job_id (str) to list of {"skill_name": str, "requirement_type": "must_have"|"nice_to_have"}.
        """
        if not job_ids:
            return {}
        uuids = [UUID(jid) if isinstance(jid, str) else jid for jid in job_ids]
        session = self._get_session()
        stmt = (
            select(
                JobRequiredSkill.job_id,
                Skill.name,
                JobRequiredSkill.requirement_type,
                JobRequiredSkill.min_years,
            )
            .join(Skill, JobRequiredSkill.skill_id == Skill.id)
            .where(JobRequiredSkill.job_id.in_(uuids))
        )
        rows = session.execute(stmt).all()
        session.close()

        result: dict[str, list[dict[str, Any]]] = {jid: [] for jid in job_ids}
        for row in rows:
            job_id, name, req_type, min_years = row
            jid_str = str(job_id)
            result.setdefault(jid_str, []).append(
                {
                    "skill_name": name,
                    "requirement_type": (
                        RequirementTypeEnum.NICE_TO_HAVE.value
                        if req_type == RequirementTypeEnum.NICE_TO_HAVE
                        else RequirementTypeEnum.MUST_HAVE.value
                    ),
                    "min_years": min_years,
                }
            )
        return result

    def get_candidate_skills(
        self,
        candidate_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Return for each candidate_id the list of skills with name, rating, years_experience.

        Args:
            candidate_ids: List of normalized candidate UUIDs (strings).

        Returns:
            Dict mapping candidate_id (str) to list of {"skill_name": str, "rating": int 1-10, "years_experience": int or None}.
        """
        if not candidate_ids:
            return {}
        uuids = [UUID(cid) if isinstance(cid, str) else cid for cid in candidate_ids]
        session = self._get_session()
        stmt = (
            select(
                CandidateSkill.candidate_id,
                Skill.name,
                CandidateSkill.rating,
                CandidateSkill.years_experience,
            )
            .join(Skill, CandidateSkill.skill_id == Skill.id)
            .where(CandidateSkill.candidate_id.in_(uuids))
        )
        rows = session.execute(stmt).all()
        session.close()

        result: dict[str, list[dict[str, Any]]] = {cid: [] for cid in candidate_ids}
        for cand_id, name, rating, years in rows:
            cid_str = str(cand_id)
            result.setdefault(cid_str, []).append(
                {
                    "skill_name": name,
                    "rating": int(rating) if rating is not None else 5,
                    "years_experience": int(years) if years is not None else None,
                }
            )
        return result

    def get_normalized_candidate_by_airtable_record_id(
        self, airtable_record_id: str
    ) -> dict[str, Any] | None:
        """Load a single NormalizedCandidate row by airtable_record_id as a dict of syncable fields.

        Returns None if no row exists. Keys are attribute names (e.g. full_name, professional_summary).
        Used by airtable_candidate_sync to build the Airtable PATCH payload.
        """
        session = self._get_session()
        row = session.execute(
            select(NormalizedCandidate).where(
                NormalizedCandidate.airtable_record_id == airtable_record_id
            )
        ).scalar_one_or_none()
        if row is None:
            session.close()
            return None
        candidate = {name: getattr(row, name) for name in NORMALIZED_CANDIDATE_SYNCABLE_FIELDS}
        session.close()
        return candidate
